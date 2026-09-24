#!/usr/bin/env python3
"""Generate lightweight LIFF launchers from CASE_LIST and card JSON files."""

from __future__ import annotations

import ast
import html
import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TEMPLATES = ROOT / "ai-MRbot" / "templates"
LEGACY_APP = ROOT / "ai-MRbot" / "legacy_app.py"
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


def descendant_texts(node) -> list[str]:
    texts: list[str] = []
    if isinstance(node, dict):
        if node.get("type") == "text" and node.get("text"):
            texts.append(str(node["text"]).strip())
        for value in node.values():
            texts.extend(descendant_texts(value))
    elif isinstance(node, list):
        for value in node:
            texts.extend(descendant_texts(value))
    return texts


def share_liff_id(card: dict, json_path: Path) -> str:
    matches: list[tuple[str, str]] = []

    def walk(node) -> None:
        if isinstance(node, dict):
            action = node.get("action")
            if isinstance(action, dict) and action.get("type") == "uri":
                match = LIFF_RE.match(str(action.get("uri", "")))
                if match:
                    label = " ".join(descendant_texts(node))
                    matches.append((label, match.group(1)))
            for value in node.values():
                if isinstance(value, (dict, list)):
                    walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)

    walk(card)
    share_matches = [liff_id for label, liff_id in matches if "分享" in label and "名片" in label]
    unique = sorted(set(share_matches))
    if len(unique) != 1:
        raise RuntimeError(f"{json_path}: 找不到唯一的分享名片 LIFF ID（找到 {unique}）")
    return unique[0]


def render_loader(*, title_name: str, liff_id: str, json_name: str, alt_text: str) -> str:
    safe_title = html.escape(title_name)
    return f'''<!DOCTYPE html>
<html lang="zh-Hant">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>分享電子名片 - {safe_title}</title>
  <script src="https://static.line-scdn.net/liff/edge/2/sdk.js"></script>
  <style>
    body {{
      min-height: 100vh;
      margin: 0;
      display: grid;
      place-items: center;
      color: #5f554d;
      background: #ffffff;
      font-family: "Noto Sans TC", "PingFang TC", "Microsoft JhengHei", sans-serif;
    }}
    .status {{ padding: 24px; text-align: center; line-height: 1.7; }}
    .status strong {{ display: block; margin-bottom: 6px; color: #2c2723; }}
  </style>
</head>
<body>
  <p class="status" id="status"><strong>正在開啟分享名片</strong>請稍候…</p>
  <script>
    const LIFF_ID = {json.dumps(liff_id, ensure_ascii=False)};
    const CARD_JSON_URL = {json.dumps('./' + json_name, ensure_ascii=False)};
    const status = document.querySelector("#status");

    async function loadLatestCard() {{
      const response = await fetch(CARD_JSON_URL, {{ cache: "no-store" }});
      if (!response.ok) {{
        throw new Error(`名片資料讀取失敗（HTTP ${{response.status}}）`);
      }}
      const card = await response.json();
      if (card?.type !== "carousel" || !Array.isArray(card?.contents) || !card.contents.length) {{
        throw new Error("名片資料格式不正確");
      }}
      return card;
    }}

    async function shareCard() {{
      const [card] = await Promise.all([
        loadLatestCard(),
        liff.init({{ liffId: LIFF_ID }})
      ]);

      if (!liff.isApiAvailable("shareTargetPicker")) {{
        throw new Error("目前的 LINE 版本不支援好友分享功能");
      }}

      const res = await liff.shareTargetPicker([
        {{
          type: "flex",
          altText: {json.dumps(alt_text, ensure_ascii=False)},
          contents: card
        }}
      ]);

      if (res) {{
        status.innerHTML = "<strong>分享完成</strong>視窗即將關閉";
        liff.closeWindow();
      }} else {{
        status.innerHTML = "<strong>已取消分享</strong>你可以關閉此視窗";
      }}
    }}

    shareCard().catch((error) => {{
      console.error("分享失敗", error);
      status.innerHTML = `<strong>目前無法分享名片</strong>${{error.message || "請稍後再試"}}`;
    }});
  </script>
</body>
</html>
'''


def main() -> int:
    changed = 0
    for case in load_cases():
        folder = TEMPLATES / case["case"]
        keyword = str(case["case"]).split("_", 1)[1]
        json_path = folder / f"card_{keyword}.json"
        liff_path = folder / f"liff_{keyword}.html"
        if not json_path.exists():
            raise RuntimeError(f"找不到 {json_path.relative_to(ROOT)}")
        card = json.loads(json_path.read_text(encoding="utf-8"))
        liff_id = share_liff_id(card, json_path.relative_to(ROOT))
        title_name = str(case.get("alt", keyword)).split("｜", 1)[0].strip() or keyword
        content = render_loader(
            title_name=title_name,
            liff_id=liff_id,
            json_name=json_path.name,
            alt_text=str(case.get("alt", title_name)),
        )
        old = liff_path.read_text(encoding="utf-8") if liff_path.exists() else ""
        if old != content:
            liff_path.write_text(content, encoding="utf-8")
            changed += 1
            print(f"更新 {liff_path.relative_to(ROOT)}")
    print(f"完成：更新 {changed} 份 LIFF")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
