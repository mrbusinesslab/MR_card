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
COMMANDS=('其他天的行程','Google日曆','新增行程','行程 ','確認行程','仍要新增行程','放棄行程','改期行程','分類行程 ','詳情行程 ','選擇預約 ','確認取消行程')

class CalendarError(Exception):
    def __init__(self,reason): self.reason=reason

def config():
    try: info=json.loads(os.getenv('GOOGLE_SERVICE_ACCOUNT_JSON','{}'))
    except ValueError: info={}
    return info,os.getenv('LIFEOS_GOOGLE_CALENDAR_ID',''),os.getenv('LIFEOS_GOOGLE_USER_ID','')

def calendar_access(user_id):
    approved=config()[2]
    if not approved or not user_id: return False
    if user_id==approved: return True
    try:
        user=l.gateway('get_user',user_id).get('user')
        return isinstance(user,dict) and user.get('shared_owner')==approved
    except l.StorageError:
        return False

def actor_metadata(event,user_id,creating=False):
    extended=event.get('extendedProperties',{})
    private={**extended.get('private',{})}
    if creating: private.setdefault('lifeos_created_by',user_id)
    private['lifeos_modified_by']=user_id
    return {**extended,'private':private}

def visible_events(user_id,events):
    user=l.gateway('get_user',user_id).get('user')
    if isinstance(user,dict) and user.get('calendar_shared') is False:
        allowed={e['event_id'] for e in l.gateway('calendar_events',user_id)['events'] if e['calendar_id']==config()[1]}
        return [e for e in events if e.get('id') in allowed]
    return events

def call(method,path='',body=None,params=None,etag=None,calendar_metadata=False):
    info,cal,_=config()
    if not info.get('client_email') or not cal: raise CalendarError('not_configured')
    if body and body.get('eventLabelId'):
        params={**(params or {}),'eventLabelVersion':1}
    try:
        creds=service_account.Credentials.from_service_account_info(info,scopes=['https://www.googleapis.com/auth/calendar.events','https://www.googleapis.com/auth/calendar.calendars.readonly'])
        with AuthorizedSession(creds,refresh_timeout=10) as session:
            response=session.request(method,'https://www.googleapis.com/calendar/v3/calendars/'+quote(cal,safe='')+('' if calendar_metadata else '/events'+path),
                json=body,params=params,headers={'If-Match':etag} if etag else {},timeout=12)
        if response.status_code>=400:
            reason=str(response.status_code)
            try: reason=response.json()['error'].get('errors',[{}])[0].get('reason',reason)
            except (ValueError,KeyError,IndexError): pass
            raise CalendarError(reason)
        return response.json()
    except CalendarError: raise
    except Exception as exc: raise CalendarError('connection_failed') from exc

def event_labels():
    metadata=call('GET',calendar_metadata=True)
    return metadata.get('labelProperties',{}).get('eventLabels',[])

def apply_label(payload,group):
    names={'美容':'美容美體','新客':'新客'}
    if group not in names: return payload
    labels=event_labels()
    match=next((x for x in labels if x.get('name')==names[group]),None)
    if not match: return payload
    result=dict(payload)
    result.pop('colorId',None)
    result['eventLabelId']=match['id']
    return result

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

def parse_booking(text,now=None):
    now=now or l.clock()
    times=list(re.finditer(TIME_PATTERN,text))
    if len(times)!=1: return parse_range(text,now)
    start,spans=l.parse_date(text,now)
    if start is None: raise l.InputError('請補上預約日期。')
    title=''.join(ch for i,ch in enumerate(text) if not any(a<=i<b for a,b in spans)).strip(' ，,。')
    if l.category_style(title)[0] not in ('美容','新客') or re.search(r'每(?:天|日|週|星期|月|年)',text):
        raise l.InputError('美容美體可只提供開始時間；F或B預設90分鐘、F+B預設180分鐘。其他行程請提供起訖時間。')
    if not title or len(title)>500: raise l.InputError('請提供預約名稱。')
    normalized=l.beauty_title(title)
    minutes=180 if re.search(r'F\s*\+\s*B',normalized,re.I) else 90
    return title,start,start+timedelta(minutes=minutes)

