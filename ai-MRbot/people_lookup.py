import json
import os
import re
import time

import gspread
from google.oauth2.service_account import Credentials


SHEET_CONFIG = [
    {
        "key": "1WIIhNOsLcJhq0wjwrGSmpaVPGOe3NBlHszcfNQOalLc",
        "label": "BNI 磐石",
    },
    {
        "key": "1tsSKZp8dkjz54jMUXuZ4rVvOHLRngQdqjUDqOFi_meU",
        "label": "BNI 建築組",
    },
]

CACHE_SECONDS = 60
_cache = {"loaded_at": 0, "people": {}}


def _clean(value):
    if value is None:
        return ""
    return str(value).strip()


def _service_account_info():
    raw = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON", "").strip()
    if not raw:
        raise RuntimeError("缺少 GOOGLE_SERVICE_ACCOUNT_JSON 環境變數")
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError("GOOGLE_SERVICE_ACCOUNT_JSON 不是有效 JSON") from exc


def _client():
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets.readonly",
        "https://www.googleapis.com/auth/drive.readonly",
    ]
    creds = Credentials.from_service_account_info(_service_account_info(), scopes=scopes)
    return gspread.authorize(creds)


def _merge_nonempty(target, source):
    for key, value in source.items():
        value = _clean(value)
        if value and not _clean(target.get(key)):
            target[key] = value


def _load_people():
    gc = _client()
    people = {}

    for cfg in SHEET_CONFIG:
        spreadsheet = gc.open_by_key(cfg["key"])
        for sheet_name in ("資料蒐集", "顧問快診", "盲蒐"):
            try:
                ws = spreadsheet.worksheet(sheet_name)
            except gspread.WorksheetNotFound:
                continue

            rows = ws.get_all_records(default_blank="")
            for row in rows:
                name = _clean(row.get("姓名"))
                if not name:
                    continue

                person = people.setdefault(name, {
                    "姓名": name,
                    "來源": [],
                    "資料蒐集": {},
                    "顧問快診": {},
                    "盲蒐": {},
                })

                source_label = f"{cfg['label']}／{sheet_name}"
                if source_label not in person["來源"]:
                    person["來源"].append(source_label)

                _merge_nonempty(person[sheet_name], row)

    return people


def get_people(force=False):
    now = time.time()
    if not force and _cache["people"] and now - _cache["loaded_at"] < CACHE_SECONDS:
        return _cache["people"]

    people = _load_people()
    _cache["loaded_at"] = now
    _cache["people"] = people
    return people


def find_people(query, limit=5):
    query = _clean(query).replace(" ", "")
    if not query:
        return []

    people = get_people()
    exact = []
    partial = []

    for name, person in people.items():
        normalized = name.replace(" ", "")
        if query == normalized:
            exact.append(person)
        elif query in normalized or normalized in query:
            partial.append(person)

    return (exact + partial)[:limit]


def get_person(name):
    return get_people().get(name)


def has_value(person, section, keys):
    data = person.get(section, {})
    return any(_clean(data.get(k)) for k in keys)


def available_categories(person, has_card=False):
    categories = []

    if has_value(person, "資料蒐集", ["公司", "品牌", "基本資料"]):
        categories.append(("basic", "基本資料"))

    if has_value(person, "資料蒐集", ["主要服務", "主要客群"]):
        categories.append(("service", "主要服務"))

    if has_value(person, "資料蒐集", ["品牌對外資訊", "線上平台／社群媒體", "公開案例／口碑"]):
        categories.append(("links", "社群／公開連結"))

    if has_value(person, "資料蒐集", ["聯絡資訊"]):
        categories.append(("contact", "聯絡方式"))

    if has_value(person, "顧問快診", [
        "網路看到的你 vs 實際的你", "第一眼印象", "別人會怎麼認識你", "搜尋現況",
        "目前優勢", "外界可能看不懂的地方", "缺少的關鍵資產", "對生意可能造成的影響",
        "顧問現場一句話", "建議下一步"
    ]):
        categories.append(("diagnosis", "顧問快診"))

    if has_value(person, "盲蒐", [
        "姓名搜尋結果", "公司搜尋結果", "自然出現的品牌／名稱", "搜尋到的平台／資產",
        "外界第一眼會怎麼理解", "本人與公司／品牌關聯是否看得懂", "搜尋干擾／同名問題",
        "盲搜時沒有自然出現的資訊", "盲搜結論", "品牌落差"
    ]):
        categories.append(("blind", "盲搜／品牌落差"))

    if has_card:
        categories.append(("card", "電子名片"))

    return categories


def category_text(person, category):
    collected = person.get("資料蒐集", {})
    diagnosis = person.get("顧問快診", {})
    blind = person.get("盲蒐", {})

    sections = {
        "basic": ("基本資料", collected, ["公司", "品牌", "基本資料"]),
        "service": ("主要服務", collected, ["主要服務", "主要客群"]),
        "links": ("社群／公開連結", collected, ["品牌對外資訊", "線上平台／社群媒體", "公開案例／口碑"]),
        "contact": ("聯絡方式", collected, ["聯絡資訊"]),
        "diagnosis": ("顧問快診", diagnosis, [
            "網路看到的你 vs 實際的你", "第一眼印象", "別人會怎麼認識你", "搜尋現況",
            "目前優勢", "外界可能看不懂的地方", "缺少的關鍵資產", "對生意可能造成的影響",
            "顧問現場一句話", "建議下一步"
        ]),
        "blind": ("盲搜／品牌落差", blind, [
            "姓名搜尋結果", "公司搜尋結果", "自然出現的品牌／名稱", "搜尋到的平台／資產",
            "外界第一眼會怎麼理解", "本人與公司／品牌關聯是否看得懂", "搜尋干擾／同名問題",
            "盲搜時沒有自然出現的資訊", "盲搜結論", "後續真實資料比對", "品牌落差", "查核日期", "備註"
        ]),
    }

    if category not in sections:
        return ""

    title, data, keys = sections[category]
    lines = [f"【{person['姓名']}｜{title}】"]
    for key in keys:
        value = _clean(data.get(key))
        if value:
            lines.append(f"\n{key}\n{value}")

    text = "\n".join(lines)
    return text[:4900]


def extract_urls(text):
    if not text:
        return []
    urls = re.findall(r"https?://[^\s，、；;）)]+", text)
    unique = []
    for url in urls:
        if url not in unique:
            unique.append(url)
    return unique[:5]
