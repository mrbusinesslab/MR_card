"""Seven-phase engineering view: stage status and notes, no task board."""
import time
import re
from datetime import timedelta
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
    return [dict(key=k,status=stored.get(k,{}).get('status','未開始'),note=stored.get(k,{}).get('note',''),completed_on=stored.get(k,{}).get('completed_on')) for k,_ in PHASES]


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


def completion_label(s):
    if s['status']!='已完成':return ''
    try:
        day=datetime.fromisoformat(s.get('completed_on') or '').date()
        elapsed=(tasks.clock().date()-day).days
        if elapsed<0:return '完成日期待確認'
        return day.strftime('%Y/%m/%d')+' 完成 · '+('今天' if elapsed==0 else f'已過 {elapsed} 天')
    except (ValueError,TypeError):return '完成日期未記錄'


def context(c,phase=None):
    return c['name']+(' · '+LABELS[phase] if phase else '')


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
        cards.append(ui.bubble(c['name'],body,[('查看工程進度','工程案件 '+c['id'])],'示範案場' if c.get('demo') else '工程案場'))
    prefix='工程驗收進度頁 ' if acceptance_only else '工程流程總覽 '
    nav=[]
    if page>1:nav.append(('上一頁',prefix+str(page-1)))
    if page*5<len(rows):nav.append(('下一頁',prefix+str(page+1)))
    return ui.message('工程進度',cards,nav+[('回首頁','工程秘書')])


def detail(uid,key):
    c=get_case(uid,key)
    body=progress_bar(c)+[ui.tx(finish_label(c),'xs','#64748B')]
    for s in phases(c):
        left=ui.tx(LABELS[s['key']],'sm',bold=True);left['flex']=3
        right=ui.tx(s['status'],'xs',INKS.get(s['status'],'#64748B'),True);right.update(flex=2,align='end')
        row=[{'type':'box','layout':'horizontal','contents':[left,right]}]
        if s['status']=='已完成':row.append(ui.tx(completion_label(s),'xxs','#64748B'))
        body.append({'type':'box','layout':'vertical','spacing':'xs','paddingAll':'12px','cornerRadius':'8px',
                     'backgroundColor':'#F4F7F6','action':{'type':'message','label':LABELS[s['key']],
                     'text':'工程流程 '+key+' '+s['key']},'contents':row})
    return ui.message('查看工程進度',[ui.bubble('查看工程進度',body,
            [('設定預計完工日','工程完工日期 '+key),('地址與工項','工程案件資料 '+key)],c['name'])],
            [('案件總覽','案件總覽'),('回首頁','工程秘書')])


def phase_card(uid,key,phase):
    if phase not in LABELS:raise tasks.InputError('請點案件卡片中的階段。')
    c=get_case(uid,key);s=next(s for s in phases(c) if s['key']==phase)
    note=s.get('note') or '目前沒有備註。'
    if len(note)>1500:note=note[:1500]+'\n…備註較長，請精簡後再編輯。'
    body=[ui.tx(s['status'],'sm',INKS.get(s['status'],'#64748B'),True)]
    choices=[('變更狀態','工程流程狀態 '+key+' '+phase),('編輯備註','工程流程備註 '+key+' '+phase)]
    if s['status']=='已完成':
        body.append(ui.tx(completion_label(s),'xs','#64748B'))
        choices.append(('設定完成日期','工程完成日期 '+key+' '+phase))
    if s.get('note'):
        lines=note.splitlines()
        summary='\n'.join(lines[:2])[:80]
        clipped=len(lines)>2 or len(note)>80
        body += [ui.tx('備註','xs','#64748B'),ui.tx(summary+('…' if clipped else ''))]
        if clipped:choices.insert(1,('查看完整備註','工程完整備註 '+key+' '+phase))
    return ui.message(LABELS[phase],[ui.bubble(LABELS[phase],body,choices,c['name'])],
            [('查看工程進度','工程案件 '+key)])


def save_note_prompt(uid,key,phase):
    c=get_case(uid,key);s=next(s for s in phases(c) if s['key']==phase)
    _PENDING[(tenant_id(),uid)]={'kind':'note','case_name':c['name'],'case_id':key,'phase':phase,'expected_note':s.get('note',''),'until':time.monotonic()+1200}
    return ui.card('編輯備註',[context(c,phase),'輸入新備註，儲存後取代原內容。'],
                   [('清空備註','清空備註'),('取消編輯','取消流程編輯')])