def day_bookings(event,exclude_id=None):
    from datetime import datetime
    start=datetime.fromisoformat(event['start']['dateTime']).astimezone(l.TZ)
    end=datetime.fromisoformat(event['end']['dateTime']).astimezone(l.TZ)
    day=start.replace(hour=0,minute=0,second=0,microsecond=0)
    until=(end+timedelta(days=1)).replace(hour=0,minute=0,second=0,microsecond=0)
    if end.date()==start.date(): until=day+timedelta(days=1)
    params={'timeMin':day.isoformat(),'timeMax':until.isoformat(),'singleEvents':'true','orderBy':'startTime','maxResults':250}
    events=[]
    for _ in range(10):
        result=call('GET',params=params)
        events.extend(e for e in result.get('items',[]) if e.get('status')!='cancelled' and e.get('id')!=exclude_id)
        token=result.get('nextPageToken')
        if not token: break
        params={**params,'pageToken':token}
    else: raise CalendarError('conflict_check_incomplete')
    conflicts=[]
    for e in events:
        a=e.get('start',{});b=e.get('end',{})
        if a.get('dateTime') and b.get('dateTime'):
            left=datetime.fromisoformat(a['dateTime'].replace('Z','+00:00')).astimezone(l.TZ)
            right=datetime.fromisoformat(b['dateTime'].replace('Z','+00:00')).astimezone(l.TZ)
        elif a.get('date') and b.get('date'):
            left=datetime.fromisoformat(a['date']).replace(tzinfo=l.TZ)
            right=datetime.fromisoformat(b['date']).replace(tzinfo=l.TZ)
        else: raise CalendarError('conflict_check_incomplete')
        if left<end and right>start: conflicts.append(e)
    return events,conflicts

def conflict_key(conflicts):
    return hashlib.sha256(json.dumps([{'id':e.get('id'),'start':e.get('start'),'end':e.get('end'),'title':e.get('summary'),'etag':e.get('etag')} for e in conflicts],sort_keys=True).encode()).hexdigest()

def instant(value):
    from datetime import datetime
    return datetime.fromisoformat(value.replace('Z','+00:00'))

def duplicate_event(event,events):
    title=re.sub(r'\s+','',event.get('summary','')).casefold()
    return next((e for e in events if re.sub(r'\s+','',e.get('summary','')).casefold()==title and e.get('start',{}).get('dateTime') and instant(e['start']['dateTime'])==instant(event['start']['dateTime'])),None)

def named_candidates(name,user_id):
    _,cal,_=config()
    owned={e['event_id']:e['id'] for e in l.gateway('calendar_events',user_id)['events'] if e['calendar_id']==cal}
    now=l.clock()
    params={'timeMin':now.isoformat(),'timeMax':(now+timedelta(days=366)).isoformat(),'singleEvents':'true','orderBy':'startTime','maxResults':250,'q':name}
    matches=[]
    for _ in range(10):
        result=call('GET',params=params)
        for event in result.get('items',[]):
            title=event.get('summary','')
            if event.get('status')=='cancelled' or event.get('id') not in owned: continue
            if not re.match(re.escape(name)+r'(?:\s|$|[（(])',title,re.I): continue
            if not event.get('start',{}).get('dateTime'): continue
            if instant(event['start']['dateTime'])<now: continue
            matches.append({**event,'local_id':owned[event['id']]})
        token=result.get('nextPageToken')
        if not token: return matches
        params={**params,'pageToken':token}
    raise CalendarError('conflict_check_incomplete')

def prepare_named(user_id,event_id,chosen,operation,when=None):
    from datetime import datetime
    _,cal,_=config()
    current=call('GET','/'+quote(chosen['id'],safe=''))
    if current.get('status')=='cancelled': return card('預約已取消',[current.get('summary','')])
    if current.get('recurrence') or current.get('recurringEventId'): raise l.InputError('這版先不更動重複行程。')
    if instant(current['start']['dateTime'])<l.clock(): raise l.InputError('這筆預約已開始，請確認Google日曆。')
    draft={'calendar_id':cal,'event_id':chosen['id'],'operation':operation,'etag':current['etag'],'original':{'summary':current['summary'],'start':current['start'],'end':current['end']}}
    if operation=='cancel':
        draft['event']=draft['original']
        l.gateway('calendar_draft',user_id,event_id,payload=draft)
        return card('確認取消預約',[current['summary'],event_time(current),'確定取消這筆預約？'],choices=[('確定取消','確認取消行程'),('保留預約','放棄行程')])
    times=list(re.finditer(TIME_PATTERN,when or ''))
    if len(times)==1:
        start,_=l.parse_date(when)
        if start is None: raise l.InputError('請提供日期與開始時間。')
        end=start+(instant(current['end']['dateTime'])-instant(current['start']['dateTime']))
    else: _,start,end=parse_range(when,title_required=False)
    draft['event']={'summary':current['summary'],'start':{'dateTime':start.isoformat(),'timeZone':'Asia/Taipei'},'end':{'dateTime':end.isoformat(),'timeZone':'Asia/Taipei'}}
    l.gateway('calendar_draft',user_id,event_id,payload=draft)
    return preview(draft,user_id)

