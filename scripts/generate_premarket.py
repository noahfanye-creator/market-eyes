#!/usr/bin/env python3
"""
生成 output/premarket/YYYY-MM-DD_premarket.md。
半结构化结论：今日环境 / 大盘概览 / 今日必盯 / Top 10 / 持仓速览 / 元信息。
仅使用 pipeline 传入的 date_str，不取“今天”。
"""

import json
from datetime import datetime, timezone
from pathlib import Path

from utils import (
    CLEAN_DIR,
    OUTPUT_DIR,
    RAW_DIR,
    load_sources,
    load_watchlist,
    date_str_to_compact,
)


def _load_market_data(date_str: str):
    """读取 raw/market/daily_YYYYMMDD.json，不存在返回 None。"""
    compact = date_str_to_compact(date_str)
    path = RAW_DIR / "market" / f"daily_{compact}.json"
    if not path.exists():
        return None
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def _assess_environment(indices: list) -> str:
    """
    根据四大指数涨跌判断氛围。有指数数据时用指数逻辑，否则返回 fallback 文案。
    """
    if not indices or len(indices) < 4:
        return ""
    pcts = []
    for item in indices:
        pct = item.get("pct_chg")
        if pct is None:
            return ""
        pcts.append(float(pct))
    all_up = all(p >= 0 for p in pcts)
    all_down = all(p <= 0 for p in pcts)
    any_big_down = any(p <= -2.0 for p in pcts)
    if any_big_down:
        return "防守"
    if all_up:
        return "偏强"
    if all_down:
        return "偏弱"
    return "分化"


def _build_environment(data: dict, by_category: dict) -> list:
    """今日环境 + 重点方向 + 风险点。"""
    lines = [
        "## 今日环境",
        "",
    ]
    market = _load_market_data(data.get("date_str", ""))
    indices = (market or {}).get("indices") or []
    assessment = _assess_environment(indices) if indices else ""
    if assessment:
        lines.append(f"- 大盘氛围：**{assessment}**（基于四大指数涨跌）。")
    lines.append("- 数据源：骨架源（财联社、金十）汇总，按日去重。")
    lines.append("- 宏观/政策：见下方分类摘要。")
    lines.append("")
    lines.append("## 重点方向")
    lines.append("")
    for cat, items in list(by_category.items())[:5]:
        if not items:
            continue
        lines.append(f"- **{cat}**：共 {len(items)} 条；示例：{items[0].get('title', '')[:50]}...")
    if not by_category:
        lines.append("- （暂无分类数据）")
    lines.append("")
    lines.append("## 风险点")
    lines.append("")
    lines.append("- 以当日快讯与公告为准，无额外风险评级。")
    lines.append("")
    return lines


def _build_market_overview(date_str: str) -> list:
    """大盘概览表：从 raw/market/daily_{date}.json 读 indices。"""
    lines = [
        "## 大盘概览",
        "",
    ]
    market = _load_market_data(date_str)
    indices = (market or {}).get("indices") or []
    if not indices:
        lines.append("_行情数据未就绪_")
        lines.append("")
        return lines
    lines.append("| 指数 | 收盘 | 涨跌幅 | 成交额(亿) |")
    lines.append("|------|------|--------|-----------|")
    for item in indices:
        name = item.get("name", "")
        close = item.get("close")
        pct = item.get("pct_chg")
        amount_yi = item.get("amount_yi")
        if close is not None:
            close_str = f"{float(close):,.2f}"
        else:
            close_str = "-"
        if pct is not None:
            sign = "+" if pct >= 0 else ""
            pct_str = f"{sign}{pct:.2f}%"
        else:
            pct_str = "-"
        if amount_yi is not None:
            amount_str = f"{amount_yi:,.1f}"
        else:
            amount_str = "-"
        lines.append(f"| {name} | {close_str} | {pct_str} | {amount_str} |")
    lines.append("")
    return lines


def _build_must_watch(entries: list) -> list:
    """今日必盯 Top 5。"""
    lines = ["## 今日必盯", ""]
    for i, e in enumerate(entries[:5], 1):
        lines.append(f"{i}. [{e.get('title', '(无标题)')[:60]}]({e.get('link', '')})")
    lines.append("")
    return lines


def _build_top_items(entries: list) -> list:
    """重要信息 Top 10。"""
    lines = ["## Top 10", ""]
    for i, e in enumerate(entries[:10], 1):
        lines.append(f"{i}. [{e.get('title', '(无标题)')[:60]}]({e.get('link', '')}) — {e.get('source_name', '')}")
    lines.append("")
    return lines


