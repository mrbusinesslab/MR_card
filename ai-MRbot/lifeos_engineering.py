"""Tenant-scoped engineering workflow using persisted cases and ordinary tasks."""
import hmac
import json
import re
import time
import requests
from datetime import datetime, timedelta
from uuid import UUID
from flask import request
import lifeos as tasks
import lifeos_calendar as calendar
from lifeos_settings import getenv,tenant_id

STAGES=('待場勘','待報價','待確認','待施工','施工中','待驗收','已結案')
KINDS=('報價','備料','施工','追加','驗收','請款','其他')
MENU=('生活助理','更多功能','工程秘書','工程總覽','案件總覽','工程待辦','報價追蹤','待驗收','工程說明','新增案件','新增工程事項','工程進度','工程更多','工程新增','停止新增')
_FLOWS={}
_FLOW_REPLIES={}

INK='#172B2A'
ACCENT='#345C58'


def tx(value,size='sm',color=INK,bold=False):
    return {'type':'text','text':str(value) or '—','size':size,'color':color,'wrap':True,
            'weight':'bold' if bold else 'regular'}


def button(label,command,primary=False):
    item={'type':'button','style':'primary' if primary else 'secondary','height':'sm',
          'action':({'type':'uri','label':label[:20],'uri':command} if command.startswith('https://www.google.com/maps/') else {'type':'message','label':label[:20],'text':command})}
    if primary:item['color']=ACCENT
    return item


def bubble(title,contents,choices=None,eyebrow=None):
    header=([tx(eyebrow,'xs','#64748B')] if eyebrow else [])+[tx(title,'lg',bold=True)]
    result={'type':'bubble','size':'mega','header':{'type':'box','layout':'vertical','spacing':'sm','paddingAll':'20px','contents':header},
        'body':{'type':'box','layout':'vertical','paddingAll':'20px','paddingTop':'0px','spacing':'md','contents':contents or [tx('請選擇下方項目。' if choices else '目前沒有資料。')]}}
    if choices:
        result['footer']={'type':'box','layout':'vertical','spacing':'sm','paddingAll':'16px',
            'contents':[button(label,command,i==0) for i,(label,command) in enumerate(choices)]}
    return result


def message(title,bubbles,quick=None):
    from linebot.v3.messaging import FlexMessage,FlexContainer,QuickReply,QuickReplyItem,MessageAction
    # Navigation stays visible in the card, including desktop clients where
    # quick replies are unavailable. Keep these separate from primary actions.
    for b in bubbles:
        for start in range(0,len(quick or []),3):
            links=[]
            for label,command in quick[start:start+3]:
                links.append({'type':'box','layout':'vertical','flex':1,'paddingAll':'8px',
                    'action':{'type':'message','label':label[:20],'text':command},
                    'contents':[tx(label,'xs',ACCENT,True)]})
            b['body']['contents'].append({'type':'box','layout':'horizontal','margin':'lg','spacing':'sm','contents':links})
    if getenv('LIFEOS_ENGINEERING_WORKFLOW')=='1':
        def convert(node):
            if isinstance(node,dict):
                action=node.get('action')
                if action and action.get('type')=='message' and len('lifeos:'+action['text'])<=300:
                    node['action']={'type':'postback','label':action['label'],'data':'lifeos:'+action['text'],'displayText':action['label']}
                for value in node.values():convert(value)
            elif isinstance(node,list):
                for value in node:convert(value)
        convert(bubbles)
    content=bubbles[0] if len(bubbles)==1 else {'type':'carousel','contents':bubbles}
    args={'alt_text':title,'contents':FlexContainer.from_dict(content)}
    if quick:
        from linebot.v3.messaging import PostbackAction
        actions=[PostbackAction(label=a[:20],data='lifeos:'+b,display_text=a[:20]) if getenv('LIFEOS_ENGINEERING_WORKFLOW')=='1' and len('lifeos:'+b)<=300
                 else MessageAction(label=a[:20],text=b) for a,b in quick[:13]]
        args['quick_reply']=QuickReply(items=[QuickReplyItem(action=a) for a in actions])
    return FlexMessage(**args)


def card(title,lines,choices=None):
    return message(title,[bubble(title,[tx(x) for x in lines],choices)])


