import os
import json
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
    FlexContainer
)
from linebot.v3.webhooks import MessageEvent, TextMessageContent

app = Flask(__name__)

configuration = Configuration(access_token=os.getenv('LINE_CHANNEL_ACCESS_TOKEN'))
handler = WebhookHandler(os.getenv('LINE_CHANNEL_SECRET'))

CASE_LIST = [
    {"case": "case1", "keyword": "小如如", "alt": "小如如｜MR.主理人"},
    {"case": "case2", "keyword": "鍾師富", "alt": "鍾師富｜詠順工程行老闆"},
    {"case": "case3", "keyword": "emma", "alt": "emma｜大象木地板"},
    {"case": "case4", "keyword": "傑哥", "alt": "蘇祺傑｜傑出油漆工程行"},
    {"case": "case5", "keyword": "一昌哥", "alt": "蔡一昌｜平衡之道-財務規劃師"},
    {"case": "case6", "keyword": "寧寧", "alt": "寧寧｜雅如詩品牌經營人"},
    {"case": "case7", "keyword": "雙雙", "alt": "品雙｜葡眾健康顧問"},
    {"case": "case8", "keyword": "林威", "alt": "林威｜amomris業務經理"},
]


def load_flex(filepath):
    base_dir = os.path.dirname(os.path.abspath(__file__))
    full_path = os.path.join(base_dir, "templates", filepath)
    print(f"DEBUG: 正在嘗試讀取: {full_path}")
    if not os.path.exists(full_path):
        print(f"ERROR: 找不到檔案 {full_path}")
        return None
    with open(full_path, "r", encoding="utf-8") as f:
        return json.load(f)


def load_liff(filepath):
    base_dir = os.path.dirname(os.path.abspath(__file__))
    full_path = os.path.join(base_dir, "templates", filepath)
    with open(full_path, "r", encoding="utf-8") as f:
        return f.read()


