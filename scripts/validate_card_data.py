#!/usr/bin/env python3
"""Validate MR card metadata, JSON, images, LIFF launchers, and CASE_LIST."""

from __future__ import annotations

import ast
import hashlib
import json
import re
import subprocess
import sys
from collections import Counter
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse


ROOT = Path(__file__).resolve().parents[1]
TEMPLATES = ROOT / "ai-MRbot" / "templates"
LEGACY_APP = ROOT / "ai-MRbot" / "legacy_app.py"
MEMBER_DATA = ROOT / "ai-MRbot" / "data" / "chapter_members.json"
PAGES_HOST = "mrbusinesslab.github.io"
PAGES_PREFIX = "/MR_card/"
LIFF_RE = re.compile(r"^https://liff\.line\.me/([^/?#]+)")


def load_cases() -> list[dict]:
    tree = ast.parse(LEGACY_APP.read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == "CASE_LIST"
            for target in node.targets
        ):
            return ast.literal_eval(node.value)
    raise RuntimeError("找不到 CASE_LIST")


def all_nodes(value):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from all_nodes(child)
    elif isinstance(value, list):
        for child in value:
            yield from all_nodes(child)


def node_text(node: dict) -> str:
    return " ".join(
        str(item.get("text", "")).strip()
        for item in all_nodes(node)
        if item.get("type") == "text" and str(item.get("text", "")).strip()
    )


def hash_object(path: Path) -> str:
    return subprocess.check_output(
        ["git", "hash-object", str(path)], cwd=ROOT, text=True
    ).strip()


def card_actions(card: dict) -> list[tuple[str, str]]:
    actions: list[tuple[str, str]] = []
    for node in all_nodes(card):
        action = node.get("action")
        if isinstance(action, dict) and action.get("type") == "uri" and action.get("uri"):
            actions.append((node_text(node), str(action["uri"])))
    return actions


def liff_id_from_html(content: str) -> str | None:
    match = re.search(r'const LIFF_ID\s*=\s*["\']([^"\']+)["\']', content)
    return match.group(1) if match else None


def duplicate_values(items: list) -> list:
    counts = Counter(items)
    return sorted(value for value, count in counts.items() if count > 1)


