"""Google Calendar pilot, restricted to one approved LINE user and calendar."""
import hashlib
import hmac
import json
import os
import re
from datetime import timedelta
from urllib.parse import quote
import requests
from google.oauth2 import service_account
from google.auth.transport.requests import AuthorizedSession
import lifeos as l

TIME_PATTERN=r'(上午|早上|下午|晚上|中午|凌晨)?\s*(\d{1,2}|[零一二兩三四五六七八九十]+)(?:點|時|:|：)(半|\d{1,2}|[一二三四五六七八九十]+)?(?:分)?'
COMMANDS=('其他天的行程','Google日曆','新增行程','行程 ','確認行程','放棄行程','改期行程')

class CalendarError(Exception):
    def __init__(self,reason): self.reason=reason

def config():
    try: info=json.loads(os.getenv('GOOGLE_SERVICE_ACCOUNT_JSON','{}'))
    except ValueError: info={}
    return info,os.getenv('LIFEOS_GOOGLE_CALENDAR_ID',''),os.getenv('LIFEOS_GOOGLE_USER_ID','')

def call(method,path='',body=None,params=None,etag=None):
    info,cal,_=config()
    if not info.get('client_email') or not cal: raise CalendarError('not_configured')
    try:
        creds=service_account.Credentials.from_service_account_info(info,scopes=['https://www.googleapis.com/auth/calendar.events'])
        with AuthorizedSession(creds,refresh_timeout=10) as session:
            response=session.request(method,'https://www.googleapis.com/calendar/v3/calendars/'+quote(cal,safe='')+'/events'+path,
                json=body,params=params,headers={'If-Match':etag} if etag else {},timeout=12)
        if response.status_code>=400:
            reason=str(response.status_code)
            try: reason=response.json()['error'].get('errors',[{}])[0].get('reason',reason)
            except (ValueError,KeyError,IndexError): pass
            raise CalendarError(reason)
        return response.json()
    except CalendarError: raise
    except Exception as exc: raise CalendarError('connection_failed') from exc

def parse_range(text,now=None,title_required=True):
    now=now or l.clock()
    times=list(re.finditer(TIME_PATTERN,text))
    if len(times)!=2: raise l.InputError('請提供開始與結束時間，例如「行程 明天下午2點到下午3點 美容預約」。')
    start,spans=l.parse_date(text,now)
    if start is None: raise l.InputError('請補上行程日期。')
    end,_=l.parse_date(start.strftime('%Y/%m/%d')+' '+times[1].group(),now)
    if end<=start: raise l.InputError('結束時間必須晚於開始時間；這版先支援同一天的行程。')
    if re.search(r'每(?:天|日|週|星期|月|年)|每個月',text): raise l.InputError('這版尚未支援重複行程。')
    dates=re.findall(r'今天|今日|明天|後天|(?:下下|下|本|這)?(?:星期|禮拜|週)[一二三四五六日天]|(?:(?:20\d{2})[年/\-])?\d{1,2}[月/\-]\d{1,2}(?:日|號)?',text)
    if len(dates)>1: raise l.InputError('這版先支援同一天的行程，請只提供一個日期。')
    all_spans=spans+[m.span() for m in times]
    title=''.join(ch for i,ch in enumerate(text) if not any(a<=i<b for a,b in all_spans))
    title=re.sub(r'^\s*(?:至|到|～|~|-)\s*','',title).strip(' ，,。')
    if title_required and (not title or len(title)>500): raise l.InputError('請提供500字以内的行程名稱。')
    return title,start,end

def event_time(event):
    from datetime import datetime
    start=event.get('start',{});end=event.get('end',{})
    if 'dateTime' in start:
        a=datetime.fromisoformat(start['dateTime'].replace('Z','+00:00')).astimezone(l.TZ)
        b=datetime.fromisoformat(end['dateTime'].replace('Z','+00:00')).astimezone(l.TZ)
        return a.strftime('%Y/%m/%d')+'（'+'一二三四五六日'[a.weekday()]+'） '+a.strftime('%H:%M')+'～'+b.strftime('%H:%M')
    return start.get('date','日期未提供')+' 全天'

