"""Editable, user-scoped calendar review cards. Never writes Google events."""
import secrets
import time
from linebot.v3.messaging import FlexMessage, FlexContainer
from lifeos_calendar_list import review_list

_PENDING = {}
PREFIXES = ('清單修改 ', '清單全天 ', '清單移除 ', '清單分頁 ', '清單總覽', '停止清單修改')
EXIT = ('查資料', '生活助理', '個人助理', '電子名片', '離開助理', '回到小幫手')

def is_editing(uid):
    pending = _PENDING.get(uid)
    if pending and pending['until'] > time.monotonic():
        return True
    _PENDING.pop(uid, None)
    return False

def claims(uid, text):
    if text in EXIT:
        _PENDING.pop(uid,None)
        return False
    return text.startswith(PREFIXES) or (is_editing(uid) and text not in EXIT)

def button(label, text):
    return {'type':'button','height':'sm','action':{'type':'message','label':label,'text':text}}

def cards(draft, page=0):
    review=draft['review']; entries=review['entries']; token=draft['review_id']
    pages=max(1,(len(entries)+7)//8);page=max(0,min(page,pages-1))
    def txt(s,size='sm',color='#333333'):
        return {'type':'text','text':s or '—','size':size,'color':color,'wrap':True}
    def bubble(body, buttons):
        return {'type':'bubble','size':'mega','body':{'type':'box','layout':'vertical','spacing':'md','contents':body},'footer':{'type':'box','layout':'vertical','contents':buttons}}
    notes='\n'.join(review.get('errors',[]))
    intro=[txt('行程清單','xl'),txt(f"共 {len(entries)} 筆 · 第 {page+1}/{pages} 頁"),txt('左右滑動查看每筆行程。\n未標示年份時依今年整理，請核對日期。\n尚未加入 Google 日曆。批次存檔尚未啟用。')]
    if notes:intro.append(txt(notes,'sm','#B3261E'))
    nav=[]
    if page:nav.append(button('上一頁',f'清單分頁 {token} {page-1}'))
    if page+1<pages:nav.append(button('下一頁',f'清單分頁 {token} {page+1}'))
    bubbles=[bubble(intro,nav or [button('重新查看','清單總覽')])]
    for idx in range(page*8,min(len(entries),(page+1)*8)):
        e=entries[idx]
        status={'all_day':'全天候選','complete':'待確認','start_only':'缺結束時間','needs_time':'待補時間'}[e['kind']]
        if e.get('incomplete'):status='待補完整內容'
        body=[txt(f"{idx+1} · {e['date']}",'md'),txt(e['title'],'lg'),txt(status,'md','#B3261E'),txt('；'.join(e['notes']))]
        actions=[button('修改',f'清單修改 {token} {idx}'),button('設為全天',f'清單全天 {token} {idx}'),button('移除這筆',f'清單移除 {token} {idx}')]
        bubbles.append(bubble(body,actions))
    return FlexMessage(alt_text=f'行程清單：{len(entries)}筆，請查看卡片並修改',contents=FlexContainer.from_dict({'type':'carousel','contents':bubbles}))

def handle(c,uid,text,event_id,source_type):
    review=review_list(text,c.l.clock().year) if not is_editing(uid) else None
    if text in EXIT:
        _PENDING.pop(uid,None)
        return None
    if review is None and not claims(uid,text):return None
    if source_type!='user':return c.card('私人日曆',['請在一對一聊天室使用。'])
    if not c.calendar_access(uid):return c.card('Google日曆尚未啟用',['請先使用管理者提供的啟用碼加入Life OS。'])
    try:
        cal=c.config()[1]
        if review is not None:
            draft={'operation':'list_review','calendar_id':cal,'review_id':secrets.token_hex(8),'review':review}
            c.l.gateway('calendar_draft',uid,event_id,payload=draft)
            _PENDING.pop(uid,None)
            return cards(draft)
        draft=c.l.gateway('calendar_get_draft',uid).get('draft')
        if not draft or draft.get('operation')!='list_review' or draft.get('calendar_id')!=cal:
            _PENDING.pop(uid,None)
            return c.card('清單草稿已失效',['請重新貼上行程清單。'])
        if text=='停止清單修改':
            _PENDING.pop(uid,None);return cards(draft)
        if text=='清單總覽':return cards(draft)
        parts=text.split()
        command=parts[0] if parts else ''
        if command in ('清單修改','清單全天','清單移除','清單分頁'):
            if len(parts)!=3 or parts[1]!=draft['review_id'] or not parts[2].isdigit():
                return c.card('這張卡片已更新',['請使用最新清單上的按鈕。'],choices=[('查看最新清單','清單總覽')])
            idx=int(parts[2])
            if command=='清單分頁':return cards(draft,idx)
            if idx>=len(draft['review']['entries']):return c.card('找不到這筆',['請查看最新清單。'])
            if command=='清單修改':
                if len(_PENDING)>=1000:_PENDING.clear()
                _PENDING[uid]={'token':draft['review_id'],'index':idx,'until':time.monotonic()+600}
                e=draft['review']['entries'][idx]
                return c.card('修改第 '+str(idx+1)+' 筆',[e['date']+' '+e['title'],'直接回覆完整的新內容，例如：18:00～21:00 吳佳蓉 B。','改日期請分兩行：2026/10/14，再填行程內容。'],choices=[('取消修改','停止清單修改')])
            _PENDING.pop(uid,None)
            if command=='清單移除':draft['review']['entries'].pop(idx)
            else:
                old=draft['review']['entries'][idx]
                import re
                title=re.sub(r'\d{1,2}[:：]\d{2}\s*(?:到|至|～|~|－|-|–|—)?\s*','',old['title'])
                draft['review']['entries'][idx]=review_list(old['date']+'\n全天 '+title,c.l.clock().year)['entries'][0]
        else:
            pending=_PENDING.get(uid)
            if not pending or pending['token']!=draft['review_id']:
                _PENDING.pop(uid,None)
                return c.card('修改已失效',['請重新按這筆行程的修改按鈕。'])
            idx=pending['index'];old=draft['review']['entries'][idx]
            replacement=review_list(text,c.l.clock().year)
            if replacement is None:replacement=review_list(old['date']+'\n'+text,c.l.clock().year)
            if not replacement or replacement['errors'] or len(replacement['entries'])!=1:
                return c.card('請只修改一筆',['請回覆完整行程內容；改日期請把日期放在第一行。'],choices=[('取消修改','停止清單修改')])
            draft['review']['entries'][idx]=replacement['entries'][0]
            _PENDING.pop(uid,None)
        draft['review_id']=secrets.token_hex(8)
        c.l.gateway('calendar_draft',uid,event_id,payload=draft)
        return cards(draft,idx//8)
    except (c.l.StorageError,c.CalendarError):
        return c.card('清單暫時無法讀取或儲存',['請稍後重試；沒有加入 Google 日曆。'])
