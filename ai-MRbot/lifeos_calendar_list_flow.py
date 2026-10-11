"""Editable, user-scoped calendar review cards. Batch writes require explicit confirmation."""
import secrets
import time
try:
    from lifeos_settings import tenant_id
except ImportError:
    def tenant_id():return 'mr'
from linebot.v3.messaging import FlexMessage, FlexContainer
from lifeos_calendar_list import review_list

_PENDING = {}
PREFIXES = ('清單補齊 ', '清單當天 ', '清單進度 ', '清單匯入 ', '清單放棄 ', '清單修改 ', '清單全天 ', '清單移除 ', '清單分頁 ', '清單總覽', '停止清單修改')
EXIT = ('查資料', '生活助理', '個人助理', '電子名片', '離開助理', '回到小幫手')

def is_editing(uid):
    pending = _PENDING.get((tenant_id(),uid))
    if pending and pending['until'] > time.monotonic():
        return True
    _PENDING.pop((tenant_id(),uid), None)
    return False

def claims(uid, text):
    if text in EXIT:
        _PENDING.pop((tenant_id(),uid),None)
        return False
    from datetime import datetime
    from zoneinfo import ZoneInfo
    dated_list='\n' in text and review_list(text,datetime.now(ZoneInfo('Asia/Taipei')).year) is not None
    return dated_list or text.startswith(PREFIXES) or (is_editing(uid) and text not in EXIT)

def button(label, text):
    return {'type':'button','height':'sm','action':{'type':'message','label':label,'text':text}}

def day_groups(entries):
    groups={}
    for idx,e in enumerate(entries):groups.setdefault(e['date'],[]).append((idx,e))
    return sorted(groups.items())