def main() -> int:
    errors: list[str] = []
    warnings: list[str] = []
    cases = load_cases()

    if not MEMBER_DATA.exists():
        errors.append("找不到可搜尋人物資料 ai-MRbot/data/chapter_members.json")
    else:
        try:
            member_data = json.loads(MEMBER_DATA.read_text(encoding="utf-8"))
            members = member_data.get("members", [])
            member_names = [item.get("name") for item in members]
            if member_data.get("member_count") != len(members) or not members:
                errors.append("chapter_members.json 的 member_count 不正確")
            if duplicate_values(member_names):
                errors.append(f"chapter_members.json 姓名重複：{duplicate_values(member_names)}")
            forbidden = {"phone", "提供", "收到", "來賓", "一對一", "遲到", "缺席"}
            if any(forbidden.intersection(item) for item in members if isinstance(item, dict)):
                errors.append("chapter_members.json 含有不必要的電話或績效欄位")
        except Exception as exc:
            errors.append(f"chapter_members.json 無法解析：{exc}")

    case_ids = [str(item.get("case", "")) for item in cases]
    nums = [item.get("num") for item in cases]
    keywords = [str(item.get("keyword", "")) for item in cases]
    for label, values in (("case", case_ids), ("num", nums), ("keyword", keywords)):
        duplicates = duplicate_values(values)
        if duplicates:
            errors.append(f"CASE_LIST 的 {label} 重複：{duplicates}")

    liff_owner: dict[str, str] = {}
    checked_images: set[Path] = set()
    for item in cases:
        case_id = str(item.get("case", ""))
        match = re.fullmatch(r"case(\d+)_(.+)", case_id)
        if not match:
            errors.append(f"CASE_LIST 格式錯誤：{case_id}")
            continue
        expected_num = int(match.group(1))
        name = match.group(2)
        if item.get("num") != expected_num:
            errors.append(f"{case_id}: num 應為 {expected_num}，目前是 {item.get('num')}")
        if item.get("keyword") != name:
            errors.append(f"{case_id}: keyword 應為 {name}，目前是 {item.get('keyword')}")

        folder = TEMPLATES / case_id
        json_path = folder / f"card_{name}.json"
        liff_path = folder / f"liff_{name}.html"
        if not folder.is_dir():
            errors.append(f"{case_id}: 找不到人物資料夾")
            continue
        if not json_path.exists():
            errors.append(f"{case_id}: 找不到 {json_path.name}")
            continue
        if not liff_path.exists():
            errors.append(f"{case_id}: 找不到 {liff_path.name}")
            continue

        try:
            card = json.loads(json_path.read_text(encoding="utf-8"))
        except Exception as exc:
            errors.append(f"{case_id}: JSON 無法解析：{exc}")
            continue
        pages = card.get("contents") if isinstance(card, dict) else None
        if card.get("type") != "carousel" or not isinstance(pages, list) or not pages:
            errors.append(f"{case_id}: JSON 必須是非空的 carousel")
            continue

        if "⚠️ 待補連結" in json_path.read_text(encoding="utf-8"):
            errors.append(f"{case_id}: 仍有 ⚠️ 待補連結")

        for page_no, page in enumerate(pages, start=1):
            images = [node for node in all_nodes(page) if node.get("type") == "image" and node.get("url")]
            if len(images) != 1:
                errors.append(f"{case_id}: 第 {page_no} 頁應有一張主圖，目前有 {len(images)} 張")
            for image in images:
                url = str(image["url"])
                parsed = urlparse(url)
                if parsed.netloc != PAGES_HOST or not parsed.path.startswith(PAGES_PREFIX):
                    errors.append(f"{case_id}: 第 {page_no} 頁不是 GitHub Pages 圖片網址：{url}")
                    continue
                relative = Path(unquote(parsed.path[len(PAGES_PREFIX):]))
                local = ROOT / relative
                if not local.is_file():
                    errors.append(f"{case_id}: 第 {page_no} 頁圖片不存在：{relative}")
                    continue
                checked_images.add(local)
                if local.suffix.lower() == ".png":
                    warnings.append(f"{case_id}: 第 {page_no} 頁仍使用 PNG，圖片最佳化流程會轉成 JPG")
                version = parse_qs(parsed.query).get("v", [""])[0]
                expected = hash_object(local)[:12]
                if version != expected:
                    errors.append(
                        f"{case_id}: 第 {page_no} 頁版本碼錯誤，應為 {expected}，目前是 {version or '空白'}"
                    )

        share_ids = []
        for label, uri in card_actions(card):
            match = LIFF_RE.match(uri)
            if match and "分享" in label and "名片" in label:
                share_ids.append(match.group(1))
        unique_share_ids = sorted(set(share_ids))
        if len(unique_share_ids) != 1:
            errors.append(f"{case_id}: 分享按鈕必須有唯一 LIFF ID，目前是 {unique_share_ids}")
            continue
        share_id = unique_share_ids[0]

        content = liff_path.read_text(encoding="utf-8")
        loader_id = liff_id_from_html(content)
        if loader_id != share_id:
            errors.append(f"{case_id}: LIFF HTML 的 ID 與 JSON 分享按鈕不一致")
        if "const flexContent" in content:
            errors.append(f"{case_id}: LIFF 仍內嵌整份名片，尚未統一")
        if f'const CARD_JSON_URL = "./{json_path.name}";' not in content:
            errors.append(f"{case_id}: LIFF 沒有指向 {json_path.name}")
        if 'cache: "no-store"' not in content or "shareTargetPicker" not in content:
            errors.append(f"{case_id}: LIFF 缺少即時讀取或分享功能")
        previous = liff_owner.get(share_id)
        if previous:
            errors.append(f"LIFF ID {share_id} 同時用於 {previous} 與 {case_id}")
        else:
            liff_owner[share_id] = case_id

        expected_short = hashlib.sha256(f"mr-card:{case_id}".encode()).hexdigest()[:10]
        print(f"✓ {case_id}: {len(pages)} 頁，LIFF {share_id}，短碼 {expected_short}")

    extra_folders = sorted(
        path.name for path in TEMPLATES.glob("case*") if path.is_dir() and path.name not in set(case_ids)
    )
    if extra_folders:
        warnings.append(f"尚未加入 CASE_LIST，未驗證：{', '.join(extra_folders)}")

    for warning in warnings:
        print(f"警告：{warning}")
    if errors:
        for error in errors:
            print(f"錯誤：{error}", file=sys.stderr)
        print(f"驗證失敗：{len(errors)} 個錯誤、{len(warnings)} 個警告", file=sys.stderr)
        return 1
    print(f"驗證成功：{len(cases)} 位人物、{len(checked_images)} 張圖片、{len(warnings)} 個警告")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
