"""Seven-phase engineering view: stage status and notes, no task board."""
import time
from datetime import datetime
from lifeos_settings import getenv,tenant_id
import lifeos as tasks
import lifeos_engineering as ui

PHASES=(('appointment','預約／場勘'),('quote','待報價'),('contract','合約確認'),
        ('materials','備料準備'),('construction','開始施工'),('finishing','完工收尾'),('acceptance','驗收'))
LABELS=dict(PHASES)
STATES=('未開始','進行中','已完成','不適用')
COLORS={'未開始':'#E4E9E8','進行中':'#E8A44A','已完成':'#345C58','不適用':'#F1F3F2'}
INKS={'未開始':'#64748B','進行中':'#9A6116','已完成':'#345C58','不適用':'#94A3B8'}
_PENDING={}
_REPLIES={}


def phases(c):
    stored={s['key']:s for s in c.get('workflow',[]) if isinstance(s,dict) and s.get('key') in LABELS}
    return [dict(key=k,status=stored.get(k,{}).get('status','未開始'),note=stored.get(k,{}).get('note','')) for k,_ in PHASES]


def progress(c):
    rows=phases(c);total=sum(s['status']!='不適用' for s in rows)
    done=sum(s['status']=='已完成' for s in rows)
    current=next((s for s in rows if s['status']=='進行中'),None)
    current=current or next((s for s in rows if s['status']=='未開始'),None)
    return rows,done,total,current


def progress_bar(c):
    rows,done,total,current=progress(c)
    segments=[{'type':'box','layout':'vertical','flex':1,'height':'10px','cornerRadius':'4px',
               'backgroundColor':COLORS.get(s['status'],COLORS['未開始']),'contents':[]} for s in rows]
    label=f'流程完成 {done}／{total} 階段' if total else '所有階段均不適用'
    return [{'type':'box','layout':'horizontal','spacing':'xs','contents':segments},ui.tx(label,'xs','#64748B')]


def get_case(uid,key):
    return ui.api('workflow_get',uid,case_id=ui.case_id(key))['case']


def finish_label(c):
    value=c.get('expected_finish')
    return '預計完工：'+value.replace('-','/') if value else '預計完工：尚未設定'