def card(title,lines,confirm=False,events=None):
    from linebot.v3.messaging import FlexMessage,FlexContainer,QuickReply,QuickReplyItem,MessageAction
    def text(value,bold=False): return {'type':'text','text':value,'size':'md' if bold else 'sm','weight':'bold' if bold else 'regular','color':'#172B2A','wrap':True}
    def btn(label,command): return {'type':'button','style':'secondary','height':'sm','action':{'type':'message','label':label,'text':command}}
    rows=[text(x) for x in lines]
    for e in events or []:
        inner=[text(e.get('summary','未命名行程'),True),text(event_time(e))]
        if e.get('local_id'): inner.append(btn('改期這筆行程','改期行程 '+str(e['local_id'])))
        rows.append({'type':'box','layout':'vertical','spacing':'sm','paddingAll':'12px','backgroundColor':l.category_style(e.get('summary',''))[1],'cornerRadius':'10px','contents':inner})
    choices=[('確認行程','確認行程'),('放棄行程','放棄行程')] if confirm else [('今日總覽','今天有哪些事'),('生活助理','生活助理')]
    bubble={'type':'bubble','header':{'type':'box','layout':'vertical','paddingAll':'20px','contents':[text('MR 個人助理',True),text(title,True)]},
        'body':{'type':'box','layout':'vertical','spacing':'md','paddingAll':'16px','contents':rows or [text('近期沒有行程。')]},
        'footer':{'type':'box','layout':'vertical','spacing':'sm','contents':[btn(a,b) for a,b in choices]}}
    return FlexMessage(alt_text=title,contents=FlexContainer.from_dict(bubble))

def handle(user_id,text,event_id=None,source_type='user'):
    text=text.strip()
    automatic=bool(re.search(TIME_PATTERN+r'\s*(?:到|至|～|~|－|-)\s*'+TIME_PATTERN,text))
    if not text.startswith(COMMANDS):
        if not automatic or source_type!='user' or user_id!=config()[2]: return None
        text='行程 '+text
    if source_type!='user': return card('私人日曆',['請在一對一聊天室使用。'])
    _,cal,approved=config()
    if not approved or user_id!=approved: return card('Google日曆尚未啟用',['目前只開放建置者的測試帳號。'])
    try:
        if text=='新增行程': return card('新增Google行程',['請傳送：行程 明天下午2點到下午3點 美容預約','請提供日期、開始與結束時間；確認後才寫入Google日曆。'])
        if text=='放棄行程':
            l.gateway('calendar_discard',user_id,event_id)
            return card('已放棄行程草稿',['這次沒有寫入Google日曆。'])
        if text in ('Google日曆','其他天的行程'):
            now=l.clock()
            if text=='其他天的行程': now=(now+timedelta(days=1)).replace(hour=0,minute=0,second=0,microsecond=0)
            result=call('GET',params={'timeMin':now.replace(hour=0,minute=0,second=0,microsecond=0).isoformat(),'timeMax':(now+timedelta(days=7)).isoformat(),'singleEvents':'true','orderBy':'startTime','maxResults':10})
            owned={e['event_id']:e['id'] for e in l.gateway('calendar_events',user_id)['events'] if e['calendar_id']==cal}
            events=[{**e,'local_id':owned.get(e['id'])} for e in result.get('items',[]) if e.get('status')!='cancelled']
            lines=['台北時間｜'+('明天起七天的行程。' if text=='其他天的行程' else '今天起七天的行程。')]
            if result.get('nextPageToken'): lines.append('行程較多，這張卡片只列前10筆。')
            return card('Google日曆',lines,events=events)
        if text=='確認行程':
            draft=l.gateway('calendar_get_draft',user_id)['draft']
            if not draft: return card('沒有行程草稿',['請重新交代行程日期與時間。'])
            if draft['calendar_id']!=cal: raise CalendarError('calendar_changed')
            key=draft['event_id'];payload=draft['event']
            if draft['operation']=='create':
                try: event=call('POST',body={**payload,'id':key},params={'sendUpdates':'none'})
                except CalendarError as exc:
                    if exc.reason not in ('duplicate','409'): raise
                    event=call('GET','/'+quote(key,safe=''))
            else:
                current=call('GET','/'+quote(key,safe=''))
                if current.get('start')==payload['start'] and current.get('end')==payload['end']: event=current
                else:
                    event=call('PATCH','/'+quote(key,safe=''),body={'start':payload['start'],'end':payload['end']},params={'sendUpdates':'none'},etag=draft['etag'])
            try: saved=l.gateway('calendar_save',user_id,calendar_id=cal,event_id=key,title=event.get('summary',payload['summary']))
            except l.StorageError: return card('Google已更新',['Google已完成這次寫入，但小幫手未完成索引存檔。請再按「確認行程」重試，不會新增第二筆。'],confirm=True)
            return card('Google行程已更新',['編號 '+str(saved['event']['id']),event.get('summary',payload['summary']),event_time(event)])
        update=re.fullmatch(r'改期行程 (\d+)(?:\s+(.+))?',text)
        if update and not update.group(2): return card('請交代新的時間',[f'例如：改期行程 {update.group(1)} 明天下午3點到下午4點'])
        if text.startswith('行程 ') or update:
            value=text.removeprefix('行程 ') if not update else update.group(2)
            title,start,end=parse_range(value,title_required=not update)
            key=hashlib.sha256((user_id+str(event_id or os.urandom(16).hex())).encode()).hexdigest()
            draft={'calendar_id':cal,'event_id':key,'operation':'create'}
            if update:
                owned=l.gateway('calendar_event',user_id,id=int(update.group(1)))['event']
                if not owned or owned['calendar_id']!=cal: raise l.InputError('只能改期自己透過小幫手建立的行程。')
                current=call('GET','/'+quote(owned['event_id'],safe=''))
                if current.get('recurrence') or current.get('recurringEventId'): raise l.InputError('這版先不更動重複行程。')
                title=current.get('summary',owned['title']);draft.update(event_id=owned['event_id'],operation='update',etag=current['etag'])
            event={'summary':title,'start':{'dateTime':start.isoformat(),'timeZone':'Asia/Taipei'},'end':{'dateTime':end.isoformat(),'timeZone':'Asia/Taipei'}}
            group,_=l.category_style(title)
            if group!='其他': event['colorId']={'美容':'9','新客':'3','商會':'6'}[group]
            draft['event']=event
            l.gateway('calendar_draft',user_id,event_id,payload=draft)
            return card('確認Google行程',[title,event_time(event),'日曆：Life OS 測試','尚未寫入。請確認日期與時間後按「確認行程」。'],confirm=True)
        return card('行程指令',['請點新增行程或查日曆。'])
    except l.InputError as exc: return card('請補充行程資料',[str(exc)])
    except l.StorageError: return card('行程存檔未確認',['小幫手目前無法讀寫草稿，請稍後再試。'])
    except CalendarError as exc:
        message='請確認測試日曆已共用給小幫手服務帳號，並開啟Google Calendar API。'
        if exc.reason in ('conditionNotMet','412'): message='這筆行程在確認前已被更改，這次沒有覆蓋。請重新交代改期。'
        return card('Google日曆尚未完成連接',[message,'狀態：'+exc.reason])