def preview(draft,user_id,event_id=None):
    events,conflicts=day_bookings(draft['event'],draft.get('event_id'))
    duplicate=duplicate_event(draft['event'],events) if draft.get('operation')=='create' else None
    if duplicate: return card('這筆預約已經建立',[duplicate.get('summary',''),event_time(duplicate),'沒有重複新增。'])
    if conflicts:
        draft['conflict_key']=conflict_key(conflicts)
        l.gateway('calendar_draft',user_id,event_id,payload=draft)
        lines=['準備新增：'+draft['event']['summary'],event_time(draft['event']),'以下標示「重疊」的預約有時間衝突。仍要新增嗎？']
        ids={e['id'] for e in conflicts}
        displayed=[{**e,'summary':('重疊｜' if e['id'] in ids else '')+e.get('summary','未命名行程')} for e in events[:12]]
        if len(events)>12: lines.append('當天行程較多，下方列前12筆；所有重疊行程：'+ '、'.join(e.get('summary','未命名')+' '+event_time(e) for e in conflicts))
        return card('預約時間重疊',lines,events=displayed,choices=[('仍要改期' if draft.get('operation')=='update' else '仍要新增','仍要新增行程'),('放棄','放棄行程')])
    lines=[draft['event']['summary']]
    if draft.get('original'): lines+=['原時間：'+event_time(draft['original']),'新時間：'+event_time(draft['event'])]
    else: lines.append(event_time(draft['event']))
    return card('確認改期' if draft.get('operation')=='update' else '確認Google行程',lines+['尚未更新，請確認。'],confirm=True)

def event_time(event):
    from datetime import datetime
    start=event.get('start',{});end=event.get('end',{})
    if 'dateTime' in start:
        a=datetime.fromisoformat(start['dateTime'].replace('Z','+00:00')).astimezone(l.TZ)
        b=datetime.fromisoformat(end['dateTime'].replace('Z','+00:00')).astimezone(l.TZ)
        return a.strftime('%Y/%m/%d')+'（'+'一二三四五六日'[a.weekday()]+'） '+a.strftime('%H:%M')+'～'+b.strftime('%H:%M')
    return start.get('date','日期未提供')+' 全天'

def event_row(event,show_date=False):
    from datetime import datetime
    title=event.get('summary','未命名行程')
    group=event.get('extendedProperties',{}).get('private',{}).get('lifeos_category')
    ink=l.category_ink(title,group)
    def tx(value,color='#172B2A',size='sm',bold=False):
        return {'type':'text','text':value,'size':size,'color':color,'weight':'bold' if bold else 'regular','wrap':True}
    start=event.get('start',{});end=event.get('end',{})
    if start.get('dateTime'):
        a=datetime.fromisoformat(start['dateTime'].replace('Z','+00:00')).astimezone(l.TZ)
        b=datetime.fromisoformat(end['dateTime'].replace('Z','+00:00')).astimezone(l.TZ)
        times=[tx(a.strftime('%H:%M'),bold=True),tx(b.strftime('%H:%M'),'#94A3B8')]
        date=a.strftime('%m/%d')+'（'+'一二三四五六日'[a.weekday()]+'）'
    else:
        times=[tx('全天',bold=True)];date=start.get('date','日期未提供')
    details=([tx(date,'#64748B','xs')] if show_date else [])+[tx(title,size='md',bold=True)]

    row={'type':'box','layout':'horizontal','spacing':'md','margin':'lg','paddingAll':'4px','contents':[
        {'type':'box','layout':'vertical','width':'54px','spacing':'sm','contents':times},
        {'type':'box','layout':'vertical','width':'3px','height':'52px','backgroundColor':ink,'contents':[]},
        {'type':'box','layout':'vertical','spacing':'sm','flex':1,'contents':details}]}
    if event.get('local_id'): row['action']={'type':'message','label':'查看行程','text':'詳情行程 '+str(event['local_id'])}
    return row

