import os
import json
from datetime import date
from flask import Flask, request, abort

from linebot.v3 import WebhookHandler
from linebot.v3.exceptions import InvalidSignatureError
from linebot.v3.messaging import (
    Configuration,
    ApiClient,
    MessagingApi,
    ReplyMessageRequest,
    TextMessage,
    FlexMessage,
    FlexContainer,
    QuickReply,
    QuickReplyItem,
    MessageAction
)
from linebot.v3.webhooks import MessageEvent, TextMessageContent

app = Flask(__name__)

configuration = Configuration(access_token=os.getenv('LINE_CHANNEL_ACCESS_TOKEN'))
handler = WebhookHandler(os.getenv('LINE_CHANNEL_SECRET'))

# ============================================================
# 案例資料
# num：對照 GitHub templates 資料夾 case1~case12 的編號（圓形標號用）
# name_keywords：任何輸入含有其中一個字串，或使用者輸入是其中一個字串的一部分，都算命中姓名
# industry_keywords：依分會名單的職業分類 / 公司名稱 / 額外指定關鍵字
# ============================================================
CASE_LIST = [
    {
        "case": "case1_小如如", "num": 1,
        "keyword": "小如如", "alt": "小如如｜MR.主理人",
        "name_keywords": ["小如如", "潘昱如", "潘 昱如"],
        "industry_keywords": ["顧問", "建築組", "個人服務", "美容美體", "如妍美學", "MN13"],
    },
    {
        "case": "case2_鍾師富", "num": 2,
        "keyword": "鍾師富", "alt": "鍾師富｜詠順工程行老闆",
        "name_keywords": ["鍾師富", "鍾一德", "鍾 一德"],
        "industry_keywords": ["建築組", "防水", "防風雨", "抓漏", "詠順工程行"],
    },
    {
        "case": "case3_emma", "num": 3,
        "keyword": "emma", "alt": "Emma｜大象木地板",
        "name_keywords": ["emma", "Emma", "吳玫勳", "吳 玫勳", "大象木地板"],
        "industry_keywords": ["建築組", "地板", "大象木地板", "廣德地板企業有限公司"],
    },
    {
        "case": "case4_傑哥", "num": 4,
        "keyword": "傑哥", "alt": "蘇祺傑｜傑出油漆工程行",
        "name_keywords": ["傑哥", "蘇祺傑", "蘇 祺傑"],
        "industry_keywords": ["建築組", "油漆", "粉刷師", "裝飾師", "傑出油漆"],
    },
    {
        "case": "case5_一昌", "num": 5,
        "keyword": "一昌", "alt": "蔡一昌｜平衡之道-財務規劃師",
        "name_keywords": ["一昌", "蔡一昌", "蔡 一昌"],
        "industry_keywords": ["房地產服務", "房地產投資", "財務規劃", "金融", "富屋"],
    },
    {
        "case": "case6_寧寧", "num": 6,
        "keyword": "寧寧", "alt": "寧寧｜雅如詩品牌經營人",
        "name_keywords": ["寧寧", "吳芷寧", "吳 芷寧"],
        "industry_keywords": ["個人服務", "頭皮理療", "SPA", "雅如詩", "森莫"],
    },
    {
        "case": "case7_雙雙", "num": 7,
        "keyword": "雙雙", "alt": "品雙｜葡眾健康顧問",
        "name_keywords": ["雙雙", "高品雙", "高 品雙"],
        "industry_keywords": ["健康", "保健", "保健品", "葡眾企業股份有限公司"],
    },
    {
        "case": "case8_林威", "num": 8,
        "keyword": "林威", "alt": "林威｜amomris業務經理",
        "name_keywords": ["林威"],
        "industry_keywords": ["健康", "保健食品", "amomris", "Amomris"],
    },
    {
        "case": "case9_昺諺", "num": 9,
        "keyword": "昺諺", "alt": "賴昺諺｜兆朋工程",
        "name_keywords": ["昺諺", "賴昺諺", "賴 昺諺"],
        "industry_keywords": ["建築組", "裝修", "改造", "清運", "兆朋工程股份有限公司"],
    },
    {
        "case": "case10_竹勝", "num": 10,
        "keyword": "竹勝", "alt": "周竹勝｜Paradiso爬樓梯創辦人",
        "name_keywords": ["竹勝", "周竹勝", "周 竹勝"],
        "industry_keywords": ["食品&飲料", "餐飲服務", "爬樓梯", "必昇有限公司"],
    },
    {
        "case": "case11_耀宗", "num": 11,
        "keyword": "耀宗", "alt": "王耀宗｜健康管理顧問",
        "name_keywords": ["耀宗", "王耀宗", "王 耀宗"],
        "industry_keywords": ["健康", "保健品", "蘆薈汁", "永久產品公司"],
    },
    {
        "case": "case12_凱程", "num": 12,
        "keyword": "凱程", "alt": "阮凱程｜耕家實業公司經理",
        "name_keywords": ["凱程", "阮凱程", "阮 凱程"],
        "industry_keywords": ["建築組", "裝修", "改造", "裝潢", "耕家"],
    },
    {
        "case": "case13_致為", "num": 13,
        "keyword": "致為", "alt": "黃致為｜蒔旭科技",
        "name_keywords": ["致為", "小捲", "黃致為", "黃 致為"],
        "industry_keywords": ["電腦&程式設計", "資訊科技顧問", "蒔旭有限公司"],
    },
    {
        "case": "case14_一晉", "num": 14,
        "keyword": "一晉", "alt": "邱一晉｜尚晉通信",
        "name_keywords": ["一晉", "邱一晉", "邱 一晉"],
        "industry_keywords": ["建築組", "電工", "電工-商業", "尚晉通科技企業社"],
    },
    {
        "case": "case16_齊齊", "num": 16,
        "keyword": "齊齊", "alt": "游宛齊｜馬鹿整合廣告",
        "name_keywords": ["齊齊", "游宛齊", "游 宛齊"],
        "industry_keywords": ["廣告&行銷", "廣告招牌輸出", "馬鹿整合廣告股份有限公司"],
    },
    {
        "case": "case17_重凱", "num": 17,
        "keyword": "重凱", "alt": "王重凱｜鉅沅管理顧問",
        "name_keywords": ["重凱", "王重凱", "王 重凱"],
        "industry_keywords": ["金融&保險", "金融投資", "金融", "鉅沅管理顧問有限公司"],
    },
]

