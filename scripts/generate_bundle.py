#!/usr/bin/env python3
"""
生成 output/ai_bundle/{YYYY-MM-DD}_{session}_bundle.md，供 LLM 配合 prompt 做筛选、分类、总结。
V1 仅实现 premarket；midday / intraday / postmarket 为 Phase 2 预留。
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

# Phase 2 sessions（当前仅占位）
# midday：盘中午间，数据源 = 上午盘中快讯 + 上午行情
# intraday：盘中快报，数据源 = 实时快讯
# postmarket：盘后，数据源 = 全天新闻 + 收盘行情 + 资金流向


def _load_market(date_str: str):
    """读取 raw/market/daily_{compact}.json，不存在返回 None。"""
    compact = date_str_to_compact(date_str)
    path = RAW_DIR / "market" / f"daily_{compact}.json"
    if not path.exists():
        return None
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def _format_time_to_minute(published: str) -> str:
    """将 published 截取到分钟，如 2026-03-09 22:30。"""
    if not published:
        return ""
    s = (published or "").strip()
    if not s:
        return ""
    # 常见格式：2026-03-09T22:30:00Z / 2026-03-09 22:30:00 / 2026-03-09
    for sep in ("T", " "):
        if sep in s:
            part = s.split(sep)[0]
            rest = s.split(sep)[-1] if sep in s else ""
            if rest and ":" in rest:
                minute_part = rest.split(":")[0] + ":" + rest.split(":")[1]
                return f"{part} {minute_part}"
            return part
    return s[:16] if len(s) >= 16 else s


def _build_premarket_bundle(date_str: str, logger=None) -> list:
    """拼装 premarket bundle 的 Markdown 行。"""
    compact = date_str_to_compact(date_str)
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    lines = []

    # 数据源
    sources_cfg = load_sources()
    active_names = [s.get("name", "") for s in sources_cfg.get("active", []) if s.get("name")]
    source_line = "、".join(active_names) if active_names else "—"

    # 一、四大指数
    market = _load_market(date_str)
    indices = (market or {}).get("indices") or []
    lines.append("## 一、四大指数")
    lines.append("")
    if not indices:
        lines.append("行情数据未就绪")
        lines.append("")
    else:
        lines.append("| 指数 | 收盘 | 涨跌幅 | 成交额(亿) |")
        lines.append("|------|------|--------|-----------|")
        for item in indices:
            name = item.get("name", "")
            close = item.get("close")
            pct = item.get("pct_chg")
            amount_yi = item.get("amount_yi")
            close_str = f"{float(close):,.2f}" if close is not None else "-"
            if pct is not None:
                sign = "+" if pct >= 0 else ""
                pct_str = f"{sign}{pct:.2f}%"
            else:
                pct_str = "-"
            amount_str = f"{amount_yi:,.1f}" if amount_yi is not None else "-"
            lines.append(f"| {name} | {close_str} | {pct_str} | {amount_str} |")
        lines.append("")
    lines.append("")

    # 二、持仓标的行情
    watchlist = load_watchlist()
    symbols_raw = watchlist.get("symbols") or []
    note_by_sym = {}
    for s in symbols_raw:
        if isinstance(s, dict):
            sym = (s.get("symbol") or s.get("code") or "").strip()
            if sym:
                note_by_sym[sym] = s.get("note", "-")
        elif isinstance(s, str) and s.strip():
            note_by_sym[s.strip()] = "-"

    stocks = (market or {}).get("stocks") or []
    lines.append("## 二、持仓标的行情")
    lines.append("")
    if not symbols_raw:
        lines.append("暂无持仓配置")
        lines.append("")
    elif not stocks:
        lines.append("| 标的 | 收盘 | 涨跌幅 | MA5 | MA20 | 备注 |")
        lines.append("|------|------|--------|-----|------|------|")
        for sym in symbols_raw:
            s = (sym.get("symbol") or sym.get("code") or "") if isinstance(sym, dict) else str(sym).strip()
            note = (sym.get("note", "-") if isinstance(sym, dict) else note_by_sym.get(s, "-"))
            lines.append(f"| {s} | - | - | - | - | {note} |")
        lines.append("")
    else:
        stock_by_code = {str(s.get("code", "")).strip(): s for s in stocks if s.get("code")}
        lines.append("| 标的 | 收盘 | 涨跌幅 | MA5 | MA20 | 备注 |")
        lines.append("|------|------|--------|-----|------|------|")
        for sym in symbols_raw:
            if isinstance(sym, dict):
                s = (sym.get("symbol") or sym.get("code") or "").strip()
                note = sym.get("note", "-")
            else:
                s = str(sym).strip()
                note = note_by_sym.get(s, "-")
            row = stock_by_code.get(s) or (stock_by_code.get(s[:6]) if len(s) >= 6 else None)
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
                name = row.get("name") or s
                lines.append(f"| {name} | {close_str} | {pct_str} | {ma5_str} | {ma20_str} | {note} |")
            else:
                lines.append(f"| {s} | - | - | - | - | {note} |")
        lines.append("")
    lines.append("")

    # 三、今日新闻全量
    clean_path = CLEAN_DIR / f"{compact}.json"
    entries = []
    if clean_path.exists():
        try:
            with open(clean_path, encoding="utf-8") as f:
                data = json.load(f)
            entries = data.get("entries", [])
        except Exception:
            pass

    def _sort_key(e):
        pub = e.get("published") or e.get("pub_time") or ""
        return (pub, 0)

    entries.sort(key=_sort_key, reverse=True)
    n_news = len(entries)

    lines.append("## 三、今日新闻全量（共 {} 条）".format(n_news))
    lines.append("")
    for i, e in enumerate(entries, 1):
        title = (e.get("title") or "(无标题)").replace("\n", " ")
        source = (e.get("source_name") or e.get("source_id") or "—").strip()
        time_str = _format_time_to_minute(e.get("published") or e.get("pub_time") or "")
        summary = (e.get("summary") or "").strip()
        lines.append(f"### {i}")
        lines.append("- 标题：" + title)
        lines.append("- 来源：" + source)
        lines.append("- 时间：" + time_str)
        lines.append("- 摘要：" + summary)
        lines.append("")
    lines.append("")

    # 文件头
    header = [
        f"# Market Eyes 数据包 — {date_str} premarket",
        "",
        f"> 自动生成于 {timestamp} | 共 {n_news} 条新闻 | 数据源：{source_line}",
        "",
        "---",
        "",
    ]
    return header + lines


def generate_bundle(date_str: str, session: str = "premarket", logger=None):
    """
    生成 AI bundle 文件。
    V1 仅实现 premarket；其他 session 记录日志并返回 None。
    返回生成的文件路径（Path），失败或未实现返回 None。
    """
    if session != "premarket":
        if logger:
            logger.info("session=%s 尚未实现，跳过", session)
        return None

    # premarket：数据源 = 隔夜新闻 + 昨日行情
    try:
        lines = _build_premarket_bundle(date_str, logger=logger)
    except Exception as e:
        if logger:
            logger.warning("generate_bundle premarket 失败: %s", e)
        return None

    out_dir = OUTPUT_DIR / "ai_bundle"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{date_str}_{session}_bundle.md"
    out_path.write_text("\n".join(lines), encoding="utf-8")
    if logger:
        logger.info("generate_bundle 已写入 %s", out_path.name)
    return out_path


if __name__ == "__main__":
    import argparse
    from utils import setup_logging
    p = argparse.ArgumentParser()
    p.add_argument("--date", required=True, help="YYYY-MM-DD")
    p.add_argument("--session", default="premarket", choices=["premarket", "midday", "intraday", "postmarket"])
    args = p.parse_args()
    log = setup_logging(args.date)
    result = generate_bundle(args.date, session=args.session, logger=log)
    if result:
        print(f"  ✅ {result}")