def _build_holdings_table(date_str: str, symbols: list) -> list:
    """持仓速览：有行情则用 stocks 填涨跌/MA，否则占位表。"""
    lines = ["## 持仓速览", ""]
    market = _load_market_data(date_str)
    stocks = (market or {}).get("stocks") or []
    stock_by_code = {str(s.get("code", "")).strip(): s for s in stocks if s.get("code")}

    if not symbols:
        lines.append("暂无持仓/观察列表，请在 config/watchlist.json 配置 symbols。")
        lines.append("")
        return lines

    if stocks:
        lines.append("| 标的 | 收盘 | 涨跌幅 | MA5 | MA20 | 备注 |")
        lines.append("|------|------|--------|-----|------|------|")
        for s in symbols:
            if isinstance(s, dict):
                sym = (s.get("symbol") or s.get("code") or "").strip()
                note = s.get("note", "-")
            else:
                sym = str(s).strip()
                note = "-"
            row = stock_by_code.get(sym) or (stock_by_code.get(sym[:6]) if len(sym) >= 6 else None)
            if row:
                close = row.get("close")
                close_str = f"{float(close):,.2f}" if close is not None else "-"
                pct = row.get("pct_chg")
                if pct is not None:
                    sign = "+" if pct >= 0 else ""
                    pct_str = f"{sign}{pct:.2f}%"
                else:
                    pct_str = "-"
                ma5 = row.get("ma5")
                ma20 = row.get("ma20")
                ma5_str = f"{ma5:.2f}" if ma5 is not None else "-"
                ma20_str = f"{ma20:.2f}" if ma20 is not None else "-"
                name = row.get("name") or sym
                lines.append(f"| {name} | {close_str} | {pct_str} | {ma5_str} | {ma20_str} | {note} |")
            else:
                lines.append(f"| {sym} | - | - | - | - | {note} |")
    else:
        lines.append("| 标的 | 备注 |")
        lines.append("|------|------|")
        for s in symbols:
            if isinstance(s, dict):
                lines.append(f"| {s.get('symbol', s)} | {s.get('note', '-')} |")
            else:
                lines.append(f"| {s} | - |")
    lines.append("")
    return lines


def _build_stats(data: dict, date_str: str, by_category_all: dict) -> list:
    """元信息。"""
    lines = [
        "---",
        "",
        "## 元信息",
        "",
    ]
    gen_time = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    lines.append(f"- **生成时间**：{gen_time}")
    sources_cfg = load_sources()
    active_names = [s.get("name", "") for s in sources_cfg.get("active", []) if s.get("name")]
    lines.append(f"- **活跃源**：{', '.join(active_names) or '-'}")
    raw_count = data.get("raw_count", 0)
    total = data.get("total", 0)
    lines.append(f"- **原始条目数**：{raw_count}")
    lines.append(f"- **去重后条目数**：{total}")
    lines.append("- **分类统计**：")
    for cat, items in sorted(by_category_all.items(), key=lambda x: -len(x[1])):
        lines.append(f"  - {cat}: {len(items)} 条")
    lines.append("")
    lines.append(f"*生成自 Market Eyes V1，date={date_str}*")
    return lines


def run_generate_premarket(date_str: str) -> None:
    compact = date_str_to_compact(date_str)
    clean_path = CLEAN_DIR / f"{compact}.json"
    if not clean_path.exists():
        print(f"  ⚠ 未找到 {clean_path}")
        return
    with open(clean_path, encoding="utf-8") as f:
        data = json.load(f)
    entries_all = data.get("entries", [])
    entries = [e for e in entries_all if not e.get("_experimental")]
    by_category_all = data.get("by_category", {})
    by_category = {k: [e for e in v if not e.get("_experimental")] for k, v in by_category_all.items()}
    by_category = {k: v for k, v in by_category.items() if v}

    watchlist = load_watchlist()
    symbols = watchlist.get("symbols") or []

    # 注入 date_str 供 _build_environment 等使用
    data["date_str"] = date_str

    parts = [
        f"# 盘前卡 Premarket — {date_str}",
        "",
        "> **机器初稿**：供参考，非最终判断。完整原料见 `output/ai_bundle/`。",
        "",
        "---",
        "",
    ]
    parts.extend(_build_environment(data, by_category))
    parts.extend(_build_market_overview(date_str))
    parts.extend(_build_must_watch(entries))
    parts.extend(_build_top_items(entries))
    parts.extend(_build_holdings_table(date_str, symbols))
    parts.extend(_build_stats(data, date_str, by_category_all))

    out_dir = OUTPUT_DIR / "premarket"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{date_str}_premarket.md"
    out_path.write_text("\n".join(parts), encoding="utf-8")
    print(f"  ✅ output/premarket/{date_str}_premarket.md")


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--date", required=True, help="YYYY-MM-DD")
    args = p.parse_args()
    run_generate_premarket(args.date)
