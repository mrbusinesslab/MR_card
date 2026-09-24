#!/usr/bin/env python3
"""Extract a searchable, privacy-minimized member directory from the BNI PDF."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import date
from pathlib import Path

import pdfplumber


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "ai-MRbot" / "分會-職位-報告.pdf"
OUTPUT = ROOT / "ai-MRbot" / "data" / "chapter_members.json"


def compact(value: str | None) -> str:
    return re.sub(r"\s+", "", value or "")


def spaced_name(value: str | None) -> str:
    return re.sub(r"\s+", " ", (value or "").strip())


def parse_leadership(text: str) -> list[dict[str, str]]:
    roles: list[dict[str, str]] = []
    phone_pattern = r"(?:\+?\d[\d -]{6,}\d|\d{8,})"
    for raw_line in text.splitlines():
        line = re.sub(r"\s+", " ", raw_line.strip())
        match = re.match(rf"(.+?)\s+([\u4e00-\u9fff]+\s+[\u4e00-\u9fff]{{1,2}})\s+{phone_pattern}$", line)
        if not match:
            continue
        role, name = match.groups()
        roles.append({"role": role.strip(), "name": compact(name)})
    return roles


def main() -> int:
    members: list[dict] = []
    leadership: list[dict[str, str]] = []
    chapter = ""
    report_generated_at = ""

    with pdfplumber.open(SOURCE) as pdf:
        for page_number, page in enumerate(pdf.pages, start=1):
            tables = page.extract_tables()
            if page_number == 1 and tables:
                metadata = tables[0]
                header = metadata[1]
                chapter = re.sub(r"^分會\s*", "", (header[5] or "").replace("\n", " ")).strip()
                generated = (header[1] or "").replace("營運在\n", "").replace("\n", " ").strip()
                report_generated_at = generated
                leadership = parse_leadership(metadata[-1][0] or "")

            member_table = tables[-1] if tables else []
            for row in member_table[2:]:
                if len(row) < 5 or not row[0] or not row[2] or not row[3]:
                    continue
                display_name = spaced_name(row[0])
                name = compact(row[0])
                occupation = compact(row[2])
                company = compact(row[3])
                occupation_path = []
                for part in (part.strip() for part in occupation.split(">") if part.strip()):
                    if part not in occupation_path:
                        occupation_path.append(part)
                search_terms = []
                for term in [name, display_name, company, *occupation_path]:
                    if term and term not in search_terms:
                        search_terms.append(term)
                members.append(
                    {
                        "name": name,
                        "display_name": display_name,
                        "company": company,
                        "occupation_path": occupation_path,
                        "chapter_roles": [
                            item["role"] for item in leadership if item["name"] == name
                        ],
                        "search_terms": search_terms,
                        "source_page": page_number,
                    }
                )

    members.sort(key=lambda item: (item["source_page"], item["name"]))
    payload = {
        "schema_version": 1,
        "source": SOURCE.relative_to(ROOT).as_posix(),
        "source_sha256": hashlib.sha256(SOURCE.read_bytes()).hexdigest(),
        "report_generated_at": report_generated_at,
        "extracted_on": date.today().isoformat(),
        "chapter": chapter,
        "privacy_note": "僅保留建立人物資料所需欄位；電話與績效統計未匯出。",
        "member_count": len(members),
        "leadership": leadership,
        "members": members,
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"完成：{len(members)} 位會員 -> {OUTPUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