def card(title,lines,confirm=False,events=None,choices=None):
    from linebot.v3.messaging import FlexMessage,FlexContainer,QuickReply,QuickReplyItem,MessageAction
    def text(value,bold=False): return {'type':'text','text':value,'size':'md' if bold else 'sm','weight':'bold' if bold else 'regular','color':'#172B2A','wrap':True}
    def btn(label,command): return {'type':'button','style':'secondary','height':'sm','action':{'type':'message','label':label,'text':command}}
    rows=[text(x) for x in lines]
    for e in events or []:
        rows.append(event_row(e,show_date=True))
    choices=choices or ([('確認行程','確認行程'),('放棄行程','放棄行程')] if confirm else [])
    bubble={'type':'bubble','header':{'type':'box','layout':'vertical','paddingAll':'20px','contents':[text('MR 個人助理',True),text(title,True)]},
        'body':{'type':'box','layout':'vertical','spacing':'md','paddingAll':'16px','contents':rows or [text('近期沒有行程。')]},
        'footer':{'type':'box','layout':'vertical','spacing':'sm','contents':[btn(a,b) for a,b in choices]}}
    if not choices: bubble.pop('footer',None)
    return FlexMessage(alt_text=title,contents=FlexContainer.from_dict(bubble))

def classification_card(draft):
    return card('請選擇排程類型',[draft['event']['summary'],event_time(draft['event']),'這是美容預約還是商會排程？'],
        choices=[('美容預約','分類行程 美容'),('商會排程','分類行程 商會'),('放棄','放棄行程')])

def set_category(draft,group):
    draft.pop('needs_category',None)
    draft['category']=group
    event=draft['event']
    event['colorId']={'美容':'9','新客':'3','商會':'6','交流':'2'}[group]
    event['extendedProperties']={'private':{'lifeos_category':group}}