# 展示清單：依你指定的順序顯示（小如如、寧寧、鍾師富、傑哥、林威、竹勝）
DEMO_KEYWORDS = ["小如如", "寧寧", "鍾師富", "傑哥", "林威", "竹勝"]

# 最近新增的名片：不用手動維護，會自動抓 CASE_LIST 裡 num 最大的兩筆
RECENTLY_ADDED_COUNT = 2

# 快速按鈕上顯示的廣泛產業分類：(按鈕上顯示的文字, 拿去比對 industry_keywords 用的關鍵字)
CATEGORY_QUICK_REPLIES = [
    ("建築組", "建築組"),
    ("健康", "健康"),
    ("美業", "個人服務"),
    ("食品飲料", "食品&飲料"),
    ("金融", "金融"),
]

# 姓名關鍵字 -> 案例資料，供快速查表使用
CASE_BY_KEYWORD = {c["keyword"]: c for c in CASE_LIST}

# 使用者是否處於「請輸入姓名或產業關鍵字」等待狀態（記憶體暫存，重啟會清空）
PENDING_SEARCH_USERS = set()

# 每位使用者最近查看過的名片關鍵字（記憶體暫存，重啟會清空），最新的排最前面
RECENT_VIEWS = {}
RECENT_VIEWS_LIMIT = 8


