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
