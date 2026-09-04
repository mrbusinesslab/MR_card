from linebot.v3.messaging import TextMessage, FlexMessage, FlexContainer, QuickReply, QuickReplyItem, MessageAction

from mr_tracking import FIELD_OPTIONS, DISPLAY_FIELDS, format_tracking_record, update_tracking_field


_original_build_person_menu = None
_original_person_category_reply = None
_original_resolve_people = None


def _is_building_person(person):
    return any("BNI 建築組" in str(source) for source in person.get("來源", []))


def _tracking_row(name):
    return {
        "type": "box",
        "layout": "horizontal",
        "paddingAll": "12px",
        "cornerRadius": "8px",
        "backgroundColor": "#F8F4EA",
        "action": {"type": "message", "label": "MR品牌開發追蹤", "text": f"人物資料|{name}|tracking"},
        "contents": [
            {"type": "text", "text": "8", "size": "sm", "weight": "bold", "color": "#9A7B4F", "flex": 0},
            {"type": "text", "text": "MR品牌開發追蹤", "size": "sm", "weight": "bold", "color": "#473C38", "margin": "md", "flex": 1},
            {"type": "text", "text": "›", "size": "md", "color": "#9A7B4F", "flex": 0},
        ],
    }


def build_person_menu(module, person):
    message = _original_build_person_menu(person)
    if not _is_building_person(person):
        return message
    try:
        data = message.contents.to_dict()
        data["body"]["contents"][-1]["contents"].append(_tracking_row(person["姓名"]))
        return FlexMessage(alt_text=message.alt_text, contents=FlexContainer.from_dict(data))
    except Exception:
        # 若 SDK 物件格式不同，退回自建版，避免影響 1–7。
        return _build_menu_fallback(module, person)


def _build_menu_fallback(module, person):
    name = person["姓名"]
    collected = person.get("資料蒐集", {})
    company = collected.get("公司") or person.get("顧問快診", {}).get("公司") or person.get("盲蒐", {}).get("公司") or ""
    categories = module.available_categories(person, has_card=bool(module.find_card_for_person(name)))
    number_map = {"basic": 1, "service": 2, "links": 3, "contact": 4, "diagnosis": 5, "blind": 6, "card": 7}
    rows = []
    for key, label in categories:
        rows.append({
            "type": "box", "layout": "horizontal", "paddingAll": "12px", "cornerRadius": "8px", "backgroundColor": "#F8F4EA",
            "action": {"type": "message", "label": label[:20], "text": f"人物資料|{name}|{key}"},
            "contents": [
                {"type": "text", "text": str(number_map.get(key, "")), "size": "sm", "weight": "bold", "color": "#9A7B4F", "flex": 0},
                {"type": "text", "text": label, "size": "sm", "weight": "bold", "color": "#473C38", "margin": "md", "flex": 1},
                {"type": "text", "text": "›", "size": "md", "color": "#9A7B4F", "flex": 0},
            ],
        })
    rows.append(_tracking_row(name))
    bubble = {"type": "bubble", "size": "mega", "body": {"type": "box", "layout": "vertical", "paddingAll": "18px", "spacing": "md", "contents": [
        {"type": "text", "text": name, "size": "xl", "weight": "bold", "color": "#473C38"},
        {"type": "text", "text": company or "人物資料", "size": "sm", "color": "#888888", "wrap": True},
        {"type": "text", "text": "請選擇要查看的資料", "size": "xs", "color": "#AAAAAA", "margin": "sm"},
        {"type": "box", "layout": "vertical", "spacing": "sm", "contents": rows},
    ]}}
    return FlexMessage(alt_text=f"{name} 人物資料", contents=FlexContainer.from_dict(bubble))


