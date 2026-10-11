"""Supplement one day's review entries, then explicitly advance to the next day."""
import re
import secrets
import time
from lifeos_calendar_list import CLOCK, HEADER, review_list
from lifeos_calendar_fill import missing, fill_entry


def entry_name(e):
    name=CLOCK.sub('',e['title'])
    name=re.sub(r'全天|上午|下午|晚上|中午|凌晨|早上','',name)
    name=re.sub(r'(?<![A-Za-z])[FB](?:\s*\+\s*[FB])?(?![A-Za-z])','',name,flags=re.I)
    return name.strip(' ～~－-–—到至')


def status(e):
    if e.get('date_problem'):return '日期待確認'
    if e.get('incomplete') or e.get('needs_name'):return '名稱待補完整'
    if e['kind']=='start_only':return '缺結束時間'
    if e['kind']=='needs_time':
        notes=' '.join(e.get('notes',[]))
        if '時間格式無效' in notes:return '時間無效，請重新提供'
        if '結束時間沒有晚於開始' in notes:return '結束早於開始，請確認起訖時間'
        if '上午或下午' in notes or '上午／下午' in notes:return '請確認上午或下午'
        if not e.get('times') and re.search(r'(?<![A-Za-z])[FB](?![A-Za-z])|小孟',e['title'],re.I):return '缺開始時間'
        return '缺開始與結束時間'
    return '已補齊，待確認'


def render(c,uid,draft,pending,tenant,notes=()):
    from linebot.v3.messaging import FlexMessage,FlexContainer
    cursor=draft['fill_day'];indices=cursor['indices'];entries=draft['review']['entries']
    todo=[i for i in indices if missing(entries[i])]
    pending[(tenant,uid)]={'token':draft['review_id'],'day_fill':True,'until':time.monotonic()+1800}
    def txt(value,size='sm',color='#263F3C',bold=False):
        return {'type':'text','text':value or '—','size':size,'color':color,'weight':'bold' if bold else 'regular','wrap':True}
    body=[]
    for needs,label in ((True,'需要補資料'),(False,'已齊全，請核對')):
        group=[i for i in indices if bool(missing(entries[i]))==needs]
        if not group:continue
        body.append(txt(f'{label} · {len(group)} 筆','md',bold=True))
        for i in group:
            e=entries[i]
            name=CLOCK.sub('',e['title'])
            name=re.sub(r'全天|上午|下午|晚上|中午|凌晨|早上','',name).strip(' ～~－-–—到至')
            clocks=e.get('times',[])
            when='全天' if e['kind']=='all_day' else ('～'.join(clocks) if clocks else '未提供時間')
            if e['kind']=='start_only':when+=' 開始'
            content=[{'type':'box','layout':'horizontal','spacing':'md','contents':[
                {**txt(f'第 {i+1} 筆','xs','#7B827F'), 'flex':0},txt(name or '名稱待補','lg',bold=True)]},
                txt('目前時間｜'+when,'sm','#66716E')]
            if needs:content.append(txt('待補｜'+status(e),'md','#B3261E',True))
            body.append({'type':'box','layout':'vertical','spacing':'md','paddingAll':'16px',
                         'cornerRadius':'10px','backgroundColor':'#F6F3EE' if needs else '#F4F7F5','contents':content})
    for note in notes:
        if note.strip():body.append(txt(note,'sm','#B3261E'))
    body.append({'type':'separator','margin':'md'})
    body.append(txt('用編號或名稱，一次回覆這天的修改。\n例如：2 下午兩點，3 到下午三點半。' if todo else '當天資料已齊全，確認後才進下一天。\n尚未加入 Google 日曆。','sm','#66716E'))
    def btn(label,command):
        return {'type':'button','height':'sm','style':'secondary','action':{'type':'message','label':label,'text':command}}
    title=cursor['day']+'｜'+('補當天資料' if todo else '確認當天')
    bubble={'type':'bubble','size':'mega','header':{'type':'box','layout':'vertical','paddingAll':'20px','spacing':'sm','contents':[
        txt(cursor['day'],'xl',bold=True),txt('補齊這一天的資料' if todo else '核對這一天的行程','md')]},
        'body':{'type':'box','layout':'vertical','paddingAll':'20px','spacing':'lg','contents':body},
        'footer':{'type':'box','layout':'vertical','spacing':'sm','contents':[
            btn('當天正確，下一天','清單當天 '+draft['review_id']),btn('回到清單','停止清單修改')]}}
    return FlexMessage(alt_text=title,contents=FlexContainer.from_dict(bubble))


