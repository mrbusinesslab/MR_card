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


@handler.add(MessageEvent, message=TextMessageContent)
def handle_message(event):
    user_msg = event.message.text.strip()

    with ApiClient(configuration) as api_client:
        line_bot_api = MessagingApi(api_client)

        if "小如如" in user_msg:
            flex_data = load_flex("case1/card_luru.json")
            if flex_data:
                reply_msg = FlexMessage(
                    alt_text="MR.主理人",
                    contents=FlexContainer.from_dict(flex_data)
                )
            else:
                reply_msg = TextMessage(text="抱歉，名片檔案讀取失敗")

        elif "鍾師富" in user_msg:
            flex_data = load_flex("case2/card_chung.json")
            if flex_data:
                reply_msg = FlexMessage(
                    alt_text="詠順工程行老闆",
                    contents=FlexContainer.from_dict(flex_data)
                )
            else:
                reply_msg = TextMessage(text="抱歉，名片檔案讀取失敗")

        elif "大象木地板" in user_msg:
            flex_data = load_flex("case3/card_emma.json")
            if flex_data:
                reply_msg = FlexMessage(
                    alt_text="大象木地板闆娘",
                    contents=FlexContainer.from_dict(flex_data)
                )
            else:
                reply_msg = TextMessage(text="抱歉，名片檔案讀取失敗")

        elif "傑哥" in user_msg:
            flex_data = load_flex("case4/card_jay.json")
            if flex_data:
                reply_msg = FlexMessage(
                    alt_text="傑出油漆工程行創辦人",
                    contents=FlexContainer.from_dict(flex_data)
                )
            else:
                reply_msg = TextMessage(text="抱歉，名片檔案讀取失敗")

        elif "一昌哥" in user_msg:
            flex_data = load_flex("case5/card_yichang.json")
            if flex_data:
                reply_msg = FlexMessage(
                    alt_text="平衡之道-財務規劃師",
                    contents=FlexContainer.from_dict(flex_data)
                )
            else:
                reply_msg = TextMessage(text="抱歉，名片檔案讀取失敗")

        elif "寧寧" in user_msg:
            flex_data = load_flex("case6/card_ningning.json")
            if flex_data:
                reply_msg = FlexMessage(
                    alt_text="雅如詩品牌經營人",
                    contents=FlexContainer.from_dict(flex_data)
                )
            else:
                reply_msg = TextMessage(text="抱歉，名片檔案讀取失敗")

        elif "雙雙" in user_msg:
            flex_data = load_flex("case7/card_shuangshuang.json")
            if flex_data:
                reply_msg = FlexMessage(
                    alt_text="葡眾健康顧問",
                    contents=FlexContainer.from_dict(flex_data)
                )
            else:
                reply_msg = TextMessage(text="抱歉，名片檔案讀取失敗")

        else:
            reply_msg = TextMessage(text="請輸入關鍵字：\n🔹 小如如\n🔹 鍾師富\n🔹 大象木地板\n🔹 傑哥\n🔹 一昌哥\n🔹 寧寧\n🔹 雙雙")

        line_bot_api.reply_message(
            ReplyMessageRequest(
                reply_token=event.reply_token,
                messages=[reply_msg]
            )
        )


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