def handle(user_id,text,event_id=None,source_type='user'):
    text=text.strip()
    name_move=re.fullmatch(r'(.+?)(?:的預約|預約)?(?:改到|改期到)\s*(.+)',text)
    name_cancel=re.fullmatch(r'取消\s*(.+?)(?:的預約|預約)',text)
    automatic=bool(re.search(TIME_PATTERN+r'\s*(?:到|至|～|~|－|-)\s*'+TIME_PATTERN,text))
    single_beauty=len(list(re.finditer(TIME_PATTERN,text)))==1 and bool(re.search(r'做臉|做身體|美容預約|美體預約|(?<![A-Za-z])[FB](?![A-Za-z])',text,re.I)) and not re.search(r'前|截止|準備|提醒|要買',text)
    automatic=automatic or single_beauty
    named=bool(name_move or name_cancel)
    if not text.startswith(COMMANDS):
        if not (automatic or named) or source_type!='user' or not calendar_access(user_id): return None
        if not named: text='行程 '+text
    if source_type!='user': return card('私人日曆',['請在一對一聊天室使用。'])
    _,cal,approved=config()
    if not calendar_access(user_id): return card('Google日曆尚未啟用',['請先使用管理者提供的啟用碼加入Life OS。'])
    try:
        if named:
            name=(name_move or name_cancel).group(1).strip()
            if not name or len(name)>80: raise l.InputError('請提供預約上的姓名。')
            operation='update' if name_move else 'cancel'
            when=name_move.group(2) if name_move else None
            matches=named_candidates(name,user_id)
            if not matches: return card('找不到預約',[name+' 沒有尚未開始、透過小幫手建立的預約。'])
            if len(matches)==1: return prepare_named(user_id,event_id,matches[0],operation,when)
            selection={'calendar_id':cal,'operation':'select','requested_operation':operation,'when':when,'candidates':[{'id':e['id'],'local_id':e['local_id']} for e in matches]}
            l.gateway('calendar_draft',user_id,event_id,payload=selection)
            return card('請選擇要處理的預約',['符合預約較多，目前列前10筆。'] if len(matches)>10 else [],choices=[((e['summary']+' '+event_time(e)[5:])[:40],'選擇預約 '+str(e['local_id'])) for e in matches[:10]]+[('放棄','放棄行程')])
        choice=re.fullmatch(r'選擇預約 (\d+)',text)
        if choice:
            draft=l.gateway('calendar_get_draft',user_id)['draft']
            if not draft or draft.get('operation')!='select' or draft['calendar_id']!=cal: raise l.InputError('選擇已失效，請重新交代姓名與改期或取消。')
            chosen=next((e for e in draft['candidates'] if str(e['local_id'])==choice.group(1)),None)
            if not chosen: raise l.InputError('這筆預約不在目前的選擇清單。')
            return prepare_named(user_id,event_id,chosen,draft['requested_operation'],draft.get('when'))
        if text=='確認取消行程':
            draft=l.gateway('calendar_get_draft',user_id)['draft']
            if not draft or draft.get('operation')!='cancel' or draft['calendar_id']!=cal: raise l.InputError('沒有待確認的取消預約。')
            current=call('GET','/'+quote(draft['event_id'],safe=''))
            if current.get('status')!='cancelled':
                call('PATCH','/'+quote(draft['event_id'],safe=''),body={'status':'cancelled','extendedProperties':actor_metadata(current,user_id)},params={'sendUpdates':'none'},etag=draft['etag'])
            l.gateway('calendar_save',user_id,calendar_id=cal,event_id=draft['event_id'],title=draft['event']['summary'])
            return card('預約已取消',[draft['event']['summary'],event_time(draft['event']),'Google日曆已同步取消。'])
        detail=re.fullmatch(r'詳情行程 (\d+)',text)
        if detail:
            owned=l.gateway('calendar_event',user_id,id=int(detail.group(1)))['event']
            if not owned or owned['calendar_id']!=cal: raise l.InputError('找不到可操作的行程。')
            current=call('GET','/'+quote(owned['event_id'],safe=''))
            return card('行程詳情',[current.get('summary',owned['title']),event_time(current)],choices=[('改期','改期行程 '+detail.group(1))])
        if text=='新增行程': return card('新增Google行程',['請傳送：行程 明天下午2點到下午3點 美容預約','美容美體只需開始時間：F或B預設90分鐘、F+B預設180分鐘；其他行程請提供起訖時間。'])
        if text=='放棄行程':
            l.gateway('calendar_discard',user_id,event_id)
            return card('已放棄行程草稿',['這次沒有寫入Google日曆。'])
        if text in ('Google日曆','其他天的行程'):
            now=l.clock()
            if text=='其他天的行程': now=(now+timedelta(days=1)).replace(hour=0,minute=0,second=0,microsecond=0)
            result=call('GET',params={'timeMin':now.replace(hour=0,minute=0,second=0,microsecond=0).isoformat(),'timeMax':(now+timedelta(days=7)).isoformat(),'singleEvents':'true','orderBy':'startTime','maxResults':10})
            owned={e['event_id']:e['id'] for e in l.gateway('calendar_events',user_id)['events'] if e['calendar_id']==cal}
            events=[{**e,'local_id':owned.get(e['id'])} for e in visible_events(user_id,result.get('items',[])) if e.get('status')!='cancelled']
            lines=['台北時間｜'+('明天起七天的行程。' if text=='其他天的行程' else '今天起七天的行程。')]
            if result.get('nextPageToken'): lines.append('行程較多，這張卡片只列前10筆。')
            return card('Google日曆',lines,events=events)
        if text.startswith('分類行程 '):
            group=text.removeprefix('分類行程 ')
            if group not in ('美容','商會'): raise l.InputError('請使用卡片上的分類按鈕。')
            draft=l.gateway('calendar_get_draft',user_id)['draft']
            if not draft: return card('沒有行程草稿',['請重新交代行程日期與時間。'])
            if draft['calendar_id']!=cal: raise CalendarError('calendar_changed')
            if not draft.get('needs_category'): return card('分類已完成',['請確認目前草稿，或重新交代新的行程。'],confirm=True)
            if group=='美容':
                group='新客' if '新客' in draft['event']['summary'] else '美容'
            elif not re.search(r'建築組|商會|BNI|商務引薦',draft['event']['summary'],re.I): group='交流'
            set_category(draft,group)
            l.gateway('calendar_draft',user_id,event_id,payload=draft)
            return preview(draft,user_id)
        if text in ('確認行程','仍要新增行程'):
            draft=l.gateway('calendar_get_draft',user_id)['draft']
            if not draft: return card('沒有行程草稿',['請重新交代行程日期與時間。'])
            if draft['calendar_id']!=cal: raise CalendarError('calendar_changed')
            if draft.get('operation') not in ('create','update'): raise l.InputError('請使用目前卡片上的確認按鈕。')
            if draft.get('needs_category'): return classification_card(draft)
            existing,conflicts=day_bookings(draft['event'],draft.get('event_id'))
            duplicate=duplicate_event(draft['event'],existing) if draft.get('operation')=='create' else None
            if duplicate: return card('這筆預約已經建立',[duplicate.get('summary',''),event_time(duplicate),'沒有重複新增。'])
            if conflicts and (text!='仍要新增行程' or draft.get('conflict_key')!=conflict_key(conflicts)):
                return preview(draft,user_id)
            key=draft['event_id'];payload=draft['event']
            if draft['operation']=='create':
                payload=apply_label(payload,draft.get('category'))
                try: event=call('POST',body={**payload,'id':key,'extendedProperties':actor_metadata(payload,user_id,creating=True)},params={'sendUpdates':'none'})
                except CalendarError as exc:
                    if exc.reason not in ('duplicate','409'): raise
                    event=call('GET','/'+quote(key,safe=''))
            else:
                current=call('GET','/'+quote(key,safe=''))
                if current.get('start')==payload['start'] and current.get('end')==payload['end']: event=current
                else:
                    event=call('PATCH','/'+quote(key,safe=''),body={'start':payload['start'],'end':payload['end'],'extendedProperties':actor_metadata(current,user_id)},params={'sendUpdates':'none'},etag=draft['etag'])
            try: saved=l.gateway('calendar_save',user_id,calendar_id=cal,event_id=key,title=event.get('summary',payload['summary']))
            except l.StorageError: return card('Google已更新',['Google已完成這次寫入，但小幫手未完成索引存檔。請再按「確認行程」重試，不會新增第二筆。'],confirm=True)
            lines=[event.get('summary',payload['summary'])]
            if draft.get('original'): lines+=['原時間：'+event_time(draft['original']),'新時間：'+event_time(event)]
            else: lines.append(event_time(event))
            return card('改期完成' if draft['operation']=='update' else 'Google行程已更新',lines+['Google日曆已同步更新。'])
        update=re.fullmatch(r'改期行程 (\d+)(?:\s+(.+))?',text)
        if update and not update.group(2): return card('請交代新的時間',[f'例如：改期行程 {update.group(1)} 明天下午3點到下午4點'])
        if text.startswith('行程 ') or update:
            value=text.removeprefix('行程 ') if not update else update.group(2)
            title,start,end=parse_range(value,title_required=False) if update else parse_booking(value)
            if not update: title=l.beauty_title(title)
            key=hashlib.sha256((user_id+str(event_id or os.urandom(16).hex())).encode()).hexdigest()
            draft={'calendar_id':cal,'event_id':key,'operation':'create'}
            if update:
                owned=l.gateway('calendar_event',user_id,id=int(update.group(1)))['event']
                if not owned or owned['calendar_id']!=cal: raise l.InputError('找不到可操作、透過小幫手建立的行程。')
                current=call('GET','/'+quote(owned['event_id'],safe=''))
                if current.get('recurrence') or current.get('recurringEventId'): raise l.InputError('這版先不更動重複行程。')
                title=current.get('summary',owned['title']);draft.update(event_id=owned['event_id'],operation='update',etag=current['etag'],original={'summary':title,'start':current['start'],'end':current['end']})
            event={'summary':title,'start':{'dateTime':start.isoformat(),'timeZone':'Asia/Taipei'},'end':{'dateTime':end.isoformat(),'timeZone':'Asia/Taipei'}}
            group,_=l.category_style(title)
            draft['event']=event
            if not update:
                if group=='其他': draft['needs_category']=True
                else: set_category(draft,group)
            l.gateway('calendar_draft',user_id,event_id,payload=draft)
            if draft.get('needs_category'): return classification_card(draft)
            return preview(draft,user_id)
        return card('行程指令',['請點新增行程或查日曆。'])
    except l.InputError as exc: return card('請補充行程資料',[str(exc)])
    except l.StorageError: return card('行程存檔未確認',['小幫手目前無法讀寫草稿，請稍後再試。'])
    except CalendarError as exc:
        if exc.reason in ('conflict_check_incomplete','connection_failed'): return card('尚未完成重疊檢查',['目前無法確認行程是否重疊，這次沒有新增。請稍後再試。'])
        message='請確認測試日曆已共用給小幫手服務帳號，並開啟Google Calendar API。'
        if exc.reason in ('conditionNotMet','412'): message='這筆行程在確認前已被更改，這次沒有覆蓋。請重新交代改期。'
        return card('Google日曆尚未完成連接',[message,'狀態：'+exc.reason])