def editing(uid,text):
    p=_PENDING[(tenant_id(),uid)]
    if p.get('preview'):return ui.card('這筆內容尚未儲存',['請確認，或取消後重新輸入。'],
        [('確認儲存','確認流程編輯'),('取消','取消流程編輯')])
    if p['kind']=='note':
        note='' if text=='清空備註' else text.strip()
        if len(note)>1500:raise tasks.InputError('備註最多1500字，請精簡後再傳。')
        p.update(note=note,preview=True)
        return ui.card('確認備註',[p['case_name']+' · '+LABELS[p['phase']],note or '清空這個階段的備註。'],[('確認儲存','確認流程編輯'),('取消','取消流程編輯')])
    value=None
    if p['kind']=='completion' and text=='不設日期':raise tasks.InputError('請輸入實際完成日期。')
    if text!='不設日期':
        date_text=text
        if p['kind']=='completion':
            if text in ('昨天','前天'):
                date_text=(tasks.clock().date()-timedelta(days=1 if text=='昨天' else 2)).isoformat()
            elif re.fullmatch(r'\d{1,2}[月/\-]\d{1,2}(?:日|號)?',text):
                date_text=str(tasks.clock().year)+'/'+text
        stamp,spans=tasks.parse_date(date_text)
        rest=''.join(ch for i,ch in enumerate(date_text) if not any(a<=i<b for a,b in spans)).strip(' ，。前到至')
        if not stamp or rest:raise tasks.InputError('請提供日期，例如「10/30」或「下星期五」。')
        value=stamp.date().isoformat()
    if p['kind']=='completion':
        if datetime.fromisoformat(value).date()>tasks.clock().date():raise tasks.InputError('完成日期不能晚於今天。')
        p.update(completed_on=value,preview=True)
        return ui.card('確認完成日期',[p['case_name']+' · '+LABELS[p['phase']],value.replace('-','/')],
                       [('確認儲存','確認流程編輯'),('取消','取消流程編輯')])
    p.update(expected_finish=value,preview=True)
    return ui.card('確認預計完工日',[value.replace('-','/') if value else '取消預計完工日'],
                   [('確認儲存','確認流程編輯'),('取消','取消流程編輯')])


# Only narrow, unambiguous progress reports are interpreted as updates.
REPORT_PHASES={
 'appointment':('預約場勘','場勘','現勘'), 'quote':('報價',),
 'contract':('合約',), 'materials':('施工材料','備料','材料'),
 'construction':('開始施工','施工'), 'finishing':('完工收尾','收尾'),
 'acceptance':('驗收',)}

def report_date(text):
    today=tasks.clock().date()
    if '前天' in text:return today-timedelta(days=2)
    if '昨天' in text:return today-timedelta(days=1)
    hit=re.search(r'(?<!\d)(?:(20\d{2})[年/\-])?(\d{1,2})[月/\-](\d{1,2})(?:日|號)?',text)
    if not hit:return today
    try:return datetime(int(hit[1] or today.year),int(hit[2]),int(hit[3])).date()
    except ValueError:raise tasks.InputError('日期不存在，請重新輸入。')

def report_preview(uid,text):
    if not re.search(r'完成|完工|做完|弄好|好了|到齊|通過|開始|開工|進行中|正在',text):return None
    matches=[c for c in ui.cases(uid) if c['name'] in text]
    if not matches:return None
    if len(matches)!=1:return ui.card('請選一個案場',['這句話符合多個案場，請輸入完整案名。'],[('案件總覽','案件總覽')])
    case=matches[0]
    if re.search(r'還沒|尚未|未完成|沒完成|未到齊|沒到齊|未通過|沒通過|預計|可能|應該|如果|明天|後天|下週|下星期|下禮拜|將會|會再',text):
        return ui.card('先不更新進度',[case['name'],'我無法確認這件事已經完成。完成後再傳一句回報。'],[('查看工程進度','工程案件 '+case['id'])])
    aliases=[k for k,words in REPORT_PHASES.items() if any(word in text for word in words)]
    # "開始施工" belongs to construction, not appointment; "施工材料" belongs to materials.
    if '開始施工' in text and 'construction' in aliases:aliases=[k for k in aliases if k!='appointment']
    if '施工材料' in text and 'materials' in aliases:aliases=[k for k in aliases if k!='construction']
    if len(aliases)!=1:
        return ui.card('請選一個階段',[case['name'],'我不確定你要更新哪個階段。'],[('查看工程進度','工程案件 '+case['id'])])
    phase=aliases[0]
    # "開始施工" is explicitly in progress; completion words are never inferred from "開始".
    state='已完成' if re.search(r'完成|完工|做完|弄好|好了|到齊|通過',text) else '進行中'
    current=next(x for x in phases(case) if x['key']==phase)
    if state==current['status']:
        return ui.card('狀態沒有變動',[context(case,phase),'目前已經是'+state+'。'],[('查看階段','工程流程 '+case['id']+' '+phase)])
    done=report_date(text) if state=='已完成' else None
    if done and done>tasks.clock().date():raise tasks.InputError('完成日期不能晚於今天。')
    pending={'kind':'report','case_id':case['id'],'case_name':case['name'],'phase':phase,'status':state,
             'expected_status':current['status'],'completed_on':done.isoformat() if done else None,'until':time.monotonic()+1200}
    _PENDING[(tenant_id(),uid)]=pending
    lines=[context(case,phase),'目前：'+current['status']+' → '+state]
    if done:lines.append('完成日：'+done.strftime('%Y/%m/%d'))
    return ui.card('確認回報進度',lines,[('確認更新','確認回報進度'),('取消','取消流程編輯')])

