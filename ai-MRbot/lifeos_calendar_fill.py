"""One-entry-at-a-time supplementation without rebuilding the list."""
import re,time
from datetime import date,timedelta
from lifeos_calendar_list import CLOCK,HEADER

def missing(e):
    return not e.get('write_started') and (e.get('incomplete') or e.get('needs_name') or e.get('date_problem') or e['kind'] not in ('complete','all_day'))

def ask_next(c,uid,draft,pending,tenant,prefix=''):
    for i,e in enumerate(draft['review']['entries']):
        if not missing(e):continue
        pending[(tenant,uid)]={'token':draft['review_id'],'index':i,'until':time.monotonic()+600,'guided':True}
        if e.get('date_problem'):question='請回覆正確日期，例如 2026/10/15（以日期為準）。'
        elif e.get('incomplete') or e.get('needs_name'):question='請回覆完整行程內容，包含已知的起訖時間。'
        elif e['kind']=='start_only':question='請提供結束時間，例如下午三點；或提供完整起訖時間。'
        else:question='請提供時間，例如 14:00～15:30；美容 F／B 可只回開始時間（90分鐘），F+B 或小孟為180分鐘。也可回覆「全天」。'
        if c.getenv('LIFEOS_INDUSTRY')=='engineering' and not e.get('date_problem') and not e.get('incomplete') and not e.get('needs_name') and e['kind']!='start_only':
            question='請提供完整起訖時間，例如 14:00～15:30；也可回覆「全天」。'
        lines=[e['date']+' '+e['title'],question]
        if prefix.strip():lines.insert(0,prefix)
        return c.card('補第 '+str(i+1)+' 筆',lines,choices=[('回到清單','停止清單修改')])
    pending.pop((tenant,uid),None)
    lines=['請查看清單，再按「先加入完整項目」確認匯入。']
    if prefix.strip():lines.insert(0,prefix)
    return c.card('資料已補齊',lines,choices=[('查看清單','清單總覽')])

def fill_entry(c,old,text):
    if old.get('date_problem'):
        h=HEADER.fullmatch(text.strip())
        if not h:return None
        y,m,d,*_=h.groups()
        try:day=date(int(y or c.l.clock().year),int(m),int(d))
        except ValueError:return None
        return day.isoformat()+'\n'+old['title']
    if HEADER.fullmatch(text.splitlines()[0].strip()):return text
    if old.get('incomplete') or old.get('needs_name'):return old['date']+'\n'+text
    title=CLOCK.sub('',old['title'])
    title=re.sub(r'^\s*(?:全天|上午|下午|晚上|中午|凌晨|早上|到|至|～|~|－|-|–|—|\s)+','',title).strip()
    if text.strip()=='全天':return old['date']+'\n全天 '+title
    matches=list(re.finditer(c.TIME_PATTERN,text))
    clocks=[]
    for m in matches:
        if not m[1] and c.l.number(m[2])<12 and len(m[2])==1:return None
        try:dt,_=c.l.parse_date(old['date']+' '+m.group())
        except c.l.InputError:return None
        if dt is None:return None
        clocks.append(dt.strftime('%H:%M'))
    if len(clocks)==1:
        if old['kind']=='start_only' and old.get('times'):clocks=[old['times'][0],clocks[0]]
        elif c.booking_category(title) in ('美容','新客'):
            from datetime import datetime
            start=datetime.fromisoformat(old['date']+'T'+clocks[0]);minutes=180 if c.is_xiaomeng(title) or re.search(r'F\s*\+\s*B',title,re.I) else 90
            end=start+timedelta(minutes=minutes)
            if end.date()!=start.date():return None
            clocks.append(end.strftime('%H:%M'))
    if not clocks:return None
    return old['date']+'\n'+('～'.join(clocks))+' '+title
