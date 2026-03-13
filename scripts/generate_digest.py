#!/usr/bin/env python3
"""
生成 output/digest/YYYY-MM-DD_digest.md。
仅使用 pipeline 传入的 date_str。
"""

import json
from pathlib import Path

from utils import CLEAN_DIR, OUTPUT_DIR, date_str_to_compact


def run_generate_digest(date_str: str) -> None:
    compact = date_str_to_compact(date_str)
    clean_path = CLEAN_DIR / f"{compact}.json"
    if not clean_path.exists():
        print(f"  ⚠ 未找到 {clean_path}")
        return
    with open(clean_path, encoding="utf-8") as f:
        data = json.load(f)
    by_category = data.get("by_category", {})
    if not by_category:
        entries = data.get("entries", [])
        by_category = {"未分类": entries}

    lines = [
        f"# 市场摘要 Digest — {date_str}",
        "",
        f"> 共 {data.get('total', 0)} 条（已去重）。",
        "",
    ]
    for cat, items in sorted(by_category.items(), key=lambda x: -len(x[1])):
        lines.append(f"## {cat}")
        lines.append("")
        for it in items:
            title = (it.get("title") or "").replace("|", "\\|")
            link = it.get("link", "")
            pub = it.get("published", "-")
            src = it.get("source_name", "")
            lines.append(f"- [{title}]({link})")
            lines.append(f"  - 来源：{src} | 时间：{pub}")
            if it.get("summary"):
                lines.append(f"  - {it['summary'][:150]}")
            lines.append("")
        lines.append("")

    out_dir = OUTPUT_DIR / "digest"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{date_str}_digest.md"
    out_path.write_text("\n".join(lines).strip() + "\n", encoding="utf-8")
    print(f"  ✅ output/digest/{date_str}_digest.md")


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--date", required=True, help="YYYY-MM-DD")
    args = p.parse_args()
    run_generate_digest(args.date)
