"""Private, zero paid-AI-API task assistant for the existing MR LINE bot.

This version parses a limited set of date expressions; it does not claim to
transcribe audio, understand arbitrary conversation, or access TimeTree.
"""
import hashlib
import hmac
import os
import re
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import requests

TZ = ZoneInfo("Asia/Taipei")
CLOSED = {"完成", "取消"}
HELP = (
    "個人待辦｜基本文字版\n\n"
    "直接交代一件事，例如：\n星期五前把資料傳給林威\n"
    "可以用手機鍵盤麥克風轉成文字再傳送。\n\n"
    "• 我的待辦／今天有哪些事／逾期待辦\n"
    "• 完成 12／取消 12／等待 12\n"
    "• 延後 12 到下星期一\n"
    "• 開啟每日提醒／關閉每日提醒\n"
    "• 查客戶 林威：使用原本的人物查詢\n"
    "• 離開助理：回到原本小幫手\n\n"
    "整理結果確認後才會存檔。每日提醒預設關閉，開啟後上午9點彙整，"
    "受現有LINE額度限制。尚不讀取TimeTree、其他聊天室或LINE語音檔。"
)


class StorageError(Exception):
    pass


class InputError(Exception):
    pass


def clock():
    return datetime.now(TZ)


def gateway(action, user_id=None, event_id=None, **values):
    endpoint = os.getenv("LIFEOS_GATEWAY_URL", "")
    secret = os.getenv("LIFEOS_GATEWAY_KEY", "")
    if not endpoint or not secret:
        raise StorageError("not configured")
    payload = {"action": action, **values}
    if user_id:
        payload["user_id"] = user_id
    if event_id:
        payload["event_id"] = event_id
    try:
        response = requests.post(endpoint, json=payload,
            headers={"X-LifeOS-Key": secret}, timeout=12)
        response.raise_for_status()
        result = response.json()
        if result.get("error") == "storage_unavailable":
            raise StorageError("unavailable")
        return result
    except (requests.RequestException, ValueError) as exc:
        raise StorageError("unavailable") from exc