def today_events(user_id,now,group=None,period=None):
    if not calendar_access(user_id): return None,None
    try:
        start=now.replace(hour=0,minute=0,second=0,microsecond=0)
        end=start+timedelta(days=7 if group else 1)
        if period: start,end=l.period_bounds(now,period)
        result=call('GET',params={'timeMin':start.isoformat(),'timeMax':end.isoformat(),'singleEvents':'true','orderBy':'startTime','maxResults':100 if group or period in ('week','month') else 8})
        events=[e for e in visible_events(user_id,result.get('items',[])) if e.get('status')!='cancelled']
        if group: events=[e for e in events if l.category_style(e.get('summary',''),e.get('extendedProperties',{}).get('private',{}).get('lifeos_category'))[0] in (('美容','新客') if group=='美容' else ('商會','交流'))]
        owned={e['event_id']:e['id'] for e in l.gateway('calendar_events',user_id)['events'] if e['calendar_id']==config()[1]}
        events=[{**e,'local_id':owned.get(e['id'])} for e in events]
        limit=64 if period in ('week','month') else 8
        return events[:limit],(f'行程較多，只列前{limit}筆；完整內容請查Google日曆。' if result.get('nextPageToken') or len(events)>limit else None)
    except (CalendarError,l.StorageError):
        return [],'目前無法讀取Google行程，請稍後查詢；待辦仍正常顯示。'