def tracking_submenu(name):
    bubble = {
        "type": "bubble",
        "size": "mega",
        "body": {
            "type": "box", "layout": "vertical", "paddingAll": "18px", "spacing": "md",
            "contents": [
                {"type": "text", "text": f"{name}｜MR品牌開發追蹤", "size": "lg", "weight": "bold", "color": "#473C38", "wrap": True},
                {"type": "text", "text": "請選擇操作", "size": "xs", "color": "#999999"},
                {"type": "button", "style": "secondary", "height": "sm", "action": {"type": "message", "label": "查看目前記錄", "text": f"人物資料|{name}|tracking_view"}},
                {"type": "button", "style": "primary", "height": "sm", "action": {"type": "message", "label": "聊天更新清單", "text": f"人物資料|{name}|tracking_chat"}},
            ],
        },
    }
    return FlexMessage(alt_text=f"{name} MR品牌開發追蹤", contents=FlexContainer.from_dict(bubble))


def tracking_chat_menu(name):
    rows = []
    for field in DISPLAY_FIELDS:
        rows.append({
            "type": "button", "style": "secondary", "height": "sm",
            "action": {"type": "message", "label": field[:20], "text": f"人物資料|{name}|tracking_field:{field}"},
        })
    bubble = {
        "type": "bubble", "size": "mega",
        "body": {"type": "box", "layout": "vertical", "paddingAll": "18px", "spacing": "sm", "contents": [
            {"type": "text", "text": f"{name}｜聊天更新清單", "size": "lg", "weight": "bold", "color": "#473C38", "wrap": True},
            {"type": "text", "text": "選擇要更新的欄位", "size": "xs", "color": "#999999"},
            *rows,
        ]},
    }
    return FlexMessage(alt_text=f"{name} 聊天更新清單", contents=FlexContainer.from_dict(bubble))


def tracking_field_prompt(name, field):
    options = FIELD_OPTIONS.get(field)
    if options:
        items = [
            QuickReplyItem(action=MessageAction(label=value[:20], text=f"人物資料|{name}|tracking_set:{field}:{value}"))
            for value in options[:13]
        ]
        return TextMessage(text=f"請選擇「{field}」的新內容：", quick_reply=QuickReply(items=items))
    return TextMessage(
        text=(
            f"請回覆要寫入「{field}」的內容。\n\n"
            f"格式：\n追蹤更新|{name}|{field}|你的內容\n\n"
            f"例如：\n追蹤更新|{name}|{field}|10月再聯絡"
        )
    )


def tracking_set(name, field, value):
    try:
        update_tracking_field(name, field, value)
        return TextMessage(text=f"已更新 {name}\n{field}：{value}")
    except Exception as exc:
        return TextMessage(text=f"更新失敗：{exc}")


def person_category_reply(name, category):
    if category == "tracking":
        return tracking_submenu(name)
    if category == "tracking_view":
        try:
            return TextMessage(text=format_tracking_record(name))
        except Exception as exc:
            return TextMessage(text=f"追蹤紀錄目前讀取失敗：{exc}")
    if category == "tracking_chat":
        return tracking_chat_menu(name)
    if category.startswith("tracking_field:"):
        field = category.split(":", 1)[1]
        return tracking_field_prompt(name, field)
    if category.startswith("tracking_set:"):
        _, field, value = category.split(":", 2)
        return tracking_set(name, field, value)
    return _original_person_category_reply(name, category)


def resolve_people(query):
    if str(query).startswith("追蹤更新|"):
        parts = str(query).split("|", 3)
        if len(parts) == 4:
            _, name, field, value = parts
            result = tracking_set(name.strip(), field.strip(), value.strip())
            return [{"姓名": "__TRACKING_RESULT__", "_tracking_message": result.text, "來源": []}]
    return _original_resolve_people(query)


def apply(module):
    global _original_build_person_menu, _original_person_category_reply, _original_resolve_people
    if getattr(module, "_MR_TRACKING_PATCHED", False):
        return
    _original_build_person_menu = module.build_person_menu
    _original_person_category_reply = module.person_category_reply
    _original_resolve_people = module.resolve_people

    module.build_person_menu = lambda person: build_person_menu(module, person)
    module.person_category_reply = person_category_reply
    module.resolve_people = resolve_people

    original_build = module.build_person_menu
    def patched_build(person):
        if person.get("姓名") == "__TRACKING_RESULT__":
            return TextMessage(text=person.get("_tracking_message") or "已更新。")
        return build_person_menu(module, person)
    module.build_person_menu = patched_build
    module._MR_TRACKING_PATCHED = True