@app.route("/cases")
def cases():
    rows = ""
    for c in CASE_LIST:
        rows += f"""
        <tr>
            <td>{c['case']}</td>
            <td>{c['keyword']}</td>
            <td>{c['alt']}</td>
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
            td {{ padding: 12px 16px; border-bottom: 1px solid #f0e8d8; font-size: 14px; }}
            tr:last-child td {{ border-bottom: none; }}
            tr:hover td {{ background: #fdf6ec; }}
        </style>
    </head>
    <body>
        <h1>MR. Bot 案例對照表</h1>
        <p>共 {len(CASE_LIST)} 個案例</p>
        <table>
            <tr>
                <th>Case</th>
                <th>關鍵字</th>
                <th>Alt Text</th>
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


@app.route("/liff/case1/luru")
def liff_luru():
    content = load_liff("case1/liff_luru.html")
    return content, 200, {"Content-Type": "text/html; charset=utf-8"}


@app.route("/liff/case2/chung")
def liff_chung():
    content = load_liff("case2/liff_chung.html")
    return content, 200, {"Content-Type": "text/html; charset=utf-8"}


@app.route("/liff/case3/emma")
def liff_emma():
    content = load_liff("case3/liff_emma.html")
    return content, 200, {"Content-Type": "text/html; charset=utf-8"}


@app.route("/liff/case4/jay")
def liff_jay():
    content = load_liff("case4/liff_jay.html")
    return content, 200, {"Content-Type": "text/html; charset=utf-8"}


@app.route("/liff/case5/yichang")
def liff_yichang():
    content = load_liff("case5/liff_yichang.html")
    return content, 200, {"Content-Type": "text/html; charset=utf-8"}


@app.route("/liff/case6/ningning")
def liff_ningning():
    content = load_liff("case6/liff_ningning.html")
    return content, 200, {"Content-Type": "text/html; charset=utf-8"}


@app.route("/liff/case7/shuangshuang")
def liff_shuangshuang():
    content = load_liff("case7/liff_shuangshuang.html")
    return content, 200, {"Content-Type": "text/html; charset=utf-8"}


@app.route("/liff/case8/LinWei")
def liff_linwei():
    content = load_liff("case8/liff_LinWei.html")
    return content, 200, {"Content-Type": "text/html; charset=utf-8"}


@handler.add(MessageEvent, message=TextMessageContent)
def handle_message(event):
    user_msg = event.message.text.strip()

    with ApiClient(configuration) as api_client:
        line_bot_api = MessagingApi(api_client)

        if "小如如" in user_msg:
            flex_data = load_flex("case1/card_luru.json")
            if flex_data:
                reply_msg = FlexMessage(
                    alt_text="小如如｜MR.主理人",
                    contents=FlexContainer.from_dict(flex_data)
                )
            else:
                reply_msg = TextMessage(text="抱歉，名片檔案讀取失敗")

        elif "鍾師富" in user_msg:
            flex_data = load_flex("case2/card_chung.json")
            if flex_data:
                reply_msg = FlexMessage(
                    alt_text="鍾師富｜詠順工程行老闆",
                    contents=FlexContainer.from_dict(flex_data)
                )
            else:
                reply_msg = TextMessage(text="抱歉，名片檔案讀取失敗")

        elif "emma" in user_msg or "大象木地板" in user_msg:
            flex_data = load_flex("case3/card_emma.json")
            if flex_data:
                reply_msg = FlexMessage(
                    alt_text="emma｜大象木地板",
                    contents=FlexContainer.from_dict(flex_data)
                )
            else:
                reply_msg = TextMessage(text="抱歉，名片檔案讀取失敗")

        elif "傑哥" in user_msg:
            flex_data = load_flex("case4/card_jay.json")
            if flex_data:
                reply_msg = FlexMessage(
                    alt_text="蘇祺傑｜傑出油漆工程行",
                    contents=FlexContainer.from_dict(flex_data)
                )
            else:
                reply_msg = TextMessage(text="抱歉，名片檔案讀取失敗")

        elif "一昌哥" in user_msg:
            flex_data = load_flex("case5/card_yichang.json")
            if flex_data:
                reply_msg = FlexMessage(
                    alt_text="蔡一昌｜平衡之道-財務規劃師",
                    contents=FlexContainer.from_dict(flex_data)
                )
            else:
                reply_msg = TextMessage(text="抱歉，名片檔案讀取失敗")

        elif "寧寧" in user_msg:
            flex_data = load_flex("case6/card_ningning.json")
            if flex_data:
                reply_msg = FlexMessage(
                    alt_text="寧寧｜雅如詩品牌經營人",
                    contents=FlexContainer.from_dict(flex_data)
                )
            else:
                reply_msg = TextMessage(text="抱歉，名片檔案讀取失敗")

        elif "雙雙" in user_msg:
            flex_data = load_flex("case7/card_shuangshuang.json")
            if flex_data:
                reply_msg = FlexMessage(
                    alt_text="品雙｜葡眾健康顧問",
                    contents=FlexContainer.from_dict(flex_data)
                )
            else:
                reply_msg = TextMessage(text="抱歉，名片檔案讀取失敗")

        elif "林威" in user_msg:
            flex_data = load_flex("case8/card_LinWei.json")
            if flex_data:
                reply_msg = FlexMessage(
                    alt_text="林威｜amomris業務經理",
                    contents=FlexContainer.from_dict(flex_data)
                )
            else:
                reply_msg = TextMessage(text="抱歉，名片檔案讀取失敗")

        else:
            reply_msg = TextMessage(
                text="請輸入關鍵字：\n"
                     "🔹 小如如\n"
                     "🔹 鍾師富\n"
                     "🔹 emma\n"
                     "🔹 傑哥\n"
                     "🔹 一昌哥\n"
                     "🔹 寧寧\n"
                     "🔹 雙雙\n"
                     "🔹 林威"
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