def api(action,uid,event_id=None,**values):
    result=tasks.gateway('engineering_'+action,uid,event_id,**values)
    if result.get('error'):
        messages={'not_found':'找不到可查看的案件，請重新開啟「案件總覽」。',
                  'status_conflict':'這個階段已被更新，請重新查看後再修改。',
                  'invalid_date':'完成日期必須是今天或之前的有效日期。',
                  'note_conflict':'這段備註已被其他人更新。請回到案場重新查看，再編輯。',
                  'duplicate_case':'已有同名案件，請改用不同案名。',
                  'not_enrolled':'請先使用建置者提供的一次性啟用碼綁定。'}
        raise tasks.InputError(messages.get(result['error'],'資料未更新，請確認格式後重試。'))
    return result


def case_id(value):
    try: return str(UUID(value))
    except ValueError: raise tasks.InputError('請使用案件卡片上的按鈕。')


def cases(uid):
    return api('list',uid).get('cases',[])


def select_case(uid,name):
    rows=cases(uid)
    exact=[c for c in rows if c['name']==name]
    found=exact or [c for c in rows if name in c['name']]
    if len(found)!=1:
        raise tasks.InputError('請提供唯一案名。符合的案件：'+('、'.join(c['name'] for c in found) if found else '沒有，請先看「案件總覽」。'))
    return found[0]


def due(value):
    if not value: return '未定期限'
    try: return datetime.fromisoformat(value.replace('Z','+00:00')).astimezone(tasks.TZ).strftime('%m/%d %H:%M')
    except ValueError: return '日期待確認'


def case_title(c):
    return ('【示範】' if c.get('demo') else '')+c['name']


def task_meta(task):
    try:
        meta=json.loads(task.get('original_text',''))
        return meta if isinstance(meta,dict) else {}
    except (TypeError,ValueError):return {}


def task_title(task):
    return task_meta(task).get('text') or task.get('title','未命名事項').split('｜',1)[-1]


def task_case(task):
    title=task.get('title','')
    return title.split('｜',1)[0].removeprefix('【示範】') if '｜' in title else '工程待辦'


def deadline_row(value):
    label='期限：'+due(value);color='#64748B'
    if value:
        try:
            stamp=datetime.fromisoformat(value.replace('Z','+00:00')).astimezone(tasks.TZ)
            if stamp<tasks.clock(): label='已逾期 · '+due(value);color='#B4533C'
            elif stamp.date()==tasks.clock().date():label='今天到期 · '+due(value)
        except ValueError:pass
    return tx(label,'xs',color)


def open_items(items):
    return sorted((t for t in items if t.get('status') not in tasks.CLOSED),key=lambda t:(t.get('due_at') or '9999',t['id']))


def task_row(task,show_case=False):
    contents=([tx(task_case(task),'xs','#64748B')] if show_case else [])
    contents += [tx(task_title(task),'md',bold=True),deadline_row(task.get('due_at'))]
    return {'type':'box','layout':'vertical','spacing':'sm','paddingAll':'16px','cornerRadius':'12px','backgroundColor':'#F4F7F6',
            'action':{'type':'message','label':'查看待辦','text':'工程待辦操作 '+str(task['id'])},'contents':contents}