def overview(uid,page=1,acceptance_only=False):
    rows=ui.cases(uid)
    if acceptance_only:
        rows=[c for c in rows if progress(c)[3] and progress(c)[3]['key']=='acceptance']
    if not rows:return ui.card('工程進度',['目前沒有符合的案場。'],[('新增案場','新增案件'),('回首頁','工程秘書')])
    page=max(1,min(page,(len(rows)+4)//5));cards=[]
    for c in rows[(page-1)*5:page*5]:
        _,done,total,current=progress(c)
        label=LABELS[current['key']] if current else '流程已完成' if total else '尚無適用階段'
        body=progress_bar(c)+[ui.tx('目前：'+label,'md',bold=True),ui.tx(finish_label(c),'xs','#64748B')]
        if current and current.get('note'):
            note=current['note'].splitlines()[0]
            body.append(ui.tx('備註：'+note[:70]+('…' if len(note)>70 else ''),'sm'))
        body.append(ui.tx('點入查看七個階段的狀態。','xs','#64748B'))
        cards.append(ui.bubble(c['name'],body,[('查看工程進度','工程案件 '+c['id'])],'示範案場' if c.get('demo') else '工程案場'))
    prefix='工程驗收進度頁 ' if acceptance_only else '工程流程總覽 '
    nav=[]
    if page>1:nav.append(('上一頁',prefix+str(page-1)))
    if page*5<len(rows):nav.append(('下一頁',prefix+str(page+1)))
    return ui.message('工程進度總覽',cards,nav+[('回首頁','工程秘書')])


def detail(uid,key):
    c=get_case(uid,key)
    body=progress_bar(c)+[ui.tx(finish_label(c),'xs','#64748B'),ui.tx('點階段，更新狀態或寫備註。','xs','#64748B')]
    for s in phases(c):
        left=ui.tx(LABELS[s['key']],'sm',bold=True);left['flex']=3
        right=ui.tx(s['status'],'xs',INKS.get(s['status'],'#64748B'),True);right.update(flex=2,align='end')
        row=[{'type':'box','layout':'horizontal','contents':[left,right]}]
        if s.get('note'):row.append(ui.tx('有備註','xxs','#94A3B8'))
        body.append({'type':'box','layout':'vertical','spacing':'xs','paddingAll':'12px','cornerRadius':'8px',
                     'backgroundColor':'#F4F7F6','action':{'type':'message','label':'查看'+LABELS[s['key']],
                     'text':'工程流程 '+key+' '+s['key']},'contents':row})
    return ui.message('七階段工程進度',[ui.bubble(c['name'],body,
            [('設定預計完工日','工程完工日期 '+key),('地址與工項','工程案件資料 '+key)],'示範案場' if c.get('demo') else None)],
            [('案件總覽','案件總覽'),('回首頁','工程秘書')])


def phase_card(uid,key,phase):
    if phase not in LABELS:raise tasks.InputError('請點案件卡片中的階段。')
    c=get_case(uid,key);s=next(s for s in phases(c) if s['key']==phase)
    note=s.get('note') or '目前沒有備註。'
    if len(note)>1500:note=note[:1500]+'\n…備註較長，請精簡後再編輯。'
    body=[ui.tx('狀態：'+s['status'],'sm',INKS.get(s['status'],'#64748B'),True),ui.tx('備註','xs','#64748B'),ui.tx(note)]
    return ui.message(LABELS[phase],[ui.bubble(LABELS[phase],body,
            [('變更狀態','工程流程狀態 '+key+' '+phase),('編輯備註','工程流程備註 '+key+' '+phase)],c['name'])],
            [('回到案場','工程案件 '+key)])


def save_note_prompt(uid,key,phase):
    c=get_case(uid,key);s=next(s for s in phases(c) if s['key']==phase)
    _PENDING[(tenant_id(),uid)]={'kind':'note','case_id':key,'phase':phase,'expected_note':s.get('note',''),'until':time.monotonic()+1200}
    return ui.card('請輸入'+LABELS[phase]+'的備註',[c['name'],'例如：缺兩個接頭，星期五到貨。\n原備註會在確認後替換。'],
                   [('清空備註','清空備註'),('取消編輯','取消流程編輯')])


def editing(uid,text):
    p=_PENDING[(tenant_id(),uid)]
    if p.get('preview'):return ui.card('這筆內容尚未儲存',['請確認，或取消後重新輸入。'],
        [('確認儲存','確認流程編輯'),('取消','取消流程編輯')])
    if p['kind']=='note':
        note='' if text=='清空備註' else text.strip()
        if len(note)>1500:raise tasks.InputError('備註最多1500字，請精簡後再傳。')
        p.update(note=note,preview=True)
        return ui.card('確認備註',[LABELS[p['phase']],note or '清空這個階段的備註。'],[('確認儲存','確認流程編輯'),('取消','取消流程編輯')])
    value=None
    if text!='不設日期':
        stamp,spans=tasks.parse_date(text)
        rest=''.join(ch for i,ch in enumerate(text) if not any(a<=i<b for a,b in spans)).strip(' ，。前到至')
        if not stamp or rest:raise tasks.InputError('請提供日期，例如「10/30」或「下星期五」。')
        value=stamp.date().isoformat()
    p.update(expected_finish=value,preview=True)
    return ui.card('確認預計完工日',[value.replace('-','/') if value else '取消預計完工日'],
                   [('確認儲存','確認流程編輯'),('取消','取消流程編輯')])


def handle(uid,text,event_id=None,source_type='user'):
    if getenv('LIFEOS_ENGINEERING_WORKFLOW')!='1':return None
    now=time.monotonic();key=(tenant_id(),uid);reply_key=(*key,event_id)
    for cache in (_PENDING,_REPLIES):
        for k,v in list(cache.items()):
            if v['until']<now:cache.pop(k,None)
    menus=('生活助理','工程秘書','案件總覽','工程總覽','工程待辦','報價追蹤','待驗收','工程更多','更多功能','工程新增',
           '工程說明','工程進度','新增案件','新增工程事項','取消流程編輯','確認流程編輯')
    prefixes=('工程流程 ','工程流程總覽 ','工程流程狀態 ','工程流程備註 ','確認階段狀態 ','工程完工日期 ',
              '工程案件 ','案件 ','工程階段 ','工程全部階段 ','工程案件待辦 ','工程案件清單 ','工程案件資料 ',
              '工程新增事項 ','工程待辦操作 ','工程清單 ','工程總覽 ','工程待驗收頁 ','工程驗收進度頁 ',
              '工程進度 ','確認工程進度 ','工程事項 ','確認工程事項 ')
    explicit=text in menus or text.startswith(prefixes)
    if not explicit and key not in _PENDING and reply_key not in _REPLIES:return None
    if source_type!='user':return ui.card('請使用私人聊天室',['只能在一對一聊天室查看與修改工程進度。'])
    try:
        if not uid or not tasks.gateway('get_user',uid).get('user'):return ui.card('尚未綁定',['請使用建置者提供的啟用碼。'])
        if event_id and reply_key in _REPLIES:return _REPLIES[reply_key]['reply']
        if text=='取消流程編輯':
            p=_PENDING.pop(key,None)
            return ui.card('已取消',['原資料保留。'],[('回到案場','工程案件 '+p['case_id'])] if p else [('案件總覽','案件總覽')])
        if text=='確認流程編輯':
            p=_PENDING.get(key)
            if not p or not p.get('preview'):return ui.card('編輯已到期',['請重新選擇階段或完工日期。'],[('案件總覽','案件總覽')])
            if p['kind']=='note':
                ui.api('workflow_note',uid,event_id,case_id=p['case_id'],phase=p['phase'],note=p['note'],expected_note=p['expected_note'])
                result=ui.card('備註已儲存',[LABELS[p['phase']]],[('查看階段','工程流程 '+p['case_id']+' '+p['phase'])])
            else:
                ui.api('workflow_finish',uid,event_id,case_id=p['case_id'],expected_finish=p['expected_finish'])
                result=ui.card('完工日期已更新',[(p['expected_finish'] or '未設定').replace('-','/')],[('回到案場','工程案件 '+p['case_id'])])
            _PENDING.pop(key,None)
        elif key in _PENDING and not explicit:
            result=editing(uid,text)
        else:
            if explicit:_PENDING.pop(key,None)
            result=route(uid,text,event_id)
        if result is not None and event_id:_REPLIES[reply_key]={'until':now+1200,'reply':result}
        return result
    except (ValueError,KeyError,StopIteration):return ui.card('請重新選擇',['請從案件卡片選擇階段。'],[('案件總覽','案件總覽')])
    except tasks.InputError as exc:return ui.card('尚未更新',[str(exc)],[('案件總覽','案件總覽')])
    except tasks.StorageError:return ui.card('暫時無法存取',['這次操作未確認完成，請稍後重新查看。'])


def route(uid,text,event_id):
    if text in ('生活助理','工程秘書'):
        return ui.message('工程秘書',[ui.bubble('工程秘書',[ui.tx('看大階段、記備註，掌握每個案場進度。')],
            [('工程進度','案件總覽'),('今天安排','今天'),('新增案場','新增案件')])],[('更多','工程更多')])
    if text in ('工程更多','更多功能','工程新增'):
        return ui.card('更多功能',[],[('本週行程','本周'),('提醒設定','提醒設定'),('使用說明','工程說明'),('回首頁','工程秘書')])
    if text in ('案件總覽','工程總覽','工程待辦','報價追蹤','工程進度','新增工程事項'):return overview(uid)
    if text=='待驗收':return overview(uid,acceptance_only=True)
    if text.startswith(('工程流程總覽 ','工程總覽 ')):return overview(uid,int(text.split()[-1]))
    if text.startswith(('工程驗收進度頁 ','工程待驗收頁 ')):return overview(uid,int(text.split()[-1]),True)
    if text.startswith('案件 '):return detail(uid,ui.select_case(uid,text[3:].strip())['id'])
    if text.startswith(('工程案件 ','工程階段 ','工程全部階段 ','工程案件待辦 ','工程案件清單 ','工程新增事項 ')):
        return detail(uid,ui.case_id(text.split()[1]))
    if text.startswith(('工程待辦操作 ','工程清單 ')):return overview(uid)
    if text.startswith('工程案件資料 '):
        c=get_case(uid,ui.case_id(text.split()[-1]))
        return ui.card(c['name'],['地點：'+(c.get('location') or '待補'),'工項：'+(c.get('scope') or '待補')],
                       [('案場行程','工程行程 '+c['id']),('回到進度','工程案件 '+c['id'])])
    if text.startswith('工程流程 '):
        _,key,phase=text.split();return phase_card(uid,ui.case_id(key),phase)
    if text.startswith('工程流程狀態 '):
        _,key,phase=text.split();c=get_case(uid,ui.case_id(key));s=next(s for s in phases(c) if s['key']==phase)
        return ui.card('設定'+LABELS[phase]+'的狀態',[c['name'],'目前：'+s['status']],
            [(v,'確認階段狀態 '+key+' '+phase+' '+v) for v in STATES if v!=s['status']]+[('返回','工程流程 '+key+' '+phase)])
    if text.startswith('確認階段狀態 '):
        _,key,phase,state=text.split()
        if phase not in LABELS or state not in STATES:raise tasks.InputError('請使用狀態按鈕。')
        ui.api('workflow_status',uid,event_id,case_id=ui.case_id(key),phase=phase,status=state)
        return ui.card('階段狀態已更新',[LABELS[phase]+' · '+state],[('查看工程進度','工程案件 '+key)])
    if text.startswith('工程流程備註 '):
        _,key,phase=text.split();return save_note_prompt(uid,ui.case_id(key),phase)
    if text.startswith('工程完工日期 '):
        key=ui.case_id(text.split()[-1]);c=get_case(uid,key)
        _PENDING[(tenant_id(),uid)]={'kind':'finish','case_id':key,'until':time.monotonic()+1200}
        return ui.card('預計哪一天完工？',[c['name'],finish_label(c),'請輸入日期，例如：10/30'],[('不設日期','不設日期'),('取消','取消流程編輯')])
    if text.startswith(('工程進度 ','確認工程進度 ')):
        # Old cards now open the new stage view; never overwrite all seven phases.
        name=text.split(' ',1)[1].split('｜',1)[0]
        try:key=ui.case_id(name)
        except tasks.InputError:key=ui.select_case(uid,name)['id']
        return detail(uid,key)
    if text.startswith(('工程事項 ','確認工程事項 ')):
        return ui.card('事項改記在階段備註',['請選擇案場，再點相應階段填備註。'],[('選擇案場','案件總覽')])
    if text=='工程說明':
        return ui.card('七階段怎麼用？',['1. 選一個案場，看流程進度條。','2. 點階段，設定未開始、進行中、已完成或不適用。',
            '3. 缺材料、客戶交代事項直接寫在階段備註。','預計完工日另外設定；進度條表示流程完成度，不是實際施工量。'],[('開始查看','案件總覽')])
    return None
