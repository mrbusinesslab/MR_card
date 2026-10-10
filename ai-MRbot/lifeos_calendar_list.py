"""Read-only review of dated calendar lists; no inferred appointments are saved."""
import re
from datetime import date

HEADER = re.compile(r'^(?:(\d{4})[年/.-])?(\d{1,2})(?:月|[/.-])(\d{1,2})日?\s*(?:[（(]\s*([一二三四五六日天])\s*[）)]|星期([一二三四五六日天]))?\s*$')
CLOCK = re.compile(r'(?<!\d)(\d{1,2})[:：](\d{2})(?!\d)')
TRUNCATED = re.compile(r'截圖.{0,5}不完整|文字不完整|內容不完整|[⋯…]|\.{3}')
WEEKDAYS = '一二三四五六日'


def clean_line(line):
    line = re.sub(r'\[([^\]]+)\]\([^)]*\)',r'\1',line)
    line = line.strip().rstrip('\\').strip()
    line = re.sub(r'^[📅🗓\ufe0f#\s]+','',line)
    line = re.sub(r'^(?:[-*•●▪]+\s*|\d+[.、]\s*)','',line)
    return line.strip('* ').strip()


def review_list(text, year):
    current = None
    entries = []
    errors = []
    headers = 0
    mismatched = False
    for raw in text.splitlines():
        line = clean_line(raw)
        if not line:
            continue
        if line in ('整理行程','行程清單','批次行程'):
            continue
        heading = HEADER.fullmatch(line.rstrip('：:'))
        if heading:
            headers += 1
            y,m,d,weekday,weekday_word = heading.groups()
            try:
                current = date(int(y or year),int(m),int(d))
            except ValueError:
                errors.append(line+'：日期無效，請更正。')
                current = None
                continue
            expected = weekday or weekday_word
            mismatched = bool(expected and ('日' if expected=='天' else expected)!=WEEKDAYS[current.weekday()])
            if mismatched:
                errors.append(line+'：日期與星期不一致，請確認年份／日期。')
            continue
        if current is None:
            if headers:
                errors.append('「'+line[:80]+'」沒有有效日期，請補日期。')
            continue
        if len(entries)>=30:
            return {'entries':entries,'errors':['一次最多整理30筆，請拆成幾段傳送。'],'limited':True}
        times = list(CLOCK.finditer(line))
        notes = []
        incomplete = bool(TRUNCATED.search(line))
        name = CLOCK.sub('',line)
        name = re.sub(r'[（(][^）)]*(?:不完整)[^）)]*[）)]','',name)
        name = re.sub(r'^\s*(?:到|至|～|~|－|-)+\s*','',name).strip()
        usable_name = re.sub(r'全天|上午|下午|晚上|中午|凌晨|早上','',name)
        if incomplete:
            notes.append('文字不完整，先保留原文，請補完整名稱／內容')
        if not re.search(r'[A-Za-z\u3400-\u9fff]',usable_name):
            notes.append('沒有可辨識的行程名稱，請補內容')
        valid_times = all(int(t[1])<24 and int(t[2])<60 for t in times)
        clocks = [f'{int(t[1]):02d}:{int(t[2]):02d}' for t in times]
        if not valid_times:
            kind='needs_time';notes.append('時間格式無效，請使用00:00～23:59')
        elif len(times)==1:
            kind='start_only'
            if len(times[0][1])==1 and int(times[0][1])<12 and not re.search(r'上午|早上|凌晨|下午|晚上|中午',line):
                notes.append('請確認上午或下午（可改用24小時制）')
            notes.append('有開始時間，缺結束時間')
        elif len(times)==2:
            separator=line[times[0].end():times[1].start()].strip()
            if not re.fullmatch(r'(?:到|至|～|~|－|-|–|—)',separator):
                kind='needs_time';notes.append('兩個時間的關係不明，請寫成開始～結束')
            elif clocks[1]<=clocks[0]:
                kind='needs_time';notes.append('結束時間沒有晚於開始，請確認是否跨日')
            elif any(len(t[1])==1 and int(t[1])<12 for t in times) and not re.search(r'上午|早上|凌晨|下午|晚上|中午',line):
                kind='needs_time';notes.append('請確認上午或下午（可改用24小時制）')
            elif re.search(r'下午|晚上|中午',line) and any(int(t[1])<12 for t in times):
                kind='needs_time';notes.append('請改用24小時制，避免上午／下午不明')
            else:
                kind='complete';notes.append('日期與時間齊全，待確認')
        elif len(times)>2:
            kind='needs_time';notes.append('有多個時間，請拆成各筆行程')
        elif re.search(r'全天',line):
            kind='all_day';notes.append('標示全天，待確認')
        elif re.search(r'休假|公休|放假',line):
            kind='all_day';notes.append('可設為全天，請確認')
        else:
            kind='needs_time';notes.append('需確認時間，或是否設為全天')
        if mismatched:
            notes.append('日期與星期需確認')
        entries.append({'date':current.isoformat(),'title':line,'kind':kind,'times':clocks,'notes':notes,'incomplete':incomplete})
    if not headers:
        return None
    return {'entries':entries,'errors':errors,'limited':False} if entries or errors else None


def reply_text(review):
    groups = [('all_day','全天候選'),('complete','日期與時間齊全'),('start_only','缺結束時間'),('needs_time','待補時間／內容')]
    lines=['行程清單｜辨識到'+str(len(review['entries']))+'筆','未標示年份時依今年整理，請核對年份與日期。','']
    for kind,label in groups:
        items=[e for e in review['entries'] if e['kind']==kind and not e['incomplete']]
        if not items:
            continue
        lines.append('【'+label+'】')
        for e in items:
            lines.append(e['date'].replace('-','/')+' '+e['title']+'\n'+ '；'.join(e['notes']))
        lines.append('')
    incomplete=[e for e in review['entries'] if e['incomplete']]
    if incomplete:
        lines.append('【文字不完整，先保留原文】')
        for e in incomplete:
            lines.append(e['date'].replace('-','/')+' '+e['title']+'\n'+'；'.join(e['notes']))
        lines.append('')
    if review['errors']:
        lines.extend(['【需確認】',*review['errors'],''])
    lines.append('以上尚未加入Google日曆。請補齊資料後重新貼上完整清單。\n這個功能目前只整理待確認項目；批次存檔尚未啟用。')
    result='\n'.join(lines)
    if len(result)>4500:
        return '清單較長，請拆成較短的段落傳送；這次沒有加入Google日曆。'
    return result