def overview(uid,filter_stage=None,page=1):
    rows=cases(uid)
    if filter_stage: rows=[c for c in rows if c['stage'] in filter_stage]
    if not rows: return card('案件總覽',['這個分類目前沒有案件。'],[('新增案件','新增案件'),('工程首頁','工程秘書')])
    page=max(1,min(page,(len(rows)+4)//5)); selected=rows[(page-1)*5:page*5]
    task_result=tasks.gateway('list',uid)
    groups={}
    for t in open_items(task_result.get('tasks',[])):
        groups.setdefault(task_meta(t).get('engineering_case_id'),[]).append(t)
    bubbles=[]
    for c in selected:
        items=groups.get(c['id'],[])
        contents=[tx(c['stage'],'sm',ACCENT,True),tx('下一步','xs','#64748B')]
        if items: contents += [tx(task_title(items[0]),'md',bold=True),deadline_row(items[0].get('due_at'))]
        elif c.get('open_tasks',0): contents.append(tx('有 '+str(c['open_tasks'])+' 項待辦，點入查看。'))
        else:contents.append(tx('尚無未完成待辦。'))
        b=bubble(c['name'],contents,[('查看案件','工程案件 '+c['id'])],('示範案件' if c.get('demo') else '工程案件'))
        b['body']['action']={'type':'message','label':'查看案件','text':'工程案件 '+c['id']}
        bubbles.append(b)
    quick=[]
    prefix='工程待驗收頁 ' if filter_stage else '工程總覽 '
    if page>1:quick.append(('上一頁',prefix+str(page-1)))
    if page*5<len(rows):quick.append(('下一頁',prefix+str(page+1)))
    quick += [('待驗收','待驗收'),('回首頁','工程秘書')]
    return message('工程案件總覽',bubbles,quick)


def detail(uid,key):
    result=api('detail',uid,case_id=key);c=result['case']
    items=open_items(result['tasks'])
    contents=[tx('目前進度 · '+c['stage'],'sm',ACCENT,True),tx('下一件要做的事','xs','#64748B')]
    contents.append(task_row(items[0]) if items else tx('目前沒有未完成待辦。'))
    choices=[('待辦事項（'+str(len(items))+'）','工程案件待辦 '+key),
             ('更新進度','工程階段 '+key),('更多資料','工程案件資料 '+key)]
    return message('案場詳情',[bubble(c['name'],contents,choices,'示範案件' if c.get('demo') else None)],
                   [('案件總覽','案件總覽'),('回首頁','工程秘書')])


def board(uid,kind=None,page=1,key=None):
    if key:
        result=api('detail',uid,case_id=key)
        rows=open_items(result['tasks']);heading=result['case']['name']+'的待辦'
    else:
        result=tasks.gateway('list',uid)
        rows=open_items([t for t in result.get('tasks',[]) if t.get('category','').startswith('工程／')])
        heading='報價待辦' if kind=='報價' else '待處理事項'
    if kind: rows=[t for t in rows if t['category']=='工程／'+kind]
    page=max(1,min(page,max(1,(len(rows)+3)//4))); selected=rows[(page-1)*4:page*4]
    contents=[tx('點事項，選擇完成或延期。','xs','#64748B')]
    contents += [task_row(t,show_case=not key) for t in selected]
    if not rows:contents=[tx('目前沒有未完成事項。')]
    if result.get('truncated'):contents.append(tx('清單較多，尚有資料未載入。','xs','#64748B'))
    prefix=('工程案件清單 '+key+' ') if key else ('工程清單 '+(kind or '全部')+' ')
    quick=[]
    if page>1:quick.append(('上一頁',prefix+str(page-1)))
    if page*4<len(rows):quick.append(('下一頁',prefix+str(page+1)))
    quick += [('新增待辦','工程新增事項 '+key) if key else ('案件總覽','案件總覽'),
              ('回到案件','工程案件 '+key) if key else ('回首頁','工程秘書')]
    return message(heading,[bubble(heading,contents,eyebrow=f'{len(rows)} 項待處理 · 第 {page} 頁')],quick)


def task_detail(uid,tid):
    result=tasks.gateway('list',uid,include_closed=True)
    task=next((t for t in result.get('tasks',[]) if t['id']==tid and t.get('category','').startswith('工程／')),None)
    if task is None:raise tasks.InputError('找不到這件待辦，請重新開啟待處理清單。')
    choices=[] if task['status'] in tasks.CLOSED else [('標記完成','完成 '+str(tid)),('延期','延期 '+str(tid)),('取消事項','取消 '+str(tid))]
    return message('處理待辦',[bubble(task_title(task),[tx(task_case(task),'sm',ACCENT),deadline_row(task.get('due_at')),tx('狀態：'+task['status'],'xs','#64748B')],choices)],
                   [('回到案件','工程案件 '+str(task_meta(task)['engineering_case_id']))] if task_meta(task).get('engineering_case_id') else [('待處理','工程待辦')])


def task_reply(uid,body):
    """Compact presentation only; keep all existing task permission checks."""
    if getenv('LIFEOS_INDUSTRY')!='engineering' or type(body) is not str:return None
    if not body.startswith(('已更新\n','已延期\n','確認取消待辦\n','請輸入延期日期\n')):return None
    try:
        if body.startswith('請輸入延期日期\n'):
            pending=tasks.gateway('get_user',uid).get('user',{}).get('pending_postpone')
            tid=pending.get('task_id') if pending else None
        else:
            match=re.search(r'#(\d+) ',body);tid=int(match[1]) if match else None
        row=next((t for t in tasks.gateway('list',uid,include_closed=True).get('tasks',[])
                  if t['id']==tid and t.get('category','').startswith('工程／')),None)
        if row is None:return None
        key=task_meta(row).get('engineering_case_id')
        back=('回到案件','工程案件 '+str(key)) if key else ('待處理','工程待辦')
        if body.startswith('確認取消待辦\n'):
            return card('取消這件事？',[task_title(row),task_case(row)],
                        [('確認取消','確認取消 '+str(tid)),('保留事項','工程待辦操作 '+str(tid))])
        if body.startswith('請輸入延期日期\n'):
            choices=[]
            for days,label in ((1,'明天'),(2,'後天'),(7,'一週後')):
                when=(tasks.clock()+timedelta(days=days)).replace(hour=17,minute=0,second=0,microsecond=0)
                choices.append((label+' 17:00',when.strftime('%Y/%m/%d %H:%M')))
            return card('要延到什麼時候？',[task_title(row),'也可直接輸入日期與時間。'],choices+[('不延期','停止延期')])
        title='已完成' if row['status']=='完成' else '已取消' if row['status']=='取消' else '已更新期限'
        lines=[task_title(row)]
        if row['status'] not in tasks.CLOSED:lines.append('新期限：'+due(row.get('due_at')))
        return card(title,lines,[back])
    except (tasks.StorageError,ValueError,KeyError):return None


def flow_prompt(flow):
    if flow['mode']=='case':
        prompts=[('案件名稱是什麼？','例如：林先生廚房'),('案場在哪裡？','請輸入地址或地點。'),('這個案件要做什麼？','例如：廚房冷熱水管更新')]
        title,hint=prompts[len(flow['values'])]
        return card(title,[hint],[('停止新增','停止新增')])
    step=len(flow['values'])
    if step==0:
        return message('選擇事項類型',[bubble('這件事屬於哪一類？',[tx(flow['case']['name'])])],[(k,k) for k in KINDS]+[('停止新增','停止新增')])
    if step==1:return card('要處理什麼事情？',[flow['case']['name'],'例如：購買防水材料'],[('停止新增','停止新增')])
    return card('什麼時候要完成？',[flow['values'][1],'例如：明天下午五點'],[('不設期限','不設期限'),('停止新增','停止新增')])


def start_flow(key,flow,event_id):
    _FLOWS[key]=flow
    result=flow_prompt(flow)
    if event_id:_FLOW_REPLIES[(*key,event_id)]={'until':flow['until'],'message':result}
    return result


def flow_step(uid,text,event_id):
    key=(tenant_id(),uid);flow=_FLOWS[key]
    if '｜' in text or '\n' in text:raise tasks.InputError('請一次輸入一個欄位，不需要加分隔符號。')
    values=flow['values'];step=len(values)
    if flow['mode']=='case':
        limit=(80,300,500)[step]
        if not text or len(text)>limit:raise tasks.InputError('這個欄位請填寫1～'+str(limit)+'字。')
        values.append(text)
        if len(values)<3:return flow_prompt(flow)
        name,location,scope=values
        _FLOWS.pop(key,None)
        return card('確認新增案件',[name,'地點：'+location,'工項：'+scope],
                    [('確認建立','確認建立案件 '+'｜'.join(values)),('放棄','工程秘書')])
    if step==0:
        if text not in KINDS:raise tasks.InputError('請點選下方的事項類型，或輸入「停止新增」。')
        values.append(text);return flow_prompt(flow)
    if step==1:
        if not text or len(text)>300:raise tasks.InputError('事項請填寫1～300字。')
        values.append(text);return flow_prompt(flow)
    when=None
    if text!='不設期限':
        when,spans=tasks.parse_date(text)
        rest=''.join(ch for i,ch in enumerate(text) if not any(a<=i<b for a,b in spans)).strip(' ，。前到至')
        if when is None or rest:raise tasks.InputError('請提供明確日期時間，例如「明天下午五點」，或點「不設期限」。')
    kind,title=values;c=flow['case']
    value=(when.strftime('%Y/%m/%d %H:%M')+' ' if when else '')+title
    _FLOWS.pop(key,None)
    return card('確認新增待辦',[title,c['name']+' · '+kind,'期限：'+due(when.isoformat() if when else None)],
                [('確認新增','確認工程事項 '+c['name']+'｜'+kind+'｜'+value),('放棄','工程案件 '+c['id'])])


def handle(uid,text,event_id=None,source_type='user'):
    if getenv('LIFEOS_INDUSTRY')!='engineering': return None
    text=text.strip()
    if getenv('LIFEOS_ENGINEERING_WORKFLOW')=='1':
        import lifeos_engineering_workflow as workflow
        result=workflow.handle(uid,text,event_id,source_type)
        if result is not None:return result
    now=time.monotonic()
    for cache in (_FLOWS,_FLOW_REPLIES):
        for key,value in list(cache.items()):
            if value['until']<now:cache.pop(key,None)
    flow_key=(tenant_id(),uid);reply_key=(tenant_id(),uid,event_id)
    prefixes=('工程案件 ','工程階段 ','工程進度 ','確認工程進度 ','案件 ','工程行程 ',
              '建立案件 ','確認建立案件 ','工程新增事項 ','工程事項 ','確認工程事項 ','工程總覽 ','工程清單 ',
              '工程案件待辦 ','工程案件資料 ','工程案件清單 ','工程待辦操作 ','工程全部階段 ','工程待驗收頁 ')
    explicit=text in MENU or text.startswith(prefixes)
    if not explicit and flow_key not in _FLOWS and reply_key not in _FLOW_REPLIES:return None
    if source_type!='user': return card('請使用私人聊天室',['工程案件只能在一對一聊天室查看與修改。'])
    try:
        if not uid or not tasks.gateway('get_user',uid).get('user'):
            return card('工程秘書尚未綁定',['請使用建置者提供的一次性啟用碼。'])
        if event_id and reply_key in _FLOW_REPLIES:return _FLOW_REPLIES[reply_key]['message']
        if text=='停止新增':
            _FLOWS.pop(flow_key,None)
            return card('已停止新增',['尚未儲存資料。'],[('回首頁','工程秘書')])
        if flow_key in _FLOWS and not explicit:
            result=flow_step(uid,text,event_id)
            if event_id:_FLOW_REPLIES[reply_key]={'until':now+1200,'message':result}
            return result
        if explicit:_FLOWS.pop(flow_key,None)
        if text in ('生活助理','工程秘書'):
            return message('工程秘書',[bubble('工程秘書',[tx('今天去哪裡、哪些事情還沒完成。')],
                [('今天安排','今天'),('案件總覽','案件總覽'),('待處理','工程待辦'),('新增','工程新增')])],
                [('更多','工程更多')])
        if text in ('更多功能','工程更多'):
            return card('更多功能',[],[('報價待辦','報價追蹤'),('待驗收案件','待驗收'),('本週行程','本周'),('提醒設定','提醒設定'),('使用說明','工程說明'),('回首頁','工程秘書')])
        if text=='工程新增':
            return card('要新增什麼？',[],[('案件','新增案件'),('案場待辦','新增工程事項'),('日曆行程','新增行程')])
        if text in ('工程總覽','案件總覽'): return overview(uid)
        if re.fullmatch(r'工程總覽 \d+',text): return overview(uid,page=int(text.split()[-1]))
        if re.fullmatch(r'工程待驗收頁 \d+',text):return overview(uid,('待驗收',),int(text.split()[-1]))
        if text=='待驗收': return overview(uid,('待驗收',))
        if text=='工程待辦': return board(uid)
        if text=='報價追蹤': return board(uid,'報價')
        if text.startswith('工程待辦操作 '):return task_detail(uid,int(text.split()[-1]))
        if text.startswith('工程案件待辦 '):return board(uid,key=case_id(text.split()[-1]))
        if text.startswith('工程案件清單 '):
            _,key,page=text.split();return board(uid,page=int(page),key=case_id(key))
        if text.startswith('工程案件資料 '):
            key=case_id(text.split()[-1]);c=api('detail',uid,case_id=key)['case']
            return card(c['name'],['地點：'+(c.get('location') or '尚未填寫'),'工項：'+(c.get('scope') or '尚未填寫')],
                        [('這個案場的行程','工程行程 '+key),('新增待辦','工程新增事項 '+key),('回到案件','工程案件 '+key)])
        if text.startswith('工程清單 '):
            _,kind,page=text.split()
            return board(uid,None if kind=='全部' else kind,int(page))
        if text=='新增案件':
            return start_flow(flow_key,{'mode':'case','values':[],'until':now+1200},event_id)
        if text=='新增工程事項':
            rows=cases(uid)
            return card('要加在哪個案件？',[],[(c['name'][:20],'工程新增事項 '+c['id']) for c in rows[:8]]+[('回首頁','工程秘書')])
        if text in ('工程說明','工程進度'):
            return card('工程秘書操作方式',[
                '查案件：案件 陳先生\n查看案場進度、地址與待處理事項。',
                '新增案件：建立案件 案名｜地點｜工項\n例如：建立案件 林先生廚房｜台中北屯（示範）｜水管更新',
                '新增事項：工程事項 案名｜類型｜日期時間＋內容\n例如：工程事項 陳先生浴室｜備料｜明天下午五點前買防水材料',
                '類型：'+ '／'.join(KINDS),
                '更新進度：工程進度 案名｜待施工\n階段：'+'／'.join(STAGES),
                '新增行程：明天上午九點到十點 陳先生浴室場勘\n工程行程請提供開始及結束時間。',
                '新增與進度更新都會先出現確認卡。待辦可完成、取消或延期；進度需由使用者更新。',
                '每日提醒可到「提醒設定」開啟。未提供庫存、多人派工及自動入帳功能。'],
                [('案件總覽','案件總覽'),('提醒設定','提醒設定')])
        if text.startswith('案件 '): return detail(uid,select_case(uid,text[3:].strip())['id'])
        if text.startswith('工程案件 '): return detail(uid,case_id(text.split()[-1]))
        if text.startswith('工程階段 '):
            key=case_id(text.split()[-1]); c=api('detail',uid,case_id=key)['case']
            choices=[]
            if c['stage'] in STAGES[:-1]:
                next_stage=STAGES[STAGES.index(c['stage'])+1]
                choices.append(('改為'+next_stage,'工程進度 '+key+'｜'+next_stage))
            choices += [('選其他進度','工程全部階段 '+key),('保留原進度','工程案件 '+key)]
            return card('更新進度',[c['name'],'目前：'+c['stage']],choices)
        if text.startswith('工程全部階段 '):
            key=case_id(text.split()[-1]);c=api('detail',uid,case_id=key)['case']
            return card('選擇進度',[c['name']],[(s,'工程進度 '+key+'｜'+s) for s in STAGES if s!=c['stage']]+[('回到案件','工程案件 '+key)])
        if text.startswith(('工程進度 ','確認工程進度 ')):
            confirm=text.startswith('確認'); value=text.split(' ',1)[1]; name,stage=value.split('｜',1)
            try: key=str(UUID(name))
            except ValueError: key=select_case(uid,name.strip())['id']
            c=api('detail',uid,case_id=key)['case'];stage=stage.strip()
            if stage not in STAGES: raise tasks.InputError('請選擇：'+'／'.join(STAGES))
            if not confirm: return card('確認更新進度',[case_title(c),c['stage']+' → '+stage],
                [('確認更新','確認工程進度 '+key+'｜'+stage),('保留原進度','工程案件 '+key)])
            api('stage',uid,event_id,case_id=key,stage=stage)
            return card('進度已更新',[c['name'],stage],[('回到案件','工程案件 '+key)])
        if text.startswith(('建立案件 ','確認建立案件 ')):
            confirm=text.startswith('確認'); value=text.split(' ',1)[1];name,location,scope=(v.strip() for v in value.split('｜',2))
            if not name or len(name)>80 or len(location)>300 or len(scope)>500: raise tasks.InputError('案名最多80字、地點300字、工項500字，請勿留空案名。')
            command='確認建立案件 '+name+'｜'+location+'｜'+scope
            if len(command)>1000: raise tasks.InputError('案件內容太長，請精簡。')
            if not confirm: return card('確認建立工程案件',[name,'地點：'+location,'工項：'+scope,'初始進度：待場勘'],[('確認建立',command),('放棄','工程秘書')])
            c=api('create',uid,event_id,name=name,location=location,scope=scope)['case']
            return card('案件已建立',[c['name']],[('查看案件','工程案件 '+c['id'])])
        if text.startswith('工程新增事項 '):
            c=api('detail',uid,case_id=case_id(text.split()[-1]))['case']
            return start_flow(flow_key,{'mode':'task','case':c,'values':[],'until':now+1200},event_id)
        if text.startswith(('工程事項 ','確認工程事項 ')):
            confirm=text.startswith('確認');name,kind,value=(s.strip() for s in text.split(' ',1)[1].split('｜',2))
            c=select_case(uid,name)
            if kind not in KINDS: raise tasks.InputError('事項類型：'+'／'.join(KINDS))
            parsed_tasks=tasks.parse_tasks(value)
            if len(parsed_tasks)!=1: raise tasks.InputError('每次請新增一筆工程事項。')
            parsed=parsed_tasks[0]
            if not confirm: return card('確認工程事項',[case_title(c),kind+'｜'+parsed['title'],'期限：'+due(parsed.get('due_at'))],
                [('確認新增','確認工程事項 '+c['name']+'｜'+kind+'｜'+value),('放棄','工程案件 '+c['id'])])
            api('add_task',uid,event_id,case_id=c['id'],kind=kind,title=parsed['title'],due_at=parsed.get('due_at'))
            return card('待辦已新增',[parsed['title'],'期限：'+due(parsed.get('due_at'))],[('回到案件','工程案件 '+c['id'])])
        if text.startswith('工程行程 '):
            c=api('detail',uid,case_id=case_id(text.split()[-1]))['case'];now=tasks.clock()
            result=calendar.call('GET',params={'q':c['name'],'timeMin':now.replace(hour=0,minute=0,second=0,microsecond=0).isoformat(),
                'timeMax':(now+timedelta(days=90)).isoformat(),'singleEvents':'true','orderBy':'startTime','maxResults':20})
            events=calendar.visible_events(uid,[e for e in result.get('items',[]) if e.get('status')!='cancelled'])
            return calendar.card('案場近期行程',[case_title(c),'未來90天｜最多列20筆'],events=events,choices=[('回到案件','工程案件 '+c['id'])])
        return card('工程指令格式',['請輸入「工程說明」查看範例。'])
    except (ValueError,KeyError): return card('請補充工程資料',['請使用「｜」分隔欄位，輸入「工程說明」查看範例。'])
    except tasks.InputError as exc: return card('請確認工程資料',[str(exc)])
    except (tasks.StorageError,calendar.CalendarError): return card('工程資料暫時無法讀取',['這次操作未確認完成，請稍後重新查詢再操作。'])


def install_routes(bp):
    @bp.post('/lifeos/engineering-check')
    def engineering_check():
        key=getenv('LIFEOS_CRON_KEY','')
        if not key or not hmac.compare_digest(request.headers.get('Authorization',''),'Bearer '+key):
            return {'error':'unauthorized'},401
        if getenv('LIFEOS_INDUSTRY')!='engineering': return {'error':'not_enabled'},404
        uid=getenv('LIFEOS_GOOGLE_USER_ID')
        try:
            rows=cases(uid)
            result={'industry':'engineering','case_count':len(rows),'demo_count':sum(bool(c.get('demo')) for c in rows),
                    'layout_version':'engineering-address-copy-v1' if getenv('LIFEOS_ENGINEERING_WORKFLOW')=='1' else 'compact-v2','ready':True}
            params=request.get_json(silent=True) or {}
            result['address_action']='clipboard'
            result['geocoding_enabled']=False
            if params.get('validate_cards') is True:
                if getenv('LIFEOS_ENGINEERING_WORKFLOW')=='1':
                    import lifeos_engineering_workflow as workflow
                    import lifeos_engineering_booking as booking
                    import lifeos_calendar as cal
                    cards=[handle(uid,'工程秘書'),booking.prompt(),cal.card('確認工程預約',
                        ['日期：2026/10/30 14:00～15:00','案場名稱：測試案場','預約工程：場勘','地點：台中車站'],confirm=True,location='台中車站')]
                    if rows:cards += [workflow.detail(uid,rows[0]['id']),handle(uid,'工程案件資料 '+rows[0]['id'])]
                    result['layout_version']='engineering-address-copy-v1'
                else:
                    cards=[handle(uid,'工程秘書'),overview(uid),board(uid)]
                    if rows:cards += [detail(uid,rows[0]['id']),handle(uid,'工程階段 '+rows[0]['id'])]
                response=requests.post('https://api.line.me/v2/bot/message/validate/reply',
                    headers={'Authorization':'Bearer '+getenv('LINE_CHANNEL_ACCESS_TOKEN','')},
                    json={'messages':[c.to_dict() for c in cards]},timeout=10)
                result['cards_valid']=response.status_code==200
                result['card_validation_status']=response.status_code
                if response.status_code!=200:
                    result['ready']=False
                    result['validation_error']=response.text[:1500]
                    return result,503
            return result
        except (tasks.StorageError,tasks.InputError,requests.RequestException): return {'ready':False},503
