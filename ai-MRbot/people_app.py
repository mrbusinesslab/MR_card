import os
from flask import request, abort

import app as legacy
from people_lookup import find_people, get_person, available_categories, category_text

from linebot.v3 import WebhookHandler
from linebot.v3.exceptions import InvalidSignatureError
from linebot.v3.messaging import (
    ApiClient,
    MessagingApi,
    ReplyMessageRequest,
    TextMessage,
    FlexMessage,
    FlexContainer,
    QuickReply,
    QuickReplyItem,
    MessageAction,
)
from linebot.v3.webhooks import MessageEvent, TextMessageContent


app = legacy.app
configuration = legacy.configuration
handler = WebhookHandler(os.getenv("LINE_CHANNEL_SECRET"))


def normalize(text):
    return "".join(str(text or "").split()).lower()


def find_card_for_person(name):
    target = normalize(name)
    for case_item in legacy.CASE_LIST:
        names = [case_item["keyword"]] + case_item.get("name_keywords", [])
        if any(normalize(item) == target for item in names):
            return case_item
    return None


def resolve_people(query):
    """先查 Google Sheet 正式姓名；若輸入的是現有電子名片暱稱，再用 CASE_LIST 反查正式姓名。"""
    direct = find_people(query)
    if direct:
        return direct

    q = normalize(query)
    candidate_names = []
    for case_item in legacy.CASE_LIST:
        aliases = [case_item["keyword"]] + case_item.get("name_keywords", [])
        if any(q == normalize(alias) or q in normalize(alias) or normalize(alias) in q for alias in aliases):
            candidate_names.extend(case_item.get("name_keywords", []))

    results = []
    seen = set()
    for candidate in candidate_names:
        for person in find_people(candidate):
            name = person.get("姓名")
            if name and name not in seen:
                seen.add(name)
                results.append(person)
    return results[:5]


def build_person_menu(person):
    name = person["姓名"]
    collected = person.get("資料蒐集", {})
    company = collected.get("公司") or person.get("顧問快診", {}).get("公司") or person.get("盲蒐", {}).get("公司") or ""
    card_item = find_card_for_person(name)
    categories = available_categories(person, has_card=bool(card_item))

    rows = []
    for index, (key, label) in enumerate(categories, start=1):
        action_text = f"人物資料|{name}|{key}"
        rows.append({
            "type": "box",
            "layout": "horizontal",
            "paddingAll": "12px",
            "cornerRadius": "8px",
            "backgroundColor": "#F8F4EA",
            "action": {"type": "message", "label": label[:20], "text": action_text},
            "contents": [
                {"type": "text", "text": str(index), "size": "sm", "weight": "bold", "color": "#9A7B4F", "flex": 0},
                {"type": "text", "text": label, "size": "sm", "weight": "bold", "color": "#473C38", "margin": "md", "flex": 1},
                {"type": "text", "text": "›", "size": "md", "color": "#9A7B4F", "flex": 0},
            ],
        })

    bubble = {
        "type": "bubble",
        "size": "mega",
        "body": {
            "type": "box",
            "layout": "vertical",
            "paddingAll": "18px",
            "spacing": "md",
            "contents": [
                {"type": "text", "text": name, "size": "xl", "weight": "bold", "color": "#473C38"},
                {"type": "text", "text": company or "人物資料", "size": "sm", "color": "#888888", "wrap": True},
                {"type": "text", "text": "請選擇要查看的資料", "size": "xs", "color": "#AAAAAA", "margin": "sm"},
                {"type": "box", "layout": "vertical", "spacing": "sm", "contents": rows},
            ],
        },
    }
    return FlexMessage(alt_text=f"{name} 人物資料", contents=FlexContainer.from_dict(bubble))


def build_people_result(query, people):
    rows = []
    for person in people:
        name = person["姓名"]
        company = person.get("資料蒐集", {}).get("公司") or ""
        rows.append({
            "type": "box",
            "layout": "vertical",
            "paddingAll": "12px",
            "action": {"type": "message", "label": name[:20], "text": f"人物選單|{name}"},
            "contents": [
                {"type": "text", "text": name, "size": "sm", "weight": "bold", "color": "#473C38"},
                {"type": "text", "text": company, "size": "xs", "color": "#888888", "wrap": True},
            ],
        })
    bubble = {
        "type": "bubble",
        "size": "mega",
        "body": {
            "type": "box",
            "layout": "vertical",
            "paddingAll": "16px",
            "spacing": "sm",
            "contents": [
                {"type": "text", "text": f"「{query}」找到 {len(people)} 位", "size": "sm", "weight": "bold", "color": "#473C38"},
                {"type": "box", "layout": "vertical", "spacing": "xs", "contents": rows},
            ],
        },
    }
    return FlexMessage(alt_text=f"{query} 人物搜尋結果", contents=FlexContainer.from_dict(bubble))


def person_category_reply(name, category):
    person = get_person(name)
    if not person:
        return TextMessage(text=f"找不到「{name}」的最新資料，請重新搜尋。")

    if category == "card":
        case_item = find_card_for_person(name)
        if case_item:
            return legacy.build_card_message(case_item)
        return TextMessage(text=f"{name} 目前尚未建立電子名片。")

    text = category_text(person, category)
    if not text:
        return TextMessage(text=f"{name} 的這個分類目前沒有資料。")
    return TextMessage(text=text)