def today_events(user_id,now,group=None):
    if not user_id or user_id!=config()[2]: return None,None
    try:
        start=now.replace(hour=0,minute=0,second=0,microsecond=0)
        result=call('GET',params={'timeMin':start.isoformat(),'timeMax':(start+timedelta(days=7 if group else 1)).isoformat(),'singleEvents':'true','orderBy':'startTime','maxResults':100 if group else 8})
        events=[e for e in result.get('items',[]) if e.get('status')!='cancelled']
        if group: events=[e for e in events if l.category_style(e.get('summary',''))[0] in (('美容','新客') if group=='美容' else ('商會',))]
        return events[:8],('行程較多，只列前8筆；完整內容請查Google日曆。' if result.get('nextPageToken') or len(events)>8 else None)
    except CalendarError:
        return [],'目前無法讀取Google行程，請稍後查詢；待辦仍正常顯示。'

def install_routes(app):
    @app.post('/lifeos/calendar-status')
    def calendar_status():
        from flask import request
        secret=os.getenv('LIFEOS_CRON_KEY','')
        if not secret or not hmac.compare_digest(request.headers.get('Authorization',''),'Bearer '+secret): return {'error':'unauthorized'},401
        info,cal,uid=config();result={'service_account_email':info.get('client_email'),'project_id':info.get('project_id'),'calendar_configured':bool(cal),'user_configured':bool(uid)}
        try: call('GET',params={'maxResults':1});result['status']='read_ready'
        except CalendarError as exc: result['status']=exc.reason
        return result