def start(c,uid,draft,pending,tenant,event_id=None,advance=False):
    cursor=draft.get('fill_day')
    if advance and cursor:
        if any(missing(draft['review']['entries'][i]) for i in cursor['indices']):
            return render(c,uid,draft,pending,tenant,['這一天還有缺資料的項目，請先補齊。'])
        draft.pop('fill_day',None);cursor=None
        draft['review_id']=secrets.token_hex(8)
    if not cursor:
        entries=draft['review']['entries']
        days=sorted({e['date'] for e in entries if missing(e)})
        if not days:
            pending.pop((tenant,uid),None)
            c.l.gateway('calendar_draft',uid,event_id,payload=draft)
            return c.card('所有日期已補齊',['請查看完整清單，再統一確認加入日曆。'],choices=[('查看完整清單','清單總覽')])
        day=days[0]
        draft['fill_day']={'day':day,'indices':[i for i,e in enumerate(entries) if e['date']==day and not e.get('write_started')]}
    c.l.gateway('calendar_draft',uid,event_id,payload=draft)
    return render(c,uid,draft,pending,tenant)


def apply(c,uid,draft,text,pending,tenant,event_id=None):
    cursor=draft.get('fill_day')
    if not cursor:return c.card('補資料已失效',['請重新按「補齊資料」。'])
    entries=draft['review']['entries'];indices=cursor['indices']
    chunks=[s.strip() for s in re.split(r'[\n，,；;]+',text) if s.strip()]
    updates={};notes=[];heading=None
    for chunk in chunks:
        if HEADER.fullmatch(chunk):
            heading=chunk
            bad=[i for i in indices if entries[i].get('date_problem')]
            for i in bad:
                replacement=fill_entry(c,entries[i],chunk)
                result=review_list(replacement,c.l.clock().year) if replacement else None
                if result and not result['errors'] and len(result['entries'])==1:updates[i]=result['entries'][0]
                else:notes.append('日期仍無效，請再確認。')
            continue
        match=re.match(r'^(\d+)(?:[.、]|\s|[：:]\s+)\s*(.*)$',chunk)
        answer=chunk;targets=[]
        if match:
            i=int(match[1])-1
            if i in indices:targets=[i];answer=match[2]
        else:
            for i in indices:
                name=entry_name(entries[i])
                if name and chunk.startswith(name):targets.append(i)
            if len(targets)==1:
                answer=chunk[len(entry_name(entries[targets[0]])):].lstrip(' ：:')
                answer=re.sub(r'^[FB](?:\s*\+\s*[FB])?\s*','',answer,flags=re.I)
            elif not targets:
                todo=[i for i in indices if missing(updates.get(i,entries[i]))]
                if len(todo)==1:targets=todo
        if len(targets)!=1:
            notes.append('「'+chunk[:60]+'」無法對應，請加行程編號。');continue
        i=targets[0];old=updates.get(i,entries[i])
        if i in updates and not entries[i].get('date_problem'):
            notes.append(f'{i+1} · 同一筆提供多次，請分開重傳。');continue
        # A number can supply a full replacement, including a corrected name/date.
        replacement=fill_entry(c,old,answer)
        if replacement is None and (CLOCK.search(answer) or HEADER.fullmatch(answer.splitlines()[0])):
            replacement=old['date']+'\n'+answer
        if replacement is None:
            notes.append(f'{i+1} · 尚未辨識到有效資料，請補日期、完整名稱或24小時制時間。');continue
        result=review_list(replacement,c.l.clock().year)
        if not result or result['errors'] or len(result['entries'])!=1:
            notes.append(f'{i+1} · 日期或格式仍需確認。');continue
        updates[i]=result['entries'][0]
    if updates:
        for i,e in updates.items():entries[i]=e
        dates={entries[i]['date'] for i in indices}
        if len(dates)==1:cursor['day']=next(iter(dates))
        draft['review']['errors']=[e['date']+' '+e['title']+'：日期待確認' for e in entries if e.get('date_problem')]
        for e in entries:
            if not e.get('write_started'):e.pop('google_id',None)
        draft['review_id']=secrets.token_hex(8)
        c.l.gateway('calendar_draft',uid,event_id,payload=draft)
        notes.insert(0,f'已更新 {len(updates)} 筆，請核對當天結果。')
    elif not notes:notes.append('請用行程姓名或編號，提供這一天缺少的資料。')
    return render(c,uid,draft,pending,tenant,notes)