def report_saved(uid,p,event_id):
    values={'case_id':p['case_id'],'phase':p['phase'],'status':p['status'],'expected_status':p['expected_status']}
    if p['completed_on']:values['completed_on']=p['completed_on']
    updated=ui.api('workflow_status',uid,event_id,**values)['case']
    rows,done,total,current=progress(updated)
    lines=[context(updated,p['phase'])+'：'+p['status']]
    if p['completed_on']:lines[0]+='（'+p['completed_on'].replace('-','/')+'）'
    lines.append('流程完成 '+str(done)+'／'+str(total)+' 階段')
    if current:lines.append('接下來：'+LABELS[current['key']])
    return ui.card('進度已更新',lines,[('查看工程進度','工程案件 '+p['case_id'])])


def handle(uid,text,event_id=None,source_type='user'):
    if getenv('LIFEOS_ENGINEERING_WORKFLOW')!='1':return None
    now=time.monotonic();key=(tenant_id(),uid);reply_key=(*key,event_id)
    for cache in (_PENDING,_REPLIES):
        for k,v in list(cache.items()):
            if v['until']<now:cache.pop(k,None)
    menus=('生活助理','工程秘書','案件總覽','工程總覽','工程待辦','報價追蹤','待驗收','工程更多','更多功能','工程新增',
           '工程說明','工程進度','回報進度','確認回報進度','新增案件','新增工程事項','取消流程編輯','確認流程編輯')
    prefixes=('工程流程 ','工程流程總覽 ','工程流程狀態 ','工程流程備註 ','確認階段狀態 ','工程完工日期 ',
              '工程完成日期 ','工程完整備註 ','工程案件 ','案件 ','工程階段 ','工程全部階段 ','工程案件待辦 ','工程案件清單 ','工程案件資料 ',
              '工程新增事項 ','工程待辦操作 ','工程清單 ','工程總覽 ','工程待驗收頁 ','工程驗收進度頁 ',
              '工程進度 ','確認工程進度 ','工程事項 ','確認工程事項 ')
    explicit=text in menus or text.startswith(prefixes)
    if not explicit and key not in _PENDING and reply_key not in _REPLIES and not re.search(r'完成|完工|做完|弄好|好了|到齊|通過|開始|開工|進行中|正在',text):return None
    if source_type!='user':return ui.card('請使用私人聊天室',['只能在一對一聊天室查看與修改工程進度。'])
    try:
        if not uid or not tasks.gateway('get_user',uid).get('user'):return ui.card('尚未綁定',['請使用建置者提供的啟用碼。'])
        if event_id and reply_key in _REPLIES:return _REPLIES[reply_key]['reply']
        if text=='確認回報進度':
            p=_PENDING.get(key)
            if not p or p['kind']!='report':return ui.card('回報已到期',['請重新傳一次進度。'],[('回首頁','工程秘書')])
            result=report_saved(uid,p,event_id)
            _PENDING.pop(key,None)
            if event_id:_REPLIES[reply_key]={'until':now+1200,'reply':result}
            return result
        if text=='取消流程編輯':
            p=_PENDING.pop(key,None)
            return ui.card('已取消',['原資料保留。'],[('回到案場','工程案件 '+p['case_id'])] if p else [('案件總覽','案件總覽')])
        if text=='確認流程編輯':
            p=_PENDING.get(key)
            if not p or not p.get('preview'):return ui.card('編輯已到期',['請重新選擇階段或完工日期。'],[('案件總覽','案件總覽')])
            if p['kind']=='note':
                ui.api('workflow_note',uid,event_id,case_id=p['case_id'],phase=p['phase'],note=p['note'],expected_note=p['expected_note'])
                result=phase_card(uid,p['case_id'],p['phase'])
            elif p['kind']=='completion':
                ui.api('workflow_status',uid,event_id,case_id=p['case_id'],phase=p['phase'],status='已完成',
                       completed_on=p['completed_on'],expected_status='已完成')
                result=phase_card(uid,p['case_id'],p['phase'])
            else:
                ui.api('workflow_finish',uid,event_id,case_id=p['case_id'],expected_finish=p['expected_finish'])
                result=ui.card('完工日期已更新',[(p['expected_finish'] or '未設定').replace('-','/')],[('回到案場','工程案件 '+p['case_id'])])
            _PENDING.pop(key,None)
        elif key in _PENDING and not explicit:
            if _PENDING[key]['kind']=='report':
                _PENDING.pop(key,None)
                result=report_preview(uid,text)
                if result is None:result=ui.card('請重新回報進度',['例如：林小姐廚房材料到齊了。'],[('取消','取消流程編輯')])
            else:result=editing(uid,text)
        else:
            if explicit:_PENDING.pop(key,None)
            result=route(uid,text,event_id)
            if result is None:result=report_preview(uid,text)
        if result is not None and event_id:_REPLIES[reply_key]={'until':now+1200,'reply':result}
        return result
    except (ValueError,KeyError,StopIteration):return ui.card('請重新選擇',['請從案件卡片選擇階段。'],[('案件總覽','案件總覽')])
    except tasks.InputError as exc:return ui.card('尚未更新',[str(exc)],[('案件總覽','案件總覽')])
    except tasks.StorageError:return ui.card('暫時無法存取',['這次操作未確認完成，請稍後重新查看。'])