def record_view(user_id, case_item):
    """記錄使用者剛看過的名片，供「最近查看的名片」使用"""
    keyword_list = RECENT_VIEWS.setdefault(user_id, [])
    kw = case_item["keyword"]
    if kw in keyword_list:
        keyword_list.remove(kw)
    keyword_list.insert(0, kw)
    del keyword_list[RECENT_VIEWS_LIMIT:]


def load_flex(filepath):
    base_dir = os.path.dirname(os.path.abspath(__file__))
    full_path = os.path.join(base_dir, "templates", filepath)
    print(f"DEBUG: 正在嘗試讀取: {full_path}")
    if not os.path.exists(full_path):
        print(f"ERROR: 找不到檔案 {full_path}")
        return None
    with open(full_path, "r", encoding="utf-8") as f:
        content = f.read()
    today = date.today().strftime("%Y%m%d")
    content = content.replace("?raw=true", f"?raw=true&v={today}")
    return json.loads(content)


def load_liff(filepath):
    base_dir = os.path.dirname(os.path.abspath(__file__))
    full_path = os.path.join(base_dir, "templates", filepath)
    with open(full_path, "r", encoding="utf-8") as f:
        content = f.read()
    today = date.today().strftime("%Y%m%d")
    content = content.replace("?raw=true", f"?raw=true&v={today}")
    return content


def build_card_message(case_item):
    """讀取單一案例的名片 Flex Message，讀取失敗則回傳文字訊息"""
    filepath = f"{case_item['case']}/card_{case_item['case'].split('_', 1)[1]}.json"
    flex_data = load_flex(filepath)
    if flex_data:
        return FlexMessage(alt_text=case_item["alt"], contents=FlexContainer.from_dict(flex_data))
    return TextMessage(text="抱歉，名片檔案讀取失敗")


def search_cases(query):
    """依姓名關鍵字（全名/暱稱/部分字皆可）或產業關鍵字比對，回傳命中的案例清單"""
    query = query.strip()
    if not query:
        return []
    matched = []
    for case_item in CASE_LIST:
        all_keywords = case_item["name_keywords"] + case_item["industry_keywords"]
        hit = any((query in kw) or (kw in query) for kw in all_keywords)
        if hit:
            matched.append(case_item)
    return matched


def get_demo_cases():
    """依 DEMO_KEYWORDS 指定順序取出展示案例"""
    return [CASE_BY_KEYWORD[k] for k in DEMO_KEYWORDS if k in CASE_BY_KEYWORD]


def build_list_flex(alt_text, header_text, matched_cases):
    """
    橫列條目樣式（搜尋結果 / 展示清單共用）：
    - 標號用圓形，顯示 GitHub case 變數的編號（case1 -> 1）
    - 稱謂照 app.py 的 alt 顯示文字
    - 點擊該列會送出該案例的姓名關鍵字，觸發原本的名片回覆邏輯
    """
    rows = []
    for case_item in matched_cases:
        rows.append({
            "type": "box",
            "layout": "horizontal",
            "spacing": "md",
            "action": {
                "type": "message",
                "label": case_item["alt"][:20],
                "text": case_item["keyword"]
            },
            "contents": [
                {
                    "type": "box",
                    "layout": "vertical",
                    "width": "36px",
                    "height": "36px",
                    "cornerRadius": "18px",
                    "backgroundColor": "#473C38",
                    "justifyContent": "center",
                    "alignItems": "center",
                    "contents": [
                        {
                            "type": "text",
                            "text": str(case_item["num"]),
                            "color": "#F8EED2",
                            "size": "sm",
                            "weight": "bold",
                            "align": "center"
                        }
                    ]
                },
                {
                    "type": "box",
                    "layout": "vertical",
                    "flex": 1,
                    "contents": [
                        {
                            "type": "text",
                            "text": case_item["alt"],
                            "size": "sm",
                            "weight": "bold",
                            "color": "#473C38",
                            "wrap": True
                        },
                        {
                            "type": "text",
                            "text": "・".join(case_item["industry_keywords"][:3]),
                            "size": "xs",
                            "color": "#888888",
                            "wrap": True
                        }
                    ]
                }
            ]
        })
        rows.append({"type": "separator", "margin": "md"})

    if rows:
        rows.pop()  # 移除最後一條多餘分隔線

    bubble = {
        "type": "bubble",
        "size": "mega",
        "body": {
            "type": "box",
            "layout": "vertical",
            "backgroundColor": "#FFFFFF",
            "paddingAll": "16px",
            "spacing": "md",
            "contents": [
                {
                    "type": "text",
                    "text": header_text,
                    "size": "xs",
                    "color": "#888888"
                },
                {
                    "type": "box",
                    "layout": "vertical",
                    "spacing": "md",
                    "contents": rows
                }
            ]
        }
    }
    return FlexMessage(alt_text=alt_text, contents=FlexContainer.from_dict(bubble))


