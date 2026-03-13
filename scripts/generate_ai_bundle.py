#!/usr/bin/env python3
"""
生成 output/ai_bundle/YYYY-MM-DD_ai_bundle.md，供大模型二次提炼的原料包。
- 时间窗口、来源、正文尽量完整；按来源分组；轻去重后的全量条目，不依赖分类做筛选。
"""

import json
from datetime import datetime, timezone

from utils import CLEAN_DIR, OUTPUT_DIR, date_str_to_compact

SUMMARY_MAX = 800  # 单条 summary 保留长度，避免单文件过大


def run_generate_ai_bundle(date_str: str) -> None:
    compact = date_str_to_compact(date_str)
    clean_path = CLEAN_DIR / f"{compact}.json"
    if not clean_path.exists():
        print(f"  ⚠ 未找到 {clean_path}")
        return
    with open(clean_path, encoding="utf-8") as f:
        data = json.load(f)

    entries = data.get("entries", [])
    # 按来源分组，保留顺序：先出现的来源顺序
    by_source = {}
    for e in entries:
        src = (e.get("source_name") or e.get("source_id") or "未标注来源").strip()
        if src not in by_source:
            by_source[src] = []
        by_source[src].append(e)

    lines = [
        f"# AI 原料包 — {date_str}",
        "",
        "> 供大模型二次提炼使用。轻去重、保留来源与时间，分类为辅助标签，未做筛选。",
        "",
        f"- **时间窗口**：{date_str}",
        f"- **条目总数**：{len(entries)}",
        f"- **生成时间**：{datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}",
        "",
        "---",
        "",
    ]

    for source_name, items in by_source.items():
        lines.append(f"## 来源：{source_name}")
        lines.append("")
        for i, e in enumerate(items, 1):
            title = (e.get("title") or "(无标题)").replace("\n", " ")
            link = e.get("link", "")
            published = e.get("published", "")
            summary = (e.get("summary") or "").strip()
            if len(summary) > SUMMARY_MAX:
                summary = summary[:SUMMARY_MAX] + "…"
            category = e.get("category", "")
            lines.append(f"### [{i}] {title}")
            lines.append("")
            lines.append(f"- **时间**：{published}")
            lines.append(f"- **链接**：{link}")
            if category:
                lines.append(f"- **标签**：{category}")
            lines.append("")
            if summary:
                lines.append(summary)
                lines.append("")
            lines.append("")

    lines.append("---")
    lines.append("")
    lines.append(f"*Market Eyes V1 原料包 · date={date_str}*")

    out_dir = OUTPUT_DIR / "ai_bundle"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{date_str}_ai_bundle.md"
    out_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"  ✅ output/ai_bundle/{date_str}_ai_bundle.md（{len(entries)} 条）")


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--date", required=True, help="YYYY-MM-DD")
    args = p.parse_args()
    run_generate_ai_bundle(args.date)
