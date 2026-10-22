"""Tenant-scoped engineering workflow using persisted cases and ordinary tasks."""
import hmac
import re
from datetime import datetime, timedelta
from uuid import UUID
from flask import request
import lifeos as tasks
import lifeos_calendar as calendar
from lifeos_settings import getenv

STAGES=('待場勘','待報價','待確認','待施工','施工中','待驗收','已結案')
KINDS=('報價','備料','施工','追加','驗收','請款','其他')
MENU=('生活助理','更多功能','工程秘書','工程總覽','案件總覽','工程待辦','報價追蹤','待驗收','工程說明','新增案件','新增工程事項','工程進度')


def card(title,lines,choices=None):
    return calendar.card(title,lines,choices=choices)


def api(action,uid,event_id=None,**values):
    result=tasks.gateway('engineering_'+action,uid,event_id,**values)
    if result.get('error'):
        messages={'not_found':'找不到可查看的案件，請重新開啟「案件總覽」。',
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


def overview(uid,filter_stage=None,page=1):
    rows=cases(uid)
    if filter_stage: rows=[c for c in rows if c['stage'] in filter_stage]
    if not rows: return card('案件總覽',['這個分類目前沒有案件。'],[('新增案件','新增案件'),('工程首頁','工程秘書')])
    page=max(1,min(page,(len(rows)+4)//5)); selected=rows[(page-1)*5:page*5]
    lines=['依案件整理進度與未完成事項｜第'+str(page)+'頁']
    for c in selected:
        lines.append(case_title(c)+'\n'+c['stage']+'｜未完成 '+str(c['open_tasks'])+' 項\n'+(c.get('location') or '尚未填寫地點'))
    choices=[(c['name'][:20],'工程案件 '+c['id']) for c in selected]
    if page*5<len(rows): choices.append(('下一頁','工程總覽 '+str(page+1)))
    choices.append(('工程首頁','工程秘書'))
    return card('工程案件總覽',lines,choices)


def detail(uid,key):
    result=api('detail',uid,case_id=key);c=result['case']
    open_tasks=[t for t in result['tasks'] if t['status'] not in tasks.CLOSED]
    lines=[case_title(c),'目前進度：'+c['stage'],'地點：'+(c.get('location') or '待補'),
           '工項：'+(c.get('scope') or '待補'),'未完成事項：'+str(len(open_tasks))+' 項']
    lines += ['#'+str(t['id'])+' '+t['title']+'\n'+t['kind']+'｜'+due(t.get('due_at'))+'｜'+t['status'] for t in open_tasks[:8]]
    if len(open_tasks)>8: lines.append('本卡列前8項，輸入「工程待辦」查看完整清單。')
    choices=[('更新案件進度','工程階段 '+key),('新增案件事項','工程新增事項 '+key),
             ('查看案件行程','工程行程 '+key),('案件總覽','案件總覽')]
    choices += [('處理 #'+str(t['id']),'待辦操作 '+str(t['id'])) for t in open_tasks[:4]]
    return card('案場詳情',lines,choices)


def board(uid,kind=None,page=1):
    result=tasks.gateway('list',uid)
    rows=[t for t in result.get('tasks',[]) if t.get('category','').startswith('工程／')]
    if kind: rows=[t for t in rows if t['category']=='工程／'+kind]
    page=max(1,min(page,max(1,(len(rows)+5)//6))); selected=rows[(page-1)*6:page*6]
    lines=['第'+str(page)+'頁｜'+str(len(rows))+'項未完成事項']
    lines += ['#'+str(t['id'])+' '+t['title']+'\n'+due(t.get('due_at'))+'｜'+t['status'] for t in selected]
    if not rows: lines.append('目前沒有未完成事項。')
    if result.get('truncated'): lines.append('資料較多，僅顯示系統目前取得的待辦。')
    choices=[('處理 #'+str(t['id']),'待辦操作 '+str(t['id'])) for t in selected]
    if page*6<len(rows): choices.append(('下一頁','工程清單 '+(kind or '全部')+' '+str(page+1)))
    choices.append(('工程首頁','工程秘書'))
    return card((kind+'追蹤') if kind else '工程待辦',lines,choices)


def handle(uid,text,event_id=None,source_type='user'):
    if getenv('LIFEOS_INDUSTRY')!='engineering': return None
    text=text.strip()
    prefixes=('工程案件 ','工程階段 ','工程進度 ','確認工程進度 ','案件 ','工程行程 ',
              '建立案件 ','確認建立案件 ','工程新增事項 ','工程事項 ','確認工程事項 ','工程總覽 ','工程清單 ')
    if text not in MENU and not text.startswith(prefixes): return None
    if source_type!='user': return card('請使用私人聊天室',['工程案件只能在一對一聊天室查看與修改。'])
    try:
        if not uid or not tasks.gateway('get_user',uid).get('user'):
            return card('工程秘書尚未綁定',['請使用建置者提供的一次性啟用碼。'])
        if text in ('生活助理','更多功能','工程秘書'):
            return card('工程秘書',['把案場安排、報價、備料與收尾事項放在一起。','【示範】代表虛構練習資料，可放心試用。'],
                [('案件總覽','案件總覽'),('今天行程','今天'),('本週行程','本周'),('工程待辦','工程待辦'),
                 ('報價追蹤','報價追蹤'),('待驗收案件','待驗收'),('新增案件','新增案件'),('操作說明','工程說明')])
        if text in ('工程總覽','案件總覽'): return overview(uid)
        if re.fullmatch(r'工程總覽 \d+',text): return overview(uid,page=int(text.split()[-1]))
        if text=='待驗收': return overview(uid,('待驗收',))
        if text=='工程待辦': return board(uid)
        if text=='報價追蹤': return board(uid,'報價')
        if text.startswith('工程清單 '):
            _,kind,page=text.split()
            return board(uid,None if kind=='全部' else kind,int(page))
        if text in ('工程說明','新增案件','新增工程事項','工程進度'):
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
            return card('更新案件進度',[case_title(c),'目前：'+c['stage'],'請選擇新階段。'],[(s,'工程進度 '+key+'｜'+s) for s in STAGES])
        if text.startswith(('工程進度 ','確認工程進度 ')):
            confirm=text.startswith('確認'); value=text.split(' ',1)[1]; name,stage=value.split('｜',1)
            try: key=str(UUID(name))
            except ValueError: key=select_case(uid,name.strip())['id']
            c=api('detail',uid,case_id=key)['case'];stage=stage.strip()
            if stage not in STAGES: raise tasks.InputError('請選擇：'+'／'.join(STAGES))
            if not confirm: return card('確認更新進度',[case_title(c),c['stage']+' → '+stage],
                [('確認更新','確認工程進度 '+key+'｜'+stage),('保留原進度','工程案件 '+key)])
            api('stage',uid,event_id,case_id=key,stage=stage)
            return detail(uid,key)
        if text.startswith(('建立案件 ','確認建立案件 ')):
            confirm=text.startswith('確認'); value=text.split(' ',1)[1];name,location,scope=(v.strip() for v in value.split('｜',2))
            if not name or len(name)>80 or len(location)>300 or len(scope)>500: raise tasks.InputError('案名最多80字、地點300字、工項500字，請勿留空案名。')
            command='確認建立案件 '+name+'｜'+location+'｜'+scope
            if len(command)>1000: raise tasks.InputError('案件內容太長，請精簡。')
            if not confirm: return card('確認建立工程案件',[name,'地點：'+location,'工項：'+scope,'初始進度：待場勘'],[('確認建立',command),('放棄','工程秘書')])
            c=api('create',uid,event_id,name=name,location=location,scope=scope)['case']
            return detail(uid,c['id'])
        if text.startswith('工程新增事項 '):
            c=api('detail',uid,case_id=case_id(text.split()[-1]))['case']
            return card('新增案件事項',[case_title(c),'請輸入：工程事項 '+c['name']+'｜備料｜明天下午五點前購買材料','類型：'+'／'.join(KINDS)])
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
            return detail(uid,c['id'])
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
            return {'industry':'engineering','case_count':len(rows),'demo_count':sum(bool(c.get('demo')) for c in rows),'ready':True}
        except (tasks.StorageError,tasks.InputError): return {'ready':False},503
