import csv
import io
import json
import os
from urllib.parse import quote
from urllib.request import Request, urlopen

import requests
from google.auth.transport.requests import Request as GoogleAuthRequest
from google.oauth2 import service_account


SPREADSHEET_ID = "1tsSKZp8dkjz54jMUXuZ4rVvOHLRngQdqjUDqOFi_meU"
SHEET_NAME = "MR品牌開發追蹤"
GOOGLE_SCOPE = "https://www.googleapis.com/auth/spreadsheets"

TRACKING_FIELDS = {
    "開發狀態": "I",
    "第一次聯絡日期": "J",
    "有無回覆": "K",
    "願意了解": "L",
    "目前需求": "M",
    "未成交／停滯原因": "N",
    "下一步": "O",
    "備註": "P",
}

FIELD_OPTIONS = {
    "開發狀態": ["未開發", "已接觸", "已回覆", "願意了解", "洽談中", "已有服務", "暫停", "成交"],
    "有無回覆": ["有", "無"],
    "願意了解": ["有", "無"],
    "下一步": ["優先開發", "次優先", "追蹤進度", "低優先", "既有客戶追蹤", "暫停"],
}

DISPLAY_FIELDS = [
    "開發狀態",
    "第一次聯絡日期",
    "有無回覆",
    "願意了解",
    "目前需求",
    "未成交／停滯原因",
    "下一步",
    "備註",
]


def _fetch_rows():
    url = (
        f"https://docs.google.com/spreadsheets/d/{SPREADSHEET_ID}/gviz/tq"
        f"?tqx=out:csv&sheet={quote(SHEET_NAME)}"
    )
    req = Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urlopen(req, timeout=15) as response:
        text = response.read().decode("utf-8-sig")
    return list(csv.DictReader(io.StringIO(text)))


def get_tracking_record(name):
    name = str(name or "").strip()
    if not name:
        return None
    for row_index, row in enumerate(_fetch_rows(), start=2):
        if str(row.get("姓名") or "").strip() == name:
            result = dict(row)
            result["_row"] = row_index
            return result
    return None


def format_tracking_record(name):
    row = get_tracking_record(name)
    if not row:
        return f"找不到「{name}」的 MR品牌開發追蹤紀錄。"
    company = str(row.get("公司") or "").strip()
    lines = [f"【{name}｜MR品牌開發追蹤】"]
    if company:
        lines.append(company)
    for field in DISPLAY_FIELDS:
        value = str(row.get(field) or "").strip() or "—"
        lines.append(f"{field}：{value}")
    return "\n".join(lines)


def _credentials():
    raw = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON", "").strip()
    if not raw:
        raise RuntimeError("尚未設定 GOOGLE_SERVICE_ACCOUNT_JSON")
    try:
        info = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError("GOOGLE_SERVICE_ACCOUNT_JSON 格式錯誤") from exc
    creds = service_account.Credentials.from_service_account_info(info, scopes=[GOOGLE_SCOPE])
    creds.refresh(GoogleAuthRequest())
    return creds


def update_tracking_field(name, field, value):
    if field not in TRACKING_FIELDS:
        raise ValueError("不支援的追蹤欄位")
    value = str(value or "").strip()
    if not value:
        raise ValueError("內容不可空白")
    options = FIELD_OPTIONS.get(field)
    if options and value not in options:
        raise ValueError(f"{field} 只能填：{'／'.join(options)}")

    row = get_tracking_record(name)
    if not row:
        raise ValueError(f"找不到「{name}」的追蹤列")

    cell = f"'{SHEET_NAME}'!{TRACKING_FIELDS[field]}{row['_row']}"
    creds = _credentials()
    url = (
        f"https://sheets.googleapis.com/v4/spreadsheets/{SPREADSHEET_ID}/values/"
        f"{quote(cell, safe="'!:")}?valueInputOption=USER_ENTERED"
    )
    response = requests.put(
        url,
        headers={"Authorization": f"Bearer {creds.token}", "Content-Type": "application/json"},
        json={"range": cell, "majorDimension": "ROWS", "values": [[value]]},
        timeout=20,
    )
    if response.status_code >= 300:
        raise RuntimeError(f"Google Sheet 更新失敗：{response.status_code} {response.text[:300]}")
    return {"name": name, "field": field, "value": value, "cell": cell}
