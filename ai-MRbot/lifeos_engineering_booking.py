"""Four-field engineering bookings; reuse persisted calendar confirmation."""
import hashlib
import re
import time
from datetime import timedelta
import lifeos as l
import lifeos_engineering as ui
from lifeos_settings import tenant_id

FIELDS=('日期','案場名稱','預約工程','地點')
_PARTIAL={}

def prompt(lines=None):
    return ui.card('新增工程預約',lines or ['照以下範例，一次傳送四項：','日期：10/30 下午2點到3點\n案場名稱：林小姐廚房\n預約工程：場勘\n地點：台中市北屯區○○路','只填日期會記為全天；填時間請提供開始與結束。'],[('取消','取消工程預約')])

def fields(text):
    hits=list(re.finditer(r'(?:^|[\n，,])\s*(日期|案場名稱|預約工程|地點)\s*[：:]\s*',text))
    if hits:
        result={}
        for i,h in enumerate(hits):
            key=h[1]
            if key in result:raise l.InputError('同一欄位請只提供一次：'+key)
            result[key]=text[h.end():hits[i+1].start() if i+1<len(hits) else len(text)].strip()
        return result
    m=re.fullmatch(r'(.+?)[，,]\s*(.+?)(場勘|施工|驗收|會議)[，,]\s*地點[：:]?\s*(.+)',text)
    return dict(zip(FIELDS,m.groups())) if m else None

def handle(c,uid,text,eid,source):
    key=(tenant_id(),uid)
    for k,p in list(_PARTIAL.items()):
        if p['until']<time.monotonic():_PARTIAL.pop(k,None)
    if text in ('生活助理','工程秘書','案件總覽','回報進度','今天','新增案件','工程更多'):
        _PARTIAL.pop(key,None);return None
    incoming=fields(text)
    if text not in ('新增工程預約','取消工程預約') and incoming is None and key not in _PARTIAL:return None
    if source!='user':return ui.card('請使用私人聊天室',['請在一對一聊天室建立工程預約。'])
    if not c.calendar_access(uid):return ui.card('尚未綁定',['請先使用管理者提供的啟用碼。'])
    if text=='取消工程預約':
        _PARTIAL.pop(key,None);return ui.card('已取消',['沒有新增工程預約。'])
    if text=='新增工程預約':
        _PARTIAL.pop(key,None);return prompt()
    try:
        prior=_PARTIAL.get(key,{}).get('fields',{})
        if incoming is None:
            missing=[f for f in FIELDS if not prior.get(f)]
            if len(missing)==1:incoming={missing[0]:text.strip()}
            else:return prompt(['請補上：'+'、'.join(missing),'可一次傳送以上欄位，欄位名稱後加冒號。'])
        data={**prior,**incoming}
        _PARTIAL[key]={'fields':data,'until':time.monotonic()+1200}
        missing=[f for f in FIELDS if not data.get(f)]
        if missing:return prompt(['請補上：'+'、'.join(missing)]+[f+'：'+dict(zip(FIELDS,('10/30 下午2點到3點','林小姐廚房','場勘','台中市北屯區○○路')))[f] for f in missing]+['其餘資料已暫存。'])
        if len(data['案場名稱'])>80 or len(data['地點'])>200 or len(data['預約工程'])>100:raise l.InputError('案場名稱最多80字、地點200字、預約工程100字。')
        when=data['日期'];times=list(re.finditer(c.TIME_PATTERN,when))
        if times:
            # Inherit 下午/上午 when the user writes 下午2點到3點.
            if len(times)==2 and times[0][1] and not times[1][1]:
                when=when[:times[1].start()]+times[0][1]+when[times[1].start():]
            _,start,end=c.parse_range(when,title_required=False)
            event={'start':{'dateTime':start.isoformat(),'timeZone':'Asia/Taipei'},'end':{'dateTime':end.isoformat(),'timeZone':'Asia/Taipei'}}
        else:
            start,spans=l.parse_date(when)
            rest=''.join(ch for i,ch in enumerate(when) if not any(a<=i<b for a,b in spans)).strip(' 全天整日，。')
            if not start or rest:raise l.InputError('日期請填如「10/30」或「10/30 下午2點到3點」。')
            event={'start':{'date':start.date().isoformat()},'end':{'date':(start.date()+timedelta(days=1)).isoformat()}}
        event.update(summary=data['案場名稱']+'｜'+data['預約工程'],location=data['地點'])
        draft={'calendar_id':c.config()[1],'event_id':hashlib.sha256((tenant_id()+uid+str(eid or time.time_ns())).encode()).hexdigest(),
               'operation':'create','event':event,'engineering_booking':data}
        work=data['預約工程'];group=next((k for k in ('場勘','施工','驗收','會議') if k in work),None)
        if group:c.set_category(draft,group)
        else:draft['category']='其他'
        l.gateway('calendar_draft',uid,eid,payload=draft)
        _PARTIAL.pop(key,None)
        return c.preview(draft,uid)
    except l.InputError as exc:return prompt([str(exc)])

def ensure_case(uid,draft):
    data=draft.get('engineering_booking')
    if not data:return
    found=[x for x in ui.cases(uid) if x['name']==data['案場名稱']]
    if found:return
    result=l.gateway('engineering_create',uid,'booking-case:'+draft['event_id'],name=data['案場名稱'],location=data['地點'],scope=data['預約工程'])
    if result.get('error') not in (None,'duplicate_case'):raise l.StorageError('Case creation not confirmed')