def route(uid,text,event_id):
    if text in ('生活助理','工程秘書'):
        return ui.message('工程秘書',[ui.bubble('工程秘書',[],
            [('回報進度','回報進度'),('工程進度','案件總覽'),('今天安排','今天')])],[('更多','工程更多')])
    if text=='回報進度':
        return ui.card('回報進度',['直接傳一句話，例如：','陳先生浴室報價完成了','張先生辦公室昨天驗收通過'],[('工程進度','案件總覽')])
    if text in ('工程更多','更多功能','工程新增'):
        return ui.card('更多功能',[],[('新增案場','新增案件'),('本週行程','本周'),('提醒設定','提醒設定'),('使用說明','工程說明'),('回首頁','工程秘書')])
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
        return ui.card('地址與工項',[c['name'],'地點：'+(c.get('location') or '待補'),'工項：'+(c.get('scope') or '待補')],
                       [('案場行程','工程行程 '+c['id']),('回到進度','工程案件 '+c['id'])])
    if text.startswith('工程流程 '):
        _,key,phase=text.split();return phase_card(uid,ui.case_id(key),phase)
    if text.startswith('工程流程狀態 '):
        _,key,phase=text.split();c=get_case(uid,ui.case_id(key));s=next(s for s in phases(c) if s['key']==phase)
        return ui.card('變更狀態',[context(c,phase),'目前：'+s['status']],
            [(v,'確認階段狀態 '+key+' '+phase+' '+v) for v in STATES if v!=s['status']]+[('返回','工程流程 '+key+' '+phase)])
    if text.startswith('確認階段狀態 '):
        _,key,phase,state=text.split()
        if phase not in LABELS or state not in STATES:raise tasks.InputError('請使用狀態按鈕。')
        ui.api('workflow_status',uid,event_id,case_id=ui.case_id(key),phase=phase,status=state)
        return phase_card(uid,key,phase)
    if text.startswith('工程完整備註 '):
        _,key,phase=text.split();c=get_case(uid,ui.case_id(key));s=next(s for s in phases(c) if s['key']==phase)
        # Notes are editable up to 1500 chars; migrated notes may be longer.
        note=s.get('note') or '目前沒有備註。'
        chunks=[note[i:i+1500] for i in range(0,len(note),1500)]
        return ui.message('查看完整備註',[ui.bubble('查看完整備註',[ui.tx(chunk)],None,context(c,phase)) for chunk in chunks[:3]],
                          [('返回階段','工程流程 '+key+' '+phase)])
    if text.startswith('工程完成日期 '):
        _,key,phase=text.split();c=get_case(uid,ui.case_id(key));s=next(s for s in phases(c) if s['key']==phase)
        if s['status']!='已完成':raise tasks.InputError('請先將這個階段設為已完成。')
        _PENDING[(tenant_id(),uid)]={'kind':'completion','case_name':c['name'],'case_id':key,'phase':phase,'until':time.monotonic()+1200}
        return ui.card('設定完成日期',[context(c,phase),completion_label(s),'請輸入實際完成日，例如：10/20'],
                       [('取消','取消流程編輯')])
    if text.startswith('工程流程備註 '):
        _,key,phase=text.split();return save_note_prompt(uid,ui.case_id(key),phase)
    if text.startswith('工程完工日期 '):
        key=ui.case_id(text.split()[-1]);c=get_case(uid,key)
        _PENDING[(tenant_id(),uid)]={'kind':'finish','case_name':c['name'],'case_id':key,'until':time.monotonic()+1200}
        return ui.card('設定預計完工日',[c['name'],finish_label(c),'請輸入日期，例如：10/30'],[('不設日期','不設日期'),('取消','取消流程編輯')])
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