def build_search_result_flex(query, matched_cases):
    return build_list_flex(
        alt_text=f"{query} 搜尋結果",
        header_text=f"「{query}」搜尋結果，共 {len(matched_cases)} 筆",
        matched_cases=matched_cases
    )


def build_demo_flex():
    demo_cases = get_demo_cases()
    return build_list_flex(
        alt_text="案例展示清單",
        header_text=f"案例展示清單，共 {len(demo_cases)} 筆",
        matched_cases=demo_cases
    )


def get_recently_added_cases():
    """自動抓 CASE_LIST 裡 num 最大的幾筆，當作『最近新增』，不用手動維護清單"""
    return sorted(CASE_LIST, key=lambda c: c["num"], reverse=True)[:RECENTLY_ADDED_COUNT]


def build_recent_flex(user_id):
    """
    最近查看的名片：
    - 先放這位使用者最近實際看過 / 搜尋命中過的名片（最新在前）
    - 不足的話，補上最近新增的新案例（num 最大的幾筆）
    - 都沒有紀錄時，就只顯示最近新增的案例
    """
    recent_keywords = RECENT_VIEWS.get(user_id, [])
    recent_cases = [CASE_BY_KEYWORD[kw] for kw in recent_keywords if kw in CASE_BY_KEYWORD]

    for case_item in get_recently_added_cases():
        if case_item not in recent_cases:
            recent_cases.append(case_item)

    recent_cases = recent_cases[:RECENT_VIEWS_LIMIT]

    return build_list_flex(
        alt_text="最近查看的名片",
        header_text=f"最近查看的名片，共 {len(recent_cases)} 筆",
        matched_cases=recent_cases
    )