def reply(line_bot_api, event, message):
    line_bot_api.reply_message(
        ReplyMessageRequest(reply_token=event.reply_token, messages=[message])
    )


@app.route("/people-data-health")
def people_data_health():
    try:
        people = resolve_people("阮凱程")
        return {"ok": True, "people_lookup": len(people)}, 200
    except Exception as exc:
        return {"ok": False, "error": str(exc)}, 500


@handler.add(MessageEvent, message=TextMessageContent)
def handle_message(event):
    user_msg = event.message.text.strip()
    user_id = event.source.user_id if hasattr(event.source, "user_id") else "unknown"

    with ApiClient(configuration) as api_client:
        line_bot_api = MessagingApi(api_client)

        # 人物分類按鈕
        if user_msg.startswith("人物資料|"):
            parts = user_msg.split("|", 2)
            if len(parts) == 3:
                _, name, category = parts
                reply(line_bot_api, event, person_category_reply(name, category))
                return

        # 多筆人物搜尋結果點入
        if user_msg.startswith("人物選單|"):
            name = user_msg.split("|", 1)[1]
            try:
                person = get_person(name)
                message = build_person_menu(person) if person else TextMessage(text=f"找不到「{name}」的最新資料。")
            except Exception as exc:
                app.logger.exception("people lookup failed")
                message = TextMessage(text="人物資料目前讀取失敗，請稍後再試。")
            reply(line_bot_api, event, message)
            return

        # 原本的「電子名片」流程完整保留
        if user_msg == "電子名片":
            legacy.PENDING_SEARCH_USERS.add(user_id)
            quick_items = [
                QuickReplyItem(action=MessageAction(label="展示", text="展示")),
                QuickReplyItem(action=MessageAction(label="最近查看的名片", text="最近查看的名片")),
            ]
            quick_items += [
                QuickReplyItem(action=MessageAction(label=label, text=label))
                for label, _ in legacy.CATEGORY_QUICK_REPLIES
            ]
            message = TextMessage(
                text="請輸入姓名或產業關鍵字搜尋\n或是點選下方按鈕快速查看",
                quick_reply=QuickReply(items=quick_items),
            )
            reply(line_bot_api, event, message)
            return

        if user_msg == "展示":
            legacy.PENDING_SEARCH_USERS.discard(user_id)
            reply(line_bot_api, event, legacy.build_demo_flex())
            return

        if user_msg == "最近查看的名片":
            legacy.PENDING_SEARCH_USERS.discard(user_id)
            reply(line_bot_api, event, legacy.build_recent_flex(user_id))
            return

        if user_msg in dict(legacy.CATEGORY_QUICK_REPLIES):
            legacy.PENDING_SEARCH_USERS.discard(user_id)
            search_keyword = dict(legacy.CATEGORY_QUICK_REPLIES)[user_msg]
            matched = legacy.search_cases(search_keyword)
            message = legacy.build_search_result_flex(user_msg, matched) if matched else TextMessage(text=f"目前「{user_msg}」還沒有對應的案例。")
            reply(line_bot_api, event, message)
            return

        if user_id in legacy.PENDING_SEARCH_USERS:
            legacy.PENDING_SEARCH_USERS.discard(user_id)
            matched = legacy.search_cases(user_msg)
            if not matched:
                suggestions = legacy.fuzzy_search_cases(user_msg)
                message = legacy.build_suggestion_flex(user_msg, suggestions) if suggestions else TextMessage(text=f"找不到與「{user_msg}」相關的名片，請換個關鍵字再試一次。")
            elif len(matched) == 1:
                legacy.record_view(user_id, matched[0])
                message = legacy.build_card_message(matched[0])
            else:
                message = legacy.build_search_result_flex(user_msg, matched)
            reply(line_bot_api, event, message)
            return

        # 一般直接輸入姓名：改為人物資料分類選單
        try:
            people = resolve_people(user_msg)
        except Exception:
            app.logger.exception("live Google Sheet lookup failed")
            people = []

        if len(people) == 1:
            reply(line_bot_api, event, build_person_menu(people[0]))
            return
        if len(people) > 1:
            reply(line_bot_api, event, build_people_result(user_msg, people))
            return

        # 若 Google Sheet 沒命中，仍保留原本電子名片錯字推薦
        suggestions = legacy.fuzzy_search_cases(user_msg)
        if suggestions:
            reply(line_bot_api, event, legacy.build_suggestion_flex(user_msg, suggestions))
            return

        reply(line_bot_api, event, TextMessage(text="找不到這位人物的資料。你可以輸入完整姓名，或輸入「電子名片」搜尋名片。"))


def callback():
    signature = request.headers.get("X-Line-Signature")
    body = request.get_data(as_text=True)
    app.logger.info("Request body: " + body)
    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        app.logger.error("Invalid signature.")
        abort(400)
    return "OK"


# 覆蓋舊 app.py 註冊的 /callback view，不改 LIFF 與其他既有 route
app.view_functions["callback"] = callback
