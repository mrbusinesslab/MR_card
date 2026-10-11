"""Explicit batch confirmation with stable Google IDs and retryable indexing."""
import hashlib
import re
from datetime import date,datetime,timedelta
from urllib.parse import quote
from lifeos_calendar_list import CLOCK

def payload(entry,c):
    if entry.get('incomplete') or entry['kind'] not in ('complete','all_day'):
        return None
    title=CLOCK.sub('',entry['title'])
    title=re.sub(r'^\s*(?:全天|上午|下午|晚上|中午|凌晨|早上|到|至|～|~|－|-|–|—|\s)+','',title).strip()
    if not re.search(r'[A-Za-z\u3400-\u9fff]',title):return None
    day=date.fromisoformat(entry['date'])
    result={'summary':title}
    if entry['kind']=='all_day':
        result.update(start={'date':day.isoformat()},end={'date':(day+timedelta(days=1)).isoformat()})
    else:
        a,b=entry['times']
        result.update(start={'dateTime':datetime.fromisoformat(day.isoformat()+'T'+a).replace(tzinfo=c.l.TZ).isoformat(),'timeZone':'Asia/Taipei'},end={'dateTime':datetime.fromisoformat(day.isoformat()+'T'+b).replace(tzinfo=c.l.TZ).isoformat(),'timeZone':'Asia/Taipei'})
    group=c.booking_category(title)
    if group in ('美容','新客','商會','交流'):
        d={'event':result};c.set_category(d,group);result=d['event']
    return c.apply_label(result,group)

def import_batch(c,uid,draft,event_id):
    if draft['review'].get('errors'):
        return c.card('請先修正清單',['日期、星期或筆數仍有問題，這次尚未匯入。'],choices=[('查看清單','清單總覽')])
    # Persist stable identity before any external write. Edits clear unsaved IDs.
    for i,e in enumerate(draft['review']['entries']):
        e.setdefault('google_id',hashlib.sha256((draft['calendar_id']+':'+uid+':'+draft['review_id']+':'+str(i)).encode()).hexdigest())
    c.l.gateway('calendar_draft',uid,event_id,payload=draft)
    done=waiting=failed=0
    for e in draft['review']['entries']:
        if e.get('imported'):done+=1;continue
        try:
            body=payload(e,c)
            if body is None:waiting+=1;continue
            e['write_started']=True
            c.l.gateway('calendar_draft',uid,payload=draft)
            key=e['google_id'];body['extendedProperties']=c.actor_metadata(body,uid,creating=True)
            try:result=c.call('POST',body={**body,'id':key,'conferenceData':None},params={'sendUpdates':'none','conferenceDataVersion':1})
            except c.CalendarError as exc:
                if exc.reason not in ('duplicate','409'):raise
                result=c.call('GET','/'+quote(key,safe=''))
                if result.get('summary')!=body['summary'] or result.get('start')!=body['start'] or result.get('end')!=body['end']:raise c.CalendarError('batch_conflict')
            saved=c.l.gateway('calendar_save',uid,calendar_id=draft['calendar_id'],event_id=key,title=result.get('summary',body['summary']))
            if saved.get('error'):raise c.l.StorageError('index_failed')
            e['imported']=True;done+=1
            c.l.gateway('calendar_draft',uid,payload=draft)
        except (c.CalendarError,c.l.StorageError):failed+=1
    choices=[('查看清單','清單總覽')]
    if failed:choices.insert(0,('重試未完成項目','清單匯入 '+draft['review_id']))
    return c.card('行程匯入結果',[f'已完成 {done} 筆',f'待補資料 {waiting} 筆',f'尚未完成 {failed} 筆','重試會沿用同一行程 ID，避免重複新增。'],choices=choices)

# Keep webhook requests short. Persisted IDs survive worker restarts.
import threading
from contextvars import copy_context
_RUNNING=set()
_LOCK=threading.Lock()

def progress(c,uid,draft):
    entries=draft['review']['entries']
    done=sum(bool(e.get('imported')) for e in entries)
    waiting=sum(not e.get('imported') and (e.get('incomplete') or e['kind'] not in ('complete','all_day')) for e in entries)
    remaining=len(entries)-done-waiting
    key=(draft['calendar_id'],uid,draft['review_id'])
    with _LOCK:running=key in _RUNNING
    choices=[('查看處理進度','清單進度 '+draft['review_id']),('查看清單','清單總覽')]
    if remaining and not running:choices.insert(0,('繼續未完成項目','清單匯入 '+draft['review_id']))
    return c.card('正在加入日曆' if running else '行程匯入狀態',[f'已完成 {done} 筆',f'待補資料 {waiting} 筆',f'尚未完成 {remaining} 筆','處理中；若尚未完成，可按「查看處理進度」，不使用推播通知。' if running else '已完成的項目不會重複新增。'],choices=choices)

class DeferredReply:
    deferred=True

class FreeReply:
    def __init__(self,c,uid,draft):
        self.c=c;self.uid=uid;self.draft=draft;self.token=None;self.sent=False;self.lock=threading.Lock()
        try:
            from flask import request
            for e in (request.get_json(silent=True) or {}).get('events',[]):
                if e.get('source',{}).get('userId')==uid and e.get('message',{}).get('text')=='清單匯入 '+draft['review_id']:
                    self.token=e.get('replyToken');break
        except RuntimeError:pass
    def send(self,message):
        if not self.token:return
        with self.lock:
            if self.sent:return
            self.sent=True
        import os,requests
        try:
            from lifeos_settings import getenv
        except ImportError:getenv=os.getenv
        response=requests.post('https://api.line.me/v2/bot/message/reply',headers={'Authorization':'Bearer '+getenv('LINE_CHANNEL_ACCESS_TOKEN','')},json={'replyToken':self.token,'messages':[message.to_dict()]},timeout=10)
        response.raise_for_status()

def start_import(c,uid,draft,event_id):
    if draft['review'].get('errors'):return import_batch(c,uid,draft,event_id)
    free_reply=FreeReply(c,uid,draft)
    key=(draft['calendar_id'],uid,draft['review_id'])
    with _LOCK:
        if key in _RUNNING:launch=False
        else:_RUNNING.add(key);launch=True
    if launch:
        context=copy_context()
        def execute():
            try:message=import_batch(c,uid,draft,event_id)
            except Exception:
                message=c.card('行程尚未全部完成',['處理中斷，已完成項目保留。請查看清單並重試未完成項目。'],choices=[('查看清單','清單總覽')])
            free_reply.send(message)
        def work():
            try:context.run(execute)
            except Exception:
                import logging
                logging.getLogger(__name__).exception('Calendar batch background import failed')
            finally:
                with _LOCK:_RUNNING.discard(key)
        threading.Thread(target=work,daemon=True,name='calendar-batch').start()
        if free_reply.token:
            context_timer=copy_context()
            def timeout_reply():
                try:context_timer.run(lambda:free_reply.send(progress(c,uid,draft)))
                except Exception:pass
            timer=threading.Timer(40,timeout_reply);timer.daemon=True;timer.start()
    return DeferredReply() if launch and free_reply.token else progress(c,uid,draft)