@app.route("/cases")
def cases():
    rows = ""
    for c in CASE_LIST:
        rows += f"""
        <tr>
            <td>{c['num']}</td>
            <td>{c['case']}</td>
            <td>{c['alt']}</td>
            <td>{'、'.join(c['name_keywords'])}</td>
            <td>{'、'.join(c['industry_keywords'])}</td>
        </tr>"""

    html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <title>MR. Bot 案例對照表</title>
        <style>
            body {{ font-family: sans-serif; padding: 30px; background: #f8eed2; color: #473c38; }}
            h1 {{ color: #473c38; font-size: 22px; margin-bottom: 8px; }}
            p {{ color: #888; font-size: 14px; margin-bottom: 20px; }}
            table {{ border-collapse: collapse; width: 100%; background: white; border-radius: 8px; overflow: hidden; box-shadow: 0 2px 8px rgba(0,0,0,0.08); }}
            th {{ background: #473c38; color: #f8eed2; padding: 12px 16px; text-align: left; font-size: 14px; }}
            td {{ padding: 12px 16px; border-bottom: 1px solid #f0e8d8; font-size: 13px; vertical-align: top; }}
            tr:last-child td {{ border-bottom: none; }}
            tr:hover td {{ background: #fdf6ec; }}
        </style>
    </head>
    <body>
        <h1>MR. Bot 案例對照表</h1>
        <p>共 {len(CASE_LIST)} 個案例｜展示清單：{'、'.join(DEMO_KEYWORDS)}</p>
        <table>
            <tr>
                <th>標號</th>
                <th>Case</th>
                <th>Alt Text</th>
                <th>姓名關鍵字</th>
                <th>產業關鍵字</th>
            </tr>
            {rows}
        </table>
    </body>
    </html>
    """
    return html, 200, {"Content-Type": "text/html; charset=utf-8"}


@app.route("/callback", methods=["POST"])
def callback():
    signature = request.headers.get('X-Line-Signature')
    body = request.get_data(as_text=True)
    app.logger.info("Request body: " + body)
    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        app.logger.error("Invalid signature.")
        abort(400)
    return 'OK'


@app.route("/liff/case1/小如如")
def liff_小如如():
    content = load_liff("case1_小如如/liff_小如如.html")
    return content, 200, {"Content-Type": "text/html; charset=utf-8"}


@app.route("/liff/case2/鍾師富")
def liff_鍾師富():
    content = load_liff("case2_鍾師富/liff_鍾師富.html")
    return content, 200, {"Content-Type": "text/html; charset=utf-8"}


@app.route("/liff/case3/emma")
def liff_emma():
    content = load_liff("case3_emma/liff_emma.html")
    return content, 200, {"Content-Type": "text/html; charset=utf-8"}


@app.route("/liff/case4/傑哥")
def liff_傑哥():
    content = load_liff("case4_傑哥/liff_傑哥.html")
    return content, 200, {"Content-Type": "text/html; charset=utf-8"}


@app.route("/liff/case5/一昌")
def liff_一昌():
    content = load_liff("case5_一昌/liff_一昌.html")
    return content, 200, {"Content-Type": "text/html; charset=utf-8"}


@app.route("/liff/case6/寧寧")
def liff_寧寧():
    content = load_liff("case6_寧寧/liff_寧寧.html")
    return content, 200, {"Content-Type": "text/html; charset=utf-8"}


@app.route("/liff/case7/雙雙")
def liff_雙雙():
    content = load_liff("case7_雙雙/liff_雙雙.html")
    return content, 200, {"Content-Type": "text/html; charset=utf-8"}


@app.route("/liff/case8/林威")
def liff_林威():
    content = load_liff("case8_林威/liff_林威.html")
    return content, 200, {"Content-Type": "text/html; charset=utf-8"}


@app.route("/liff/case9/昺諺")
def liff_昺諺():
    content = load_liff("case9_昺諺/liff_昺諺.html")
    return content, 200, {"Content-Type": "text/html; charset=utf-8"}


@app.route("/liff/case10/竹勝")
def liff_竹勝():
    content = load_liff("case10_竹勝/liff_竹勝.html")
    return content, 200, {"Content-Type": "text/html; charset=utf-8"}


@app.route("/liff/case11/耀宗")
def liff_耀宗():
    content = load_liff("case11_耀宗/liff_耀宗.html")
    return content, 200, {"Content-Type": "text/html; charset=utf-8"}


@app.route("/liff/case12/凱程")
def liff_凱程():
    content = load_liff("case12_凱程/liff_凱程.html")
    return content, 200, {"Content-Type": "text/html; charset=utf-8"}


@app.route("/liff/case13/致為")
def liff_致為():
    content = load_liff("case13_致為/liff_致為.html")
    return content, 200, {"Content-Type": "text/html; charset=utf-8"}


@app.route("/liff/case14/一晉")
def liff_一晉():
    content = load_liff("case14_一晉/liff_一晉.html")
    return content, 200, {"Content-Type": "text/html; charset=utf-8"}


@app.route("/liff/case16/齊齊")
def liff_齊齊():
    content = load_liff("case16_齊齊/liff_齊齊.html")
    return content, 200, {"Content-Type": "text/html; charset=utf-8"}


@app.route("/liff/case17/重凱")
def liff_重凱():
    content = load_liff("case17_重凱/liff_重凱.html")
    return content, 200, {"Content-Type": "text/html; charset=utf-8"}


@handler.add(MessageEvent, message=TextMessageContent)
def handle_message(event):
    user_msg = event.message.text.strip()
    user_id = event.source.user_id if hasattr(event.source, "user_id") else "unknown"

    with ApiClient(configuration) as api_client:
        line_bot_api = MessagingApi(api_client)

        # 1) 觸發「電子名片」搜尋流程，並附上「展示」+「最近查看」+ 常見產業分類快速按鈕
        if user_msg == "電子名片":
            PENDING_SEARCH_USERS.add(user_id)
            quick_items = [
                QuickReplyItem(action=MessageAction(label="展示", text="展示")),
                QuickReplyItem(action=MessageAction(label="最近查看的名片", text="最近查看的名片")),
            ]
            quick_items += [
                QuickReplyItem(action=MessageAction(label=label, text=label))
                for label, _ in CATEGORY_QUICK_REPLIES
            ]
            reply_msg = TextMessage(
                text="請輸入姓名或產業關鍵字搜尋\n或是點選下方按鈕快速查看",
                quick_reply=QuickReply(items=quick_items)
            )

        # 2) 點選「展示」按鈕（或直接手動輸入「展示」）→ 顯示展示清單
        elif user_msg == "展示":
            PENDING_SEARCH_USERS.discard(user_id)
            reply_msg = build_demo_flex()

        # 3) 點選「最近查看的名片」按鈕 → 顯示這位使用者最近看過／搜尋過的名片
        elif user_msg == "最近查看的名片":
            PENDING_SEARCH_USERS.discard(user_id)
            reply_msg = build_recent_flex(user_id)

        # 4) 點選產業分類快速按鈕（建築組／健康／美業／食品飲料／金融）
        elif user_msg in dict(CATEGORY_QUICK_REPLIES):
            PENDING_SEARCH_USERS.discard(user_id)
            search_keyword = dict(CATEGORY_QUICK_REPLIES)[user_msg]
            matched = search_cases(search_keyword)
            if matched:
                reply_msg = build_search_result_flex(user_msg, matched)
            else:
                reply_msg = TextMessage(text=f"目前「{user_msg}」還沒有對應的案例。")

        # 5) 使用者剛輸入過「電子名片」，這一則訊息視為搜尋關鍵字
        elif user_id in PENDING_SEARCH_USERS:
            PENDING_SEARCH_USERS.discard(user_id)
            matched = search_cases(user_msg)
            if not matched:
                reply_msg = TextMessage(text=f"找不到與「{user_msg}」相關的名片，請換個關鍵字再試一次。")
            elif len(matched) == 1:
                record_view(user_id, matched[0])
                reply_msg = build_card_message(matched[0])
            else:
                reply_msg = build_search_result_flex(user_msg, matched)

        # 6) 沿用原本：輸入姓名關鍵字直接顯示名片（維持既有使用習慣）
        else:
            direct_matches = [c for c in CASE_LIST if c["keyword"].lower() in user_msg.lower()
                               or user_msg.lower() in c["keyword"].lower()]
            if direct_matches:
                record_view(user_id, direct_matches[0])
                reply_msg = build_card_message(direct_matches[0])
            else:
                reply_msg = TextMessage(
                    text="輸入「電子名片」開始搜尋，或直接輸入姓名關鍵字：\n"
                         "🔹 小如如\n"
                         "🔹 鍾師富\n"
                         "🔹 emma\n"
                         "🔹 傑哥\n"
                         "🔹 一昌\n"
                         "🔹 寧寧\n"
                         "🔹 雙雙\n"
                         "🔹 林威\n"
                         "🔹 昺諺\n"
                         "🔹 竹勝\n"
                         "🔹 耀宗\n"
                         "🔹 凱程\n"
                         "🔹 致為\n"
                         "🔹 一晉\n"
                         "🔹 齊齊\n"
                         "🔹 重凱"
                )

        line_bot_api.reply_message(
            ReplyMessageRequest(
                reply_token=event.reply_token,
                messages=[reply_msg]
            )
        )


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
