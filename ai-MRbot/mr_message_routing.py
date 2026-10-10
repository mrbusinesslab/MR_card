"""Decide explicit chat intent before a stateful assistant consumes text."""
import re

LIFEOS_LABELS = frozenset(('個人助理','助理說明','生活助理','更多功能','我的待辦','全部待辦',
    '今天有哪些事','今天有什麼事','今天有哪些是','今天的事','今天','明天','本周','本週','本月',
    '逾期待辦','逾期事項','其他天的事','美容','商會','新增待辦','提醒設定','測試提醒',
    '開啟每日提醒','關閉每日提醒','停止延期','離開助理','回到小幫手',
    '確認','確認存檔','存檔','放棄草稿','取消草稿','Google日曆','新增行程','確認行程',
    '仍要新增行程','放棄行程','其他天的行程'))
LIFEOS_PREFIXES = ('啟用助理','待辦按鈕 ','待辦操作 ','延期 ','確認取消 ',
    '完成 ','取消 ','等待 ','開始 ','延後 ','行程 ','改期行程','分類行程 ',
    '詳情行程 ','選擇預約 ','確認取消行程')
PEOPLE_LABELS = frozenset(('電子名片','展示','最近查看的名片'))
PEOPLE_PREFIXES = ('查客戶 ','人物資料|','人物完整|','人物選單|','追蹤更新|')

def normalize(text):
    return ''.join(text.split()).lower()

def is_lifeos_command(text):
    return text in LIFEOS_LABELS or text.startswith(LIFEOS_PREFIXES) or bool(
        re.fullmatch(r'.+?(?:的預約|預約)?(?:改到|改期到)\s*.+',text)
        or re.fullmatch(r'取消\s*.+?(?:的預約|預約)',text))

def prefer_people(text, *, pending_search=False, names=(), categories=()):
    text=text.strip()
    if text in PEOPLE_LABELS or text.startswith(PEOPLE_PREFIXES):
        return True
    if normalize(text) in {normalize(name) for name in names}:
        return True
    if text in categories:
        return True
    return pending_search and not is_lifeos_command(text)
