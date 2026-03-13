#!/usr/bin/env python3
"""
生成分类验收抽样表 output/category_audit_YYYY-MM-DD.md。
每类抽样 N 条（个股全量），供人工快速抽检分类规则。
"""

import json
import random
from datetime import datetime, timezone

from utils import CLEAN_DIR, OUTPUT_DIR, date_str_to_compact

SAMPLE_SIZE = 10


def run_generate_audit(date_str: str) -> None:
    compact = date_str_to_compact(date_str)
    clean_path = CLEAN_DIR / f"{compact}.json"
    if not clean_path.exists():
        print(f"  ⚠ 未找到 {clean_path}")
        return
    with open(clean_path, encoding="utf-8") as f:
        data = json.load(f)

    by_category = data.get("by_category", {})
    cat_order = ["个股", "宏观", "行业", "政策监管", "综合"]

    lines = [
        f"# 分类验收抽样表 — {date_str}",
        "",
        f"> 总条目: {data.get('total', 0)} | 生成时间: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}",
        "> 个股全量，其余每类抽样最多 10 条。请在「人工标注」列填写你认为正确的分类，「是否接受」填 ✓ 或 ✗。",
        "",
    ]

    seq = 0
    for cat in cat_order:
        items = by_category.get(cat, [])
        if not items:
            continue

        if cat == "个股":
            sampled = items
        elif len(items) <= SAMPLE_SIZE:
            sampled = items
        else:
            sampled = random.sample(items, SAMPLE_SIZE)

        lines.append(f"## {cat}（共 {len(items)} 条，抽样 {len(sampled)} 条）")
        lines.append("")
        lines.append("| # | 标题 | 当前分类 | 人工标注 | 是否接受 | 备注 |")
        lines.append("|---|------|---------|---------|---------|------|")

        for item in sampled:
            seq += 1
            title = (item.get("title") or "").replace("|", "\\|")[:60]
            lines.append(f"| {seq} | {title} | {cat} | | | |")

        lines.append("")

    for cat in sorted(by_category.keys()):
        if cat not in cat_order:
            items = by_category[cat]
            sampled = items[:SAMPLE_SIZE]
            lines.append(f"## {cat}（共 {len(items)} 条，抽样 {len(sampled)} 条）")
            lines.append("")
            lines.append("| # | 标题 | 当前分类 | 人工标注 | 是否接受 | 备注 |")
            lines.append("|---|------|---------|---------|---------|------|")
            for item in sampled:
                seq += 1
                title = (item.get("title") or "").replace("|", "\\|")[:60]
                lines.append(f"| {seq} | {title} | {cat} | | | |")
            lines.append("")

    lines.append("---")
    lines.append("")
    lines.append(f"抽样总计: {seq} 条")

    out_path = OUTPUT_DIR / f"category_audit_{date_str}.md"
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"  ✅ output/category_audit_{date_str}.md ({seq} 条抽样)")


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--date", required=True, help="YYYY-MM-DD")
    args = p.parse_args()
    run_generate_audit(args.date)