def cards(draft, page=0):
    review=draft['review'];entries=review['entries'];token=draft['review_id']
    days=day_groups(entries);pages=max(1,(len(days)+7)//8);page=max(0,min(page,pages-1))
    def txt(s,size='sm',color='#333333'):
        return {'type':'text','text':s or '—','size':size,'color':color,'wrap':True}
    def bubble(body,buttons=None):
        result={'type':'bubble','size':'mega','body':{'type':'box','layout':'vertical','spacing':'md','contents':body}}
        if buttons:result['footer']={'type':'box','layout':'vertical','contents':buttons}
        return result
    ready=sum(e['kind'] in ('complete','all_day') and not any(e.get(k) for k in ('incomplete','date_problem','needs_name','imported')) for e in entries)
    intro=[txt('辨識完成｜行程清單','xl'),txt(f'可加入 {ready} 筆，其餘項目請查看狀態'),txt(f"共 {len(entries)} 筆 · {len(days)} 天 · 第 {page+1}/{pages} 頁"),txt('一天一張卡，左右滑動查看。完整項目按確認加入日曆；缺資料保留待補。未標年份依今年整理。')]
    if review.get('errors'):intro.append(txt('\n'.join(review['errors']),'sm','#B3261E'))
    nav=[]
    if page:nav.append(button('上一頁',f'清單分頁 {token} {page-1}'))
    if page+1<pages:nav.append(button('下一頁',f'清單分頁 {token} {page+1}'))
    nav += [button('先加入完整項目','清單匯入 '+token),button('補齊資料','清單補齊 '+token),button('放棄匯入','清單放棄 '+token)]
    bubbles=[bubble(intro,nav)]
    from datetime import date
    for day,items in days[page*8:(page+1)*8]:
        try:weekday='一二三四五六日'[date.fromisoformat(day).weekday()]
        except ValueError:weekday='日期待補'
        body=[txt(day+'（'+weekday+'）','xl'),txt(str(len(items))+' 筆行程')]
        for idx,e in items:
            if len(body)>2:body.append({'type':'separator'})
            status={'all_day':'全天候選','complete':'待確認','start_only':'缺結束時間','needs_time':'待補時間'}[e['kind']]
            if e.get('imported'):status='已加入日曆'
            elif e.get('date_problem'):status='日期待確認'
            elif e.get('incomplete'):status='待補完整內容'
            body.extend([txt(f"{idx+1} · {e['title']}",'md'),txt(status,'xs','#B3261E')])
            if not e.get('imported'):
                actions=[button('修改',f'清單修改 {token} {idx}'),button('全天',f'清單全天 {token} {idx}'),button('移除',f'清單移除 {token} {idx}')]
                body.append({'type':'box','layout':'horizontal','contents':actions})
        bubbles.append(bubble(body))
    return FlexMessage(alt_text=f'行程清單：{len(entries)}筆、{len(days)}天，請按日期查看',contents=FlexContainer.from_dict({'type':'carousel','contents':bubbles}))

def handle(c,uid,text,event_id,source_type):
    review=review_list(text,c.l.clock().year) if not is_editing(uid) else None
    if text in EXIT:
        _PENDING.pop((tenant_id(),uid),None)
        return None
    if review is None and not claims(uid,text):return None
    if source_type!='user':return c.card('私人日曆',['請在一對一聊天室使用。'])
    if not c.calendar_access(uid):return c.card('Google日曆尚未啟用',['請先使用管理者提供的啟用碼加入Life OS。'])
    try:
        cal=c.config()[1]
        from lifeos_calendar_batch import _RUNNING,_LOCK,progress
        with _LOCK:busy=any(k[0]==cal and k[1]==uid for k in _RUNNING)
        if busy:
            active=c.l.gateway('calendar_get_draft',uid).get('draft')
            if active:return progress(c,uid,active)
        if review is not None:
            draft={'operation':'list_review','calendar_id':cal,'review_id':secrets.token_hex(8),'review':review}
            c.l.gateway('calendar_draft',uid,event_id,payload=draft)
            _PENDING.pop((tenant_id(),uid),None)
            return cards(draft)
        draft=c.l.gateway('calendar_get_draft',uid).get('draft')
        if not draft or draft.get('operation')!='list_review' or draft.get('calendar_id')!=cal:
            _PENDING.pop((tenant_id(),uid),None)
            return c.card('清單草稿已失效',['請重新貼上行程清單。'])
        if text.startswith(('清單補齊 ','清單當天 ')):
            if text.split()[-1]!=draft['review_id']:return c.card('這張卡片已更新',['請使用最新清單。'])
            from lifeos_calendar_day_fill import start
            return start(c,uid,draft,_PENDING,tenant_id(),event_id,advance=text.startswith('清單當天 '))
        if text.startswith('清單進度 '):
            if text.split()[-1]!=draft['review_id']:return c.card('這張卡片已更新',['請使用最新清單。'])
            from lifeos_calendar_batch import progress
            return progress(c,uid,draft)
        if text.startswith(('清單匯入 ','清單放棄 ')):
            if text.split()[-1]!=draft['review_id']:
                return c.card('這張卡片已更新',['請使用最新清單。'],choices=[('查看最新清單','清單總覽')])
            _PENDING.pop((tenant_id(),uid),None)
            if text.startswith('清單放棄 '):
                draft['operation']='list_cancelled';c.l.gateway('calendar_draft',uid,event_id,payload=draft)
                return c.card('已放棄匯入',['不再新增這份清單；先前已匯入的行程保留。'])
            from lifeos_calendar_batch import start_import
            return start_import(c,uid,draft,event_id)
        if text=='停止清單修改':
            _PENDING.pop((tenant_id(),uid),None);return cards(draft)
        if text=='清單總覽':return cards(draft)
        parts=text.split()
        command=parts[0] if parts else ''
        if command in ('清單修改','清單全天','清單移除','清單分頁'):
            if len(parts)!=3 or parts[1]!=draft['review_id'] or not parts[2].isdigit():
                return c.card('這張卡片已更新',['請使用最新清單上的按鈕。'],choices=[('查看最新清單','清單總覽')])
            idx=int(parts[2])
            if command=='清單分頁':return cards(draft,idx)
            if idx>=len(draft['review']['entries']):return c.card('找不到這筆',['請查看最新清單。'])
            if draft['review']['entries'][idx].get('write_started'):
                return c.card('這筆已加入日曆',['請透過改期或取消行程操作。'])
            if command=='清單修改':
                if len(_PENDING)>=1000:_PENDING.clear()
                _PENDING[(tenant_id(),uid)]={'token':draft['review_id'],'index':idx,'until':time.monotonic()+600}
                e=draft['review']['entries'][idx]
                return c.card('修改第 '+str(idx+1)+' 筆',[e['date']+' '+e['title'],'直接回覆完整的新內容，例如：18:00～21:00 吳佳蓉 B。','改日期請分兩行：2026/10/14，再填行程內容。'],choices=[('取消修改','停止清單修改')])
            _PENDING.pop((tenant_id(),uid),None)
            draft.pop('fill_day',None)
            if command=='清單移除':draft['review']['entries'].pop(idx)
            else:
                old=draft['review']['entries'][idx]
                import re
                title=re.sub(r'\d{1,2}[:：]\d{2}\s*(?:到|至|～|~|－|-|–|—)?\s*','',old['title'])
                draft['review']['entries'][idx]=review_list(old['date']+'\n全天 '+title,c.l.clock().year)['entries'][0]
        else:
            pending=_PENDING.get((tenant_id(),uid))
            if not pending or pending['token']!=draft['review_id']:
                _PENDING.pop((tenant_id(),uid),None)
                return c.card('修改已失效',['請重新按這筆行程的修改按鈕。'])
            if pending.get('day_fill'):
                from lifeos_calendar_day_fill import apply
                return apply(c,uid,draft,text,_PENDING,tenant_id(),event_id)
            idx=pending['index'];old=draft['review']['entries'][idx]
            if pending.get('guided'):
                from lifeos_calendar_fill import fill_entry
                text=fill_entry(c,old,text)
                if text is None:return c.card('資料仍需補齊',['請依提示提供日期、時間或完整名稱。'],choices=[('停止補資料','停止清單修改')])
            replacement=review_list(text,c.l.clock().year)
            if replacement is None:replacement=review_list(old['date']+'\n'+text,c.l.clock().year)
            if not replacement or replacement['errors'] or len(replacement['entries'])!=1:
                return c.card('請只修改一筆',['請回覆完整行程內容；改日期請把日期放在第一行。'],choices=[('取消修改','停止清單修改')])
            draft['review']['entries'][idx]=replacement['entries'][0]
            draft.pop('fill_day',None)
            _PENDING.pop((tenant_id(),uid),None)
        if draft['review'].get('version')==2:
            draft['review']['errors']=[e['date']+' '+e['title']+'：日期待確認' for e in draft['review']['entries'] if e.get('date_problem')]
        for entry in draft['review']['entries']:
            if not entry.get('write_started'):entry.pop('google_id',None)
        draft['review_id']=secrets.token_hex(8)
        c.l.gateway('calendar_draft',uid,event_id,payload=draft)
        if command not in ('清單修改','清單全天','清單移除','清單分頁') and pending.get('guided'):
            from lifeos_calendar_fill import ask_next
            return ask_next(c,uid,draft,_PENDING,tenant_id(),prefix='已更新這一筆。')
        return cards(draft,next((i//8 for i,(day,items) in enumerate(day_groups(draft['review']['entries'])) if any(n==min(idx,len(draft['review']['entries'])-1) for n,e in items)),0))
    except (c.l.StorageError,c.CalendarError):
        return c.card('清單暫時無法讀取或儲存',['請稍後重試；沒有加入 Google 日曆。'])