def number(value):
    if value.isdigit():
        return int(value)
    digits = {"零": 0, "一": 1, "二": 2, "兩": 2, "三": 3, "四": 4,
              "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}
    if "十" in value:
        left, right = value.split("十", 1)
        return digits.get(left, 1) * 10 + digits.get(right, 0)
    if value not in digits:
        raise InputError("數字不清楚，請改用阿拉伯數字。")
    return digits[value]


def parse_date(text, now=None):
    """Return a local explicit deadline, or None if no precise date was given."""
    now = now or clock()
    today = now.date()
    day = None
    span = None
    # Explicit year/month/day takes precedence over relative expressions.
    explicit = re.search(r"(?:(20\d{2})[年/\-])?(\d{1,2})[月/\-](\d{1,2})(?:日|號)?", text)
    if explicit:
        year, month, date = explicit.groups()
        try:
            day = today.replace(year=int(year or today.year), month=int(month), day=int(date))
            if not year and day < today:
                day = day.replace(year=today.year + 1)
        except ValueError as exc:
            raise InputError("日期不存在，請重新說明日期。") from exc
        span = explicit.span()
    else:
        relative = re.search(r"今天|今日|明天|後天", text)
        week = re.search(r"(下下|下|本|這)?(?:星期|禮拜|週)([一二三四五六日天])", text)
        offset = re.search(r"(\d+|[一二兩三四五六七八九十]+)天(?:後|內)", text)
        if relative:
            day = today + timedelta(days={"今天": 0, "今日": 0, "明天": 1, "後天": 2}[relative.group()])
            span = relative.span()
        elif week:
            prefix, weekday = week.groups()
            target = "一二三四五六日".index("日" if weekday == "天" else weekday)
            delta = target - today.weekday()
            if prefix in ("下", "下下"):
                delta += 7 if prefix == "下" else 14
            elif prefix not in ("本", "這") and delta < 0:
                delta += 7
            day = today + timedelta(days=delta)
            span = week.span()
        elif offset:
            day = today + timedelta(days=number(offset.group(1)))
            span = offset.span()
    time = re.search(r"(上午|早上|下午|晚上|中午|凌晨)?\s*(\d{1,2}|[零一二兩三四五六七八九十]+)(?:點|時|:|：)(半|\d{1,2}|[一二三四五六七八九十]+)?(?:分)?", text)
    if day is None:
        if time:
            raise InputError("有時間但沒有日期，請補上哪一天。")
        return None, []
    hour, minute = 23, 59
    spans = [span]
    if time:
        period, h, m = time.groups()
        hour = number(h)
        minute = 30 if m == "半" else number(m) if m else 0
        if period in ("下午", "晚上") and 1 <= hour < 12:
            hour += 12
        elif period in ("上午", "早上", "凌晨") and hour == 12:
            hour = 0
        elif period == "中午" and hour < 11:
            hour += 12
        if not 0 <= hour <= 23 or not 0 <= minute <= 59:
            raise InputError("時間不正確，請使用例如「下午2點」或「14:30」。")
        if period is None and 1 <= hour <= 11:
            raise InputError("請補上上午／下午，或使用24小時時間。")
        spans.append(time.span())
    return datetime.combine(day, datetime.min.time(), TZ).replace(hour=hour, minute=minute), spans


def parse_tasks(text, now=None):
    now = now or clock()
    text = text.strip()
    if not text or len(text) > 1500:
        raise InputError("請傳送1500字以內的待辦內容。")
    if re.search(r"每(?:天|日|週|星期|月|年)|每個月", text):
        raise InputError("這版尚未支援自動重複任務。請先指定這一期的日期，例如「10月15日繳電話費」。")
    if re.search(r"(?:前|提早)(?:一|兩|二|\d+)天|提前|之前提醒|那天|到時候|下週末|下星期末|月底|下個月|下月", text):
        raise InputError("這個日期或相對提醒還不夠明確。請直接說準備事項的日期；目前讀不到TimeTree預約。")
    parts = [p.strip(" ，。") for p in re.split(r"[；;\n]+|[，,。]\s*(?:另外|還有|再來)", text) if p.strip(" ，。")]
    if len(parts) > 10:
        raise InputError("一次最多整理10件事，請分段傳送。")
    tasks = []
    for part in parts:
        due, spans = parse_date(part, now)
        title = part
        for start, end in sorted(spans, reverse=True):
            title = title[:start] + title[end:]
        title = re.sub(r"^(?:幫我|請|記得|我要|我想|待辦[：:]?|新增待辦[：:]?)\s*", "", title)
        title = re.sub(r"^[\s，,：:]*(?:之前|以前|前|到|要|提醒我|記得|幫我)\s*", "", title)
        title = title.strip(" ，,。:：")
        if not title or len(title) > 500:
            raise InputError("請補上要做的事情，例如「星期五前傳資料給林威」。")
        category = "生活"
        if re.search(r"繳|付款|帳單|匯款", part):
            category = "付款"
        elif re.search(r"買|補貨|耗材|庫存", part):
            category = "補貨"
        elif re.search(r"資料|客戶|客人|報價|會議|交付|提案", part):
            category = "工作"
        tasks.append({"title":title,"due_at":due.isoformat() if due else None,
            "remind_at":None,"category":category,"priority":"重要" if re.search(r"重要|緊急",part) else "一般",
            "original_text":part})
    return tasks


def deadline(task):
    value = task.get("due_at")
    if not value:
        return "待安排"
    d = datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(TZ)
    return d.strftime("%m/%d") + (" 當日截止" if (d.hour,d.minute)==(23,59) else d.strftime(" %H:%M"))


def task_line(task):
    tag = f"#{task['id']} " if "id" in task else ""
    return f"{tag}{task['title']}\n  {deadline(task)}｜{task.get('status','未開始')}"


class Digest(str):
    def __new__(cls,body,tasks,now,mode):
        value=super().__new__(cls,body)
        value.tasks=tasks;value.now=now;value.mode=mode
        return value


def summary(tasks, now=None, mode="today", user_id=None):
    now = now or clock()
    active = [t for t in tasks if t.get("status") not in CLOSED]
    buckets = {"已逾期":[],"今天到期":[],"近期三天":[],"等待對方":[],"待安排":[]}
    for task in active:
        due = datetime.fromisoformat(task["due_at"].replace("Z","+00:00")).astimezone(TZ) if task.get("due_at") else None
        if task.get("status") == "等待對方":
            buckets["等待對方"].append(task)
        if due and due < now:
            buckets["已逾期"].append(task)
        elif due and due.date() == now.date():
            buckets["今天到期"].append(task)
        elif due and due.date() <= now.date()+timedelta(days=3):
            buckets["近期三天"].append(task)
        elif due is None and task.get("status") != "等待對方":
            buckets["待安排"].append(task)
    if mode == "all":
        body = "我的未完成待辦\n\n" + ("\n\n".join(task_line(t) for t in active) or "目前沒有未完成待辦。")
    else:
        headings = ["已逾期"] if mode == "overdue" else list(buckets)
        sections = [h+"\n"+"\n".join(task_line(t) for t in buckets[h]) for h in headings if buckets[h]]
        body = now.strftime("%m/%d 待辦摘要\n\n") + ("\n\n".join(sections) or "目前沒有需要列入這份摘要的待辦。")
    body += "\n\n完成請回覆「完成 編號」。TimeTree與其他LINE聊天尚未納入。"
    # LINE limit is 5000 characters; a truthful truncation notice is required.
    if len(body) > 4500:
        body = body[:4350] + "\n\n內容較多，這份摘要未列完。請先完成部分事項後再查詢。"
    digest=Digest(body,active,now,mode)
    digest.user_id=user_id
    return digest


def choose_task(target, tasks):
    target = target.strip().lstrip("#").strip()
    matches = [t for t in tasks if str(t["id"]) == target] if target.isdigit() else [t for t in tasks if target and target in t["title"]]
    if len(matches) != 1:
        raise InputError("找不到唯一對應的待辦。請先傳「我的待辦」，再用編號，例如「完成 12」。")
    return matches[0]


def handle_text(user_id, text, event_id=None, source_type="user"):
    """Return text for private commands; None leaves the original MR routing intact."""
    if os.getenv("LIFEOS_ENABLED") != "1":
        return None
    text = text.strip()
    explicit = text.startswith(("啟用助理","待辦按鈕 ","待辦操作 ")) or text in ("個人助理","我的待辦","今天有哪些事","今天有什麼事","逾期待辦","新增待辦","提醒設定","測試提醒","更多功能","生活助理","其他天的事","今天有哪些是")
    if source_type != "user":
        return "私人待辦僅能在與MR小幫手的一對一聊天室使用。" if explicit else None
    try:
        if text.startswith("啟用助理"):
            code = text.removeprefix("啟用助理").strip()
            result = gateway("enroll",user_id,event_id,code_hash=hashlib.sha256(code.encode()).hexdigest())
            if result.get("error"):
                return "啟用碼無效、已使用或已到期。請向建置者確認，不需要提供LINE密碼。"
            return "你的私人待辦已啟用。每日主動提醒尚未開啟。\n\n" + HELP
        result = gateway("get_user",user_id)
        user = result.get("user")
        if not user:
            return "個人助理尚未綁定。請使用建置者提供的一次性啟用碼。" if explicit else None
        if text in ("生活助理","更多功能"):
            return "生活助理\n今天的事：今日待辦與行程\n其他天的事：未來待辦\n其他天的行程：未來七天日曆\n逾期追蹤：之前尚未完成的事\n新增事項：交代要做的事情\n提醒設定：設定與測試通知"
        if text in ("個人助理","助理說明"):
            gateway("mode",user_id,event_id,enabled=True)
            return HELP
        if text in ("離開助理","回到小幫手"):
            gateway("mode",user_id,event_id,enabled=False)
            return "已回到MR小幫手。私人待辦仍保留，傳「個人助理」即可繼續。"
        if text.startswith("查客戶 ") or text in ("電子名片","展示","最近查看的名片") or text.startswith(("人物資料|","人物完整|","人物選單|","追蹤更新|")):
            return None
        commands = ("完成","取消","等待","開始","延後","開啟每日提醒","關閉每日提醒")
        if not user.get("assistant_mode") and not explicit and not text.startswith(commands):
            return None
        if text == "新增待辦":
            gateway("mode",user_id,event_id,enabled=True)
            return "請說明要做的事情與日期，例如「明天買耗材」。\n可按手機鍵盤的麥克風轉成文字，傳送後按「確認存檔」。"
        if text == "提醒設定":
            return "每日提醒目前" + ("開啟" if user.get("notifications") else "關閉") + "。\n開啟後上午9點發送未完成待辦摘要，受現有LINE額度限制。請點下方按鈕設定。"
        if text == "測試提醒":
            result=gateway("test_schedule",user_id,event_id)
            if result.get("error"): raise StorageError("test schedule failed")
            if result.get("already_scheduled"):
                return "今天已安排過測試提醒。\n" + ("測試訊息已送出，請查看聊天室。" if result.get("state")=="sent" else "尚未確認送出；若超過3分鐘未收到，請告訴建置者檢查。每天最多測試一次，避免耗用額度。")
            return "測試提醒已安排\n約1～2分鐘後，小幫手會主動傳送測試卡片。你可以先離開聊天室，不需要再傳訊息。\n使用現有LINE推播額度；額度不足時不發送。這次測試不會開啟每日提醒。"
        page = re.fullmatch(r"待辦按鈕 (\d+)",text)
        operation = re.fullmatch(r"待辦操作 (\d+)",text)
        if page:
            tasks=gateway("list",user_id)["tasks"]
            index=max(1,int(page.group(1)))
            if not tasks:
                return "目前沒有未完成待辦。請點「新增待辦」。"
            index=min(index,(len(tasks)+7)//8)
            selected=tasks[(index-1)*8:index*8]
            return f"選擇要操作的待辦｜第{index}頁\n\n" + "\n\n".join(task_line(t) for t in selected) + (f"\n下一頁：{index+1}" if index*8<len(tasks) else "")
        if operation:
            task=choose_task(operation.group(1),gateway("list",user_id)["tasks"])
            return "待辦操作\n" + task_line(task) + "\n\n請點下方按鈕完成、等待對方或延後。"
        if text in ("開啟每日提醒","關閉每日提醒"):
            enabled = text.startswith("開啟")
            gateway("notifications",user_id,event_id,enabled=enabled)
            return ("已開啟每日上午9點待辦摘要。僅有未完成事項時發送，每月最多60次，"
                "並受MR現有LINE額度限制；額度不足時停止推播，不會升級方案。") if enabled else "已關閉主動提醒。待辦保留，可隨時傳「今天有哪些事」查詢。"
        if text in ("確認","確認存檔","存檔"):
            result = gateway("confirm",user_id,event_id)
            if result.get("error") in ("no_draft","expired_draft"):
                return "目前沒有可確認的草稿，或草稿已超過一天。請重新交代內容。"
            if result.get("error"):
                raise StorageError("confirmation failed")
            return "已存檔（相同未完成事項會合併）\n\n" + "\n\n".join(task_line(t) for t in result["tasks"])
        if text in ("放棄草稿","取消草稿"):
            gateway("discard",user_id,event_id)
            return "已放棄草稿，沒有新增待辦。"
        if text in ("我的待辦","全部待辦","今天有哪些事","今天有什麼事","今天有哪些是","其他天的事","逾期待辦"):
            result = gateway("list",user_id)
            body = summary(result["tasks"],user_id=user_id,mode="all" if text in ("我的待辦","全部待辦") else "overdue" if text=="逾期待辦" else "future" if text=="其他天的事" else "today")
            if result.get("truncated"):
                body=Digest(str(body)+"\n待辦超過200件，這次僅列前200件。",body.tasks,body.now,body.mode)
                body.truncated=True
                body.user_id=user_id
            return body
        change = re.fullmatch(r"(完成|取消|等待|開始)\s*(.+)",text)
        postpone = re.fullmatch(r"延後\s*(.+?)\s*(?:到|至)\s*(.+)",text)
        if change or postpone:
            tasks = gateway("list",user_id)["tasks"]
            target = change.group(2) if change else postpone.group(1)
            task = choose_task(target,tasks)
            if change:
                state = {"完成":"完成","取消":"取消","等待":"等待對方","開始":"進行中"}[change.group(1)]
                result = gateway("update",user_id,event_id,task_id=task["id"],status=state)
            else:
                date, _ = parse_date(postpone.group(2))
                if date is None:
                    raise InputError("延後日期需明確到哪一天，例如「延後 12 到下星期一」。")
                result = gateway("update",user_id,event_id,task_id=task["id"],due_at=date.isoformat())
            if result.get("error"):
                raise StorageError("update failed")
            return "已更新\n" + task_line(result["task"])
        # Date parsing is intentionally bounded and always reviewed before storage.
        tasks = parse_tasks(text)
        result = gateway("draft",user_id,event_id,tasks=tasks)
        if result.get("error"):
            raise StorageError("draft failed")
        return ("請確認內容（尚未存成正式待辦）\n\n" + "\n\n".join(task_line(t) for t in tasks)
            + "\n\n回覆「確認存檔」即可記錄；不正確請重新傳完整內容，或回覆「放棄草稿」。")
    except InputError as exc:
        return str(exc)
    except StorageError:
        return "私人待辦目前無法讀寫，這次未確認成功。請稍後重試；不會只用口頭承諾代替存檔。" if explicit or text.startswith(commands if 'commands' in locals() else ()) or 'user' in locals() and user else None


def handle_audio(user_id, source_type="user"):
    if os.getenv("LIFEOS_ENABLED") != "1" or source_type != "user":
        return None
    try:
        if not gateway("get_user",user_id).get("user"):
            return None
    except StorageError:
        return "私人待辦目前無法讀取，請稍後重試。"
    return "這個零新增費用版本尚未辨識LINE語音檔。請按手機鍵盤的麥克風，把語音轉成文字後傳送；收到後會整理待辦供你確認。"


def reminder_run(now=None):
    """Daily summaries only; never add LINE paid quota or start a paid AI API."""
    now = now or clock()
    if os.getenv("LIFEOS_ENABLED") != "1":
        return {"sent":0,"skipped":"disabled"}
    if now.hour != 9:
        return {"sent":0,"skipped":"outside_daily_window"}
    token = os.getenv("LINE_CHANNEL_ACCESS_TOKEN", "")
    headers = {"Authorization":f"Bearer {token}"}
    quota = requests.get("https://api.line.me/v2/bot/message/quota",headers=headers,timeout=10)
    quota.raise_for_status()
    usage = requests.get("https://api.line.me/v2/bot/message/quota/consumption",headers=headers,timeout=10)
    usage.raise_for_status()
    q, used = quota.json(), usage.json().get("totalUsage",0)
    # Reserve at least 20 messages for existing MR functions. Unlimited/unknown
    # plans do not establish a free allowance and must not enable pushes here.
    if q.get("type") != "limited" or q.get("value",0) <= 20:
        return {"sent":0,"skipped":"quota_not_verified"}
    cap = min(180,q["value"]-20)
    if used >= cap:
        return {"sent":0,"skipped":"quota_reserved"}
    sent = 0
    for user in gateway("notification_users")["users"]:
        if used+sent >= cap:
            break
        tasks = gateway("list",user["user_id"])["tasks"]
        if not tasks:
            continue
        claimed = gateway("notification_claim",user["user_id"],key="daily:"+now.date().isoformat())
        if "notification" not in claimed:
            continue
        n = claimed["notification"]
        response = requests.post("https://api.line.me/v2/bot/message/push",
            headers={**headers,"X-Line-Retry-Key":n["retry_key"]},
            json={"to":user["user_id"],"messages":[button_message(summary(tasks,now,user_id=user["user_id"])).to_dict()]},timeout=15)
        ok = response.status_code in (200,409)
        gateway("notification_finish",user["user_id"],notification_id=n["id"],sent=ok)
        if ok:
            sent += 1
    return {"sent":sent}


def install_routes(app):
    @app.post("/lifeos/test-reminders")
    def run_test_reminders():
        from flask import request
        secret=os.getenv("LIFEOS_CRON_KEY","")
        if not secret or not hmac.compare_digest(request.headers.get("Authorization",""),"Bearer "+secret):
            return {"error":"unauthorized"},401
        try: return test_reminder_run()
        except Exception:
            app.logger.error("Life OS test reminder execution failed")
            return {"error":"test_reminder_failed"},503

    @app.post("/lifeos/reminders")
    def run_reminders():
        from flask import request
        secret = os.getenv("LIFEOS_CRON_KEY", "")
        supplied = request.headers.get("Authorization", "")
        if not secret or not hmac.compare_digest(supplied,"Bearer "+secret):
            return {"error":"unauthorized"},401
        try:
            return reminder_run()
        except Exception:
            app.logger.error("Life OS reminder execution failed")
            return {"error":"reminder_failed"},503

    @app.get("/lifeos/health")
    def lifeos_health():
        return {"enabled":os.getenv("LIFEOS_ENABLED")=="1",
            "storage_configured":bool(os.getenv("LIFEOS_GATEWAY_KEY") and os.getenv("LIFEOS_GATEWAY_URL")),
            "audio_transcription":False,"paid_ai_api":False,"calendar_sync":False,
            "version":"2026-10-08-calendar-pilot"}


def test_reminder_run():
    if os.getenv("LIFEOS_ENABLED")!="1": return {"sent":0,"skipped":"disabled"}
    users=gateway("test_users")["users"]
    if not users: return {"sent":0,"skipped":"no_test_scheduled"}
    headers={"Authorization":"Bearer "+os.getenv("LINE_CHANNEL_ACCESS_TOKEN","")}
    quota=requests.get("https://api.line.me/v2/bot/message/quota",headers=headers,timeout=10)
    quota.raise_for_status()
    usage=requests.get("https://api.line.me/v2/bot/message/quota/consumption",headers=headers,timeout=10)
    usage.raise_for_status()
    q=quota.json();used=usage.json().get("totalUsage",0)
    if q.get("type")!="limited" or q.get("value",0)<=20:
        return {"sent":0,"skipped":"quota_not_verified"}
    cap=min(180,q['value']-20);sent=0
    for user in users:
        if used+sent>=cap: break
        uid=user['user_id'];result=gateway('test_claim',uid)
        if 'notification' not in result: continue
        n=result['notification']
        response=requests.post("https://api.line.me/v2/bot/message/push",headers={**headers,"X-Line-Retry-Key":n['retry_key']},
            json={'to':uid,'messages':[button_message('測試提醒送達\n這是你剛才按下「測試提醒」後，小幫手主動傳送的卡片。\n你已確認這個帳號可以收到主動訊息。每日提醒仍依你的設定開啟或關閉。').to_dict()]},timeout=15)
        ok=response.status_code in (200,409)
        gateway('test_finish',uid,retry_key=n['retry_key'],sent=ok)
        if ok: sent+=1
    return {'sent':sent}


def button_message(body):
    """LINE quick replies use existing commands, preserving owner checks."""
    if isinstance(body,Digest): return digest_message(body)
    from linebot.v3.messaging import FlexMessage, FlexContainer, QuickReply, QuickReplyItem, MessageAction
    choices=[]
    if body.startswith("待辦操作\n"):
        match=re.search(r"#(\d+)",body)
        if match:
            tid=match.group(1)
            choices=[("完成這件事",f"完成 {tid}"),("等待對方",f"等待 {tid}"),
                ("開始處理",f"開始 {tid}"),("延到明天",f"延後 {tid} 到明天"),
                ("延到下週一",f"延後 {tid} 到下星期一"),("取消這件事",f"取消 {tid}")]
    elif body.startswith("選擇要操作的待辦"):
        choices=[(f"{tid} {title}"[:20],f"待辦操作 {tid}") for tid,title in re.findall(r"#(\d+) ([^\n]+)",body)]
        next_page=re.search(r"下一頁：(\d+)",body)
        if next_page: choices.append(("下一頁",f"待辦按鈕 {next_page.group(1)}"))
    elif body.startswith("請確認內容"):
        choices=[("確認存檔","確認存檔"),("放棄草稿","放棄草稿")]
    elif body.startswith("每日提醒目前"):
        choices=[("測試提醒","測試提醒"),("開啟每日提醒","開啟每日提醒"),("關閉每日提醒","關閉每日提醒")]
    if body.startswith("生活助理"):
        choices=[("今天的事","今天有哪些事"),("其他天的事","其他天的事"),("其他天的行程","其他天的行程"),("逾期追蹤","逾期待辦"),("新增事項","新增待辦"),("提醒設定","提醒設定")]
    elif not choices:
        choices=[("今日總覽","今天有哪些事"),("更多功能","更多功能")]
    quick=QuickReply(items=[QuickReplyItem(action=MessageAction(label=label,text=command)) for label,command in choices[:13]])
    def text(value,size="sm",color="#475569",weight="regular"):
        return {"type":"text","text":value or " ","size":size,"color":color,"weight":weight,"wrap":True}
    def button(label,command,primary=False):
        result={"type":"button","height":"sm","style":"primary" if primary else "secondary",
            "action":{"type":"message","label":label,"text":command}}
        if primary: result["color"]="#345C58"
        return result
    first=body.split("\n",1)[0]
    heading=("確認待辦" if body.startswith("請確認內容") else
        "個人助理" if "你的私人待辦已啟用" in first else
        "待辦清單" if first.startswith("選擇要操作") else first[:40])
    draft=body.startswith("請確認內容")
    content=[]
    lines=body.splitlines()[1:]
    i=0; rendered=0; omitted=0
    while i<len(lines):
        line=lines[i].strip()
        if not line: i+=1;continue
        # Existing task output is always a title followed by deadline/status.
        is_task=i+1<len(lines) and lines[i+1].startswith("  ") and "｜" in lines[i+1]
        if is_task:
            meta=lines[i+1].strip();i+=2
            if rendered >= (10 if draft else 8): omitted+=1;continue
            rendered+=1
            match=re.match(r"#(\d+) (.*)",line)
            title=match.group(2) if match else line
            date,state=meta.rsplit("｜",1)
            badge_color="#345C58"
            row=[text(title,"md","#172B2A","bold"),
                {"type":"box","layout":"horizontal","margin":"md","contents":[
                  {**text(date,"sm"),"flex":3}, {**text(state,"xs",badge_color,"bold"),"flex":2,"align":"end"}]}]
            if match and state not in CLOSED and not body.startswith("待辦操作\n"):
                tid=match.group(1)
                row.append({"type":"box","layout":"horizontal","spacing":"sm","margin":"md","contents":[
                    button("完成",f"完成 {tid}",True),button("更多操作",f"待辦操作 {tid}")]})
            content.append({"type":"box","layout":"vertical","paddingAll":"16px","cornerRadius":"12px",
                "backgroundColor":"#F4F7F6","contents":row,"margin":"md"})
        else:
            if line.startswith("下一頁："):
                content.append(button("下一頁","待辦按鈕 "+line.split("：",1)[1]))
            else:
                section=line in ("已逾期","今天到期","近期三天","等待對方","待安排")
                content.append({**text(line,"sm","#345C58" if section else "#64748B","bold" if section else "regular"),"margin":"md"})
            i+=1
    if omitted: content.append(text(f"這張卡片另有{omitted}項未展開，請點「操作待辦」逐頁查看。","xs"))
    if not content: content=[text(first)]
    if draft: footer=[button("確認存檔","確認存檔",True),button("放棄草稿","放棄草稿")]
    elif body.startswith("待辦操作\n"): footer=[button(label,command,index==0) for index,(label,command) in enumerate(choices[:6])]
    elif body.startswith("每日提醒目前"): footer=[button("測試提醒（1～2分鐘）","測試提醒",True),button("開啟每日提醒","開啟每日提醒"),button("關閉每日提醒","關閉每日提醒")]
    elif body.startswith("生活助理"): footer=[button(a,b) for a,b in choices]+[button("今日總覽","今天有哪些事",True)]
    else: footer=[button("今日總覽","今天有哪些事",True),button("生活助理","生活助理")]
    bubble={"type":"bubble","size":"mega","header":{"type":"box","layout":"vertical","paddingAll":"20px","backgroundColor":"#FFFFFF",
        "contents":[text("MR 個人助理","xs","#345C58"),text(heading,"xl","#172B2A","bold")]},
        "body":{"type":"box","layout":"vertical","paddingAll":"16px","contents":content},
        "footer":{"type":"box","layout":"vertical","spacing":"sm","paddingAll":"16px","contents":footer}}
    return FlexMessage(alt_text=first[:400],contents=FlexContainer.from_dict(bubble),quick_reply=quick)


def digest_message(digest):
    """Today's deadlines use a board; other dates form a chronological timeline."""
    from linebot.v3.messaging import FlexMessage,FlexContainer,QuickReply,QuickReplyItem,MessageAction
    now=digest.now
    def date(task):
        return datetime.fromisoformat(task['due_at'].replace('Z','+00:00')).astimezone(TZ) if task.get('due_at') else None
    def label(d): return d.strftime('%Y/%m/%d')+'（'+'一二三四五六日'[d.weekday()]+'）'
    def tx(value,size='sm',color='#475569',bold=False):
        return {'type':'text','text':value,'size':size,'color':color,'weight':'bold' if bold else 'regular','wrap':True}
    def btn(title,command,primary=False):
        b={'type':'button','height':'sm','style':'primary' if primary else 'secondary','action':{'type':'message','label':title,'text':command}}
        if primary: b['color']='#345C58'
        return b
    def row(task):
        d=date(task);state=task.get('status','未開始')
        detail='到期日：'+label(d) if d else '到期日：待安排'
        if d and (d.hour,d.minute)!=(23,59): detail+=' '+d.strftime('%H:%M')
        elements=[tx(task['title'],'md','#172B2A',True),tx(detail,'sm','#475569',True),
            tx('狀態：'+state,'sm','#345C58')]
        if 'id' in task:
            tid=str(task['id'])
            elements.append({'type':'box','layout':'horizontal','spacing':'sm','margin':'md','contents':[btn('完成','完成 '+tid,True),btn('更多操作','待辦操作 '+tid)]})
        return {'type':'box','layout':'vertical','spacing':'sm','paddingAll':'14px','backgroundColor':'#FFFFFF','cornerRadius':'10px','contents':elements}
    tasks=sorted(digest.tasks,key=lambda t:(date(t) or datetime.max.replace(tzinfo=TZ),t.get('id',0)))
    overdue=[t for t in tasks if date(t) and date(t)<now]
    today=[t for t in tasks if date(t) and date(t)>=now and date(t).date()==now.date()]
    future=[t for t in tasks if date(t) and date(t).date()>now.date()]
    unscheduled=[t for t in tasks if not date(t)]
    if digest.mode=='overdue': today=[];future=[];unscheduled=[]
    elif digest.mode=='today':
        today=[t for t in tasks if date(t) and date(t).date()==now.date()]
        overdue=[];future=[];unscheduled=[]
    elif digest.mode=='future': today=[];overdue=[];unscheduled=[]
    content=[];shown=0;total=len(overdue)+len(today)+len(future)+len(unscheduled)
    def board(title,items,bg,ink):
        nonlocal shown
        if not items: return
        remaining=max(0,8-shown);visible=items[:remaining];shown+=len(visible)
        if not visible: return
        heading={'type':'box','layout':'horizontal','contents':[{**tx(title,'md',ink,True),'flex':2},{**tx(str(len(items))+'件','sm',ink,True),'align':'end','flex':1}]}
        content.append({'type':'box','layout':'vertical','spacing':'md','paddingAll':'12px','backgroundColor':bg,'cornerRadius':'12px','margin':'md',
            'contents':[heading]+[row(t) for t in visible]})
    board('今日待辦',today,'#F4F7F6','#345C58')
    board('已逾期',overdue,'#F4F7F6','#345C58')
    if not today and digest.mode not in ('overdue','future'): content.append({**tx('今天沒有到期事項','sm','#345C58',True),'margin':'md'})
    if future:
        content.append({**tx('接下來的到期時間軸','md','#345C58',True),'margin':'xl'})
        grouped={}
        for task in future: grouped.setdefault(date(task).date(),[]).append(task)
        for day,items in grouped.items():
            visible=items[:max(0,8-shown)]
            if not visible: break
            shown+=len(visible)
            d=date(visible[0]);relative='明天' if day==now.date()+timedelta(days=1) else '後天' if day==now.date()+timedelta(days=2) else '到期日'
            node={'type':'box','layout':'vertical','spacing':'sm','contents':[tx(relative+'｜'+label(d),'sm','#345C58',True)]+[row(t) for t in visible]}
            content.append({'type':'box','layout':'horizontal','spacing':'md','margin':'md','contents':[
                {'type':'box','layout':'vertical','width':'14px','alignItems':'center','contents':[tx('●','sm','#345C58'),
                    {'type':'box','layout':'vertical','width':'2px','height':'120px','backgroundColor':'#C9DDD7','contents':[tx(' ','xxs')]}]},
                {**node,'flex':1}]})
    board('待安排日期',unscheduled,'#F4F7F6','#345C58')
    if not tasks or (digest.mode=='overdue' and not overdue): content.append(tx('目前沒有未完成的逾期事項。' if digest.mode=='overdue' else '目前沒有未完成待辦。'))
    if total>shown: content.append({**tx(f'卡片尚有{total-shown}件未展開，請點「操作待辦」逐頁查看。','xs'),'margin':'md'})
    if getattr(digest,'truncated',False): content.append(tx('待辦超過200件，這份卡片僅整理前200件。','xs'))
    if digest.mode=='today':
        import lifeos_calendar as calendar
        events,note=calendar.today_events(getattr(digest,'user_id',None),now)
        if events is not None:
            content.append({'type':'separator','margin':'xl'})
            content.append({**tx('今日預計行程','lg','#345C58',True),'margin':'lg'})
            for event in events:
                content.append({'type':'box','layout':'vertical','spacing':'sm','paddingAll':'12px','backgroundColor':'#F4F7F6','cornerRadius':'10px','margin':'md','contents':[
                    tx(event.get('summary','未命名行程'),'md','#172B2A',True),tx(calendar.event_time(event),'sm','#345C58',True)]})
            if not events and not note: content.append({**tx('今天沒有安排Google行程。'),'margin':'md'})
            if note: content.append({**tx(note,'xs'),'margin':'md'})
    content.append({**tx('行程來源：Life OS 測試；尚未包含TimeTree及其他LINE聊天室。','xs','#64748B'),'margin':'lg'})
    title='逾期追蹤' if digest.mode=='overdue' else '其他天的事' if digest.mode=='future' else '我的待辦' if digest.mode=='all' else '今日摘要'
    bubble={'type':'bubble','size':'mega','header':{'type':'box','layout':'vertical','paddingAll':'20px','spacing':'sm','contents':[
        tx('MR 個人助理','xs','#345C58',True),tx(title,'lg','#172B2A',True),tx(label(now),'xl','#172B2A',True),tx('摘要日期','xs','#64748B')]},
        'body':{'type':'box','layout':'vertical','paddingAll':'14px','contents':content},
        'footer':{'type':'box','layout':'vertical','paddingAll':'14px','spacing':'sm','contents':[btn('新增事項','新增待辦',True),btn('生活助理','生活助理')]}}
    choices=[('新增事項','新增待辦'),('生活助理','生活助理')]
    return FlexMessage(alt_text=title+'｜'+label(now),contents=FlexContainer.from_dict(bubble),
        quick_reply=QuickReply(items=[QuickReplyItem(action=MessageAction(label=a,text=b)) for a,b in choices]))
