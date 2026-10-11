"""Shared appointment layout, including retained times in older invalid-date drafts."""
import re
from lifeos_calendar_list import CLOCK


def txt(value,size='sm',color='#263F3C',bold=False):
    result={'type':'text','text':value or '—','size':size,'color':color,'wrap':True}
    if bold:result['weight']='bold'
    return result


def appointment_block(e,index,actions=None):
    # Older drafts kept original text but discarded parsed times for invalid dates.
    clocks=e.get('times') or [f'{int(m[1]):02d}:{int(m[2]):02d}' for m in CLOCK.finditer(e['title'])]
    name=CLOCK.sub('',e['title'])
    name=re.sub(r'全天|上午|下午|晚上|中午|凌晨|早上','',name).strip(' ～~－-–—到至')
    when='全天' if e['kind']=='all_day' else ('～'.join(clocks) if clocks else '未提供時間')
    if len(clocks)==1:when+=' 開始'
    problems=[]
    if e.get('date_problem'):problems.append('日期待確認')
    if e.get('incomplete') or e.get('needs_name'):problems.append('名稱待補完整')
    valid_range=len(clocks)==2 and all(int(t.split(':')[0])<24 and int(t.split(':')[1])<60 for t in clocks) and clocks[1]>clocks[0]
    notes=' '.join(e.get('notes',[]))
    known_time_problem=any(word in notes for word in ('上午或下午','上午／下午','時間的關係不明'))
    if len(clocks)==1:problems.append('缺結束時間')
    elif e['kind']=='needs_time' and not (e.get('date_problem') and valid_range and not known_time_problem):
        notes=' '.join(e.get('notes',[]))
        if clocks and any(int(t.split(':')[0])>=24 or int(t.split(':')[1])>=60 for t in clocks):problem='時間無效，請重新提供'
        elif len(clocks)==2 and clocks[1]<=clocks[0]:problem='結束早於開始，請確認起訖時間'
        elif '上午或下午' in notes or '上午／下午' in notes:problem='請確認上午或下午'
        elif not clocks and re.search(r'(?<![A-Za-z])[FB](?![A-Za-z])|小孟',e['title'],re.I):problem='缺開始時間'
        else:problem='缺開始與結束時間'
        problems.append(problem)
    contents=[txt(f"第 {index+1} 筆｜{name or '名稱待補'}",'lg',bold=True),
        txt('目前時間｜'+when,'sm','#66716E')]
    if e.get('imported'):contents.append(txt('已加入日曆','sm','#30715B'))
    elif problems:
        contents.extend(txt('待補｜'+p,'md','#B3261E',True) for p in problems)
    else:contents.append(txt('資料齊全，待確認','sm','#30715B'))
    if actions:contents.append({'type':'box','layout':'horizontal','contents':actions})
    return {'type':'box','layout':'vertical','spacing':'md','paddingAll':'16px','cornerRadius':'10px',
            'backgroundColor':'#F6F3EE' if problems else '#F4F7F5','contents':contents}