def install_routes(app):
    import lifeos_week_image
    lifeos_week_image.install_routes(app)
    @app.post('/lifeos/calendar-label')
    def calendar_label():
        from flask import request
        secret=os.getenv('LIFEOS_CRON_KEY','')
        if not secret or not hmac.compare_digest(request.headers.get('Authorization',''),'Bearer '+secret): return {'error':'unauthorized'},401
        data=request.get_json(silent=True) or {}
        key=data.get('event_id','');expected=data.get('expected_title','')
        if not isinstance(key,str) or not re.fullmatch(r'[0-9a-v]{5,1024}',key) or not expected: return {'error':'invalid_event'},400
        try:
            event=call('GET','/'+quote(key,safe=''),params={'eventLabelVersion':1})
            if event.get('summary')!=expected: return {'error':'title_changed'},409
            group=l.category_style(expected)[0]
            if group not in ('美容','新客'): return {'error':'not_beauty_booking'},400
            payload=apply_label({},group)
            if not payload.get('eventLabelId'): return {'error':'label_missing'},409
            if event.get('eventLabelId')!=payload['eventLabelId']:
                call('PATCH','/'+quote(key,safe=''),body=payload,params={'sendUpdates':'none'},etag=event['etag'])
            verified=call('GET','/'+quote(key,safe=''),params={'eventLabelVersion':1})
            return {'title':verified.get('summary'),'label_id':verified.get('eventLabelId'),'verified':verified.get('eventLabelId')==payload['eventLabelId']}
        except CalendarError as exc: return {'error':exc.reason},502

    @app.post('/lifeos/calendar-status')
    def calendar_status():
        from flask import request
        secret=os.getenv('LIFEOS_CRON_KEY','')
        if not secret or not hmac.compare_digest(request.headers.get('Authorization',''),'Bearer '+secret): return {'error':'unauthorized'},401
        info,cal,uid=config();result={'service_account_email':info.get('client_email'),'project_id':info.get('project_id'),'calendar_configured':bool(cal),'user_configured':bool(uid)}
        try:
            call('GET',params={'maxResults':1});result['status']='read_ready'
            result['labels']=event_labels()
        except CalendarError as exc: result['status']=exc.reason
        return result

