#!/usr/bin/env python3
"""从 raw/clean 数据生成最小化 JSON bundle，供 LLM 按模板生成报告。
- premarket_bundle.json：盘前预案用（保持）
- intraday：{date}_intraday_1000_bundle.json / {date}_intraday_1400_bundle.json
- midday：{date}_midday_bundle.json
- postmarket：{date}_postmarket_bundle.json
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from utils import CLEAN_DIR, OUTPUT_BUNDLE_DIR, RAW_DIR, OUTPUT_DIR, load_watchlist, date_str_to_compact


def _load_daily_market(date_str: str) -> dict:
    compact = date_str_to_compact(date_str)
    path = RAW_DIR / "market" / f"daily_{compact}.json"
    if not path.exists():
        return {}
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _load_realtime(date_str: str) -> dict:
    compact = date_str_to_compact(date_str)
    path = RAW_DIR / "market" / f"realtime_{compact}.json"
    if not path.exists():
        return {}
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _load_clean(date_str: str) -> dict:
    compact = date_str_to_compact(date_str)
    path = CLEAN_DIR / f"{compact}.json"
    if not path.exists():
        return {}
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _load_clean_intraday(date_str: str) -> dict:
    compact = date_str_to_compact(date_str)
    path = CLEAN_DIR / f"{compact}_intraday.json"
    if not path.exists():
        return {}
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _load_premarket_summary(date_str: str, max_lines: int = 40) -> str:
    path = OUTPUT_DIR / "premarket" / f"{date_str}_premarket.md"
    if not path.exists():
        return ""
    text = path.read_text(encoding="utf-8")
    return "\n".join(text.strip().split("\n")[:max_lines])


def _index_snapshot_item(x: dict) -> dict:
    """单条指数快照：current/open/pre_close/pct_chg，缺 pre_close 时用 current/(1+pct_chg/100) 反推。"""
    close = x.get("close")
    pct_chg = x.get("pct_chg")
    prev = x.get("prev_close")
    if prev is None and close is not None and pct_chg is not None and pct_chg != -100:
        try:
            prev = round(close / (1 + pct_chg / 100.0), 2)
        except (TypeError, ZeroDivisionError):
            pass
    return {
        "name": x.get("name"),
        "current": close,
        "pct_chg": pct_chg,
        "open": x.get("open"),
        "pre_close": prev,
    }


def build_premarket_bundle_json(date_str: str, logger=None) -> Path | None:
    """
    生成 output/ai_bundle/{date}_premarket_bundle.json。
    结构：report_meta, yesterday_a, overnight, news_increments, watchlist_mapping。
    """
    daily = _load_daily_market(date_str)
    clean = _load_clean(date_str)
    watchlist = load_watchlist()
    compact = date_str_to_compact(date_str)
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

    indices = daily.get("indices") or []
    sectors_top = daily.get("sectors_top") or []
    sectors_bottom = daily.get("sectors_bottom") or []
    overnight = daily.get("overnight") or []
    stocks = daily.get("stocks") or []
    symbols_raw = watchlist.get("symbols") or []

    # 新闻按分类整理（简化：只保留 title, source, published, category）
    entries = clean.get("entries") or []
    news_list = []
    for e in entries[:80]:
        news_list.append({
            "title": (e.get("title") or "")[:200],
            "source": e.get("source_name") or e.get("source_id") or "",
            "published": e.get("published") or e.get("pub_time") or "",
            "category": e.get("category") or "",
        })

    bundle = {
        "report_meta": {
            "report_type": "premarket_plan",
            "date": date_str,
            "generated_at": ts,
        },
        "yesterday_a": {
            "indices": [{"name": x.get("name"), "close": x.get("close"), "pct_chg": x.get("pct_chg"), "amount_yi": x.get("amount_yi")} for x in indices],
            "sectors_top": [{"name": s.get("name"), "pct_chg": s.get("pct_chg")} for s in sectors_top],
            "sectors_bottom": [{"name": s.get("name"), "pct_chg": s.get("pct_chg")} for s in sectors_bottom],
        },
        "overnight": [{"name": x.get("name"), "close": x.get("close"), "pct_chg": x.get("pct_chg")} for x in overnight],
        "news_increments": news_list,
        "watchlist_mapping": {
            "symbols": [
                (s.get("symbol") or s.get("code") or "").strip()
                for s in symbols_raw
                if isinstance(s, dict) and (s.get("symbol") or s.get("code"))
            ]
            + [s.strip() for s in symbols_raw if isinstance(s, str) and s.strip()],
            "stocks": [{"name": s.get("name"), "code": s.get("code"), "pct_chg": s.get("pct_chg"), "ma5": s.get("ma5"), "ma20": s.get("ma20")} for s in stocks],
        },
    }

    OUTPUT_BUNDLE_DIR.mkdir(parents=True, exist_ok=True)
    out_path = OUTPUT_BUNDLE_DIR / f"{date_str}_premarket_bundle.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(bundle, f, ensure_ascii=False, indent=2)
    if logger:
        logger.info("premarket_bundle.json 已写入 %s", out_path.name)
    return out_path


def _snapshot_time_to_suffix(snapshot_time: str) -> str:
    """10:00 -> 1000, 14:00 -> 1400"""
    return snapshot_time.replace(":", "")


def build_intraday_bundle_json(date_str: str, snapshot_time: str = "10:00", logger=None) -> Path | None:
    """
    盘中数据包（仅素材）。snapshot_time 为 "10:00" 或 "14:00"。
    输出：{date}_intraday_1000_bundle.json 或 {date}_intraday_1400_bundle.json
    """
    realtime = _load_realtime(date_str)
    clean_intraday = _load_clean_intraday(date_str)
    premarket_key_points = _load_premarket_summary(date_str)

    indices = realtime.get("indices") or []
    sectors_top = (realtime.get("sectors_top") or [])[:3]
    sectors_bottom = (realtime.get("sectors_bottom") or [])[:3]
    watchlist = realtime.get("watchlist") or []
    entries = clean_intraday.get("entries") or []

    bundle = {
        "date": date_str,
        "snapshot_time": snapshot_time,
        "indices": [_index_snapshot_item(x) for x in indices],
        "sectors_top3": [{"name": s.get("name"), "pct_chg": s.get("pct_chg")} for s in sectors_top],
        "sectors_bottom3": [{"name": s.get("name"), "pct_chg": s.get("pct_chg")} for s in sectors_bottom],
        "leaders": [
            {"name": x.get("name"), "pct_chg": x.get("pct_chg"), "status_summary": x.get("status_summary") or ""}
            for x in watchlist
        ],
        "news_increment": [
            {"title": (e.get("title") or "")[:200], "source": e.get("source_name") or e.get("source_id") or "", "published": e.get("published") or e.get("pub_time") or ""}
            for e in entries[:30]
        ],
        "premarket_key_points": (premarket_key_points[:2000] if premarket_key_points else "") or "",
    }

    suffix = _snapshot_time_to_suffix(snapshot_time)
    OUTPUT_BUNDLE_DIR.mkdir(parents=True, exist_ok=True)
    out_path = OUTPUT_BUNDLE_DIR / f"{date_str}_intraday_{suffix}_bundle.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(bundle, f, ensure_ascii=False, indent=2)
    if logger:
        logger.info("intraday_%s_bundle.json 已写入 %s", suffix, out_path.name)
    return out_path


def build_intraday_1000_bundle_json(date_str: str, logger=None) -> Path | None:
    """兼容：生成 10:00 盘中 bundle。"""
    return build_intraday_bundle_json(date_str, snapshot_time="10:00", logger=logger)


def build_midday_bundle_json(date_str: str, logger=None) -> Path | None:
    """
    午盘数据包。输出 {date}_midday_bundle.json。
    数据源：realtime 作上午盘面代理，clean_intraday 作上午快讯，premarket 摘要。
    """
    realtime = _load_realtime(date_str)
    clean_intraday = _load_clean_intraday(date_str)
    premarket_key_points = _load_premarket_summary(date_str)

    indices = realtime.get("indices") or []
    sectors_top = (realtime.get("sectors_top") or [])[:3]
    sectors_bottom = (realtime.get("sectors_bottom") or [])[:3]
    watchlist = realtime.get("watchlist") or []

    bundle = {
        "date": date_str,
        "snapshot_time": "11:30",
        "indices_am": [_index_snapshot_item(x) for x in indices],
        "sectors_top_am": [{"name": s.get("name"), "pct_chg": s.get("pct_chg")} for s in sectors_top],
        "sectors_bottom_am": [{"name": s.get("name"), "pct_chg": s.get("pct_chg")} for s in sectors_bottom],
        "leaders_am": [
            {"name": x.get("name"), "pct_chg": x.get("pct_chg"), "status_summary": x.get("status_summary") or ""}
            for x in watchlist
        ],
        "news_am": [
            {"title": (e.get("title") or "")[:200], "source": e.get("source_name") or e.get("source_id") or "", "published": e.get("published") or e.get("pub_time") or ""}
            for e in (clean_intraday.get("entries") or [])[:30]
        ],
        "emotion_am": {},
        "premarket_key_points": (premarket_key_points[:2000] if premarket_key_points else "") or "",
    }

    OUTPUT_BUNDLE_DIR.mkdir(parents=True, exist_ok=True)
    out_path = OUTPUT_BUNDLE_DIR / f"{date_str}_midday_bundle.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(bundle, f, ensure_ascii=False, indent=2)
    if logger:
        logger.info("midday_bundle.json 已写入 %s", out_path.name)
    return out_path


def _realtime_to_indices_full(realtime: dict) -> list:
    """从 realtime 的 indices 转为 postmarket 的 indices_full 格式（close/pct_chg/amount_yi）。"""
    indices = realtime.get("indices") or []
    out = []
    for x in indices:
        close = x.get("close")
        out.append({
            "name": x.get("name"),
            "close": close,
            "pct_chg": x.get("pct_chg"),
            "amount_yi": x.get("amount_yi"),
        })
    return out


def build_postmarket_bundle_json(date_str: str, logger=None) -> Path | None:
    """
    盘后数据包。输出 {date}_postmarket_bundle.json。
    数据源：优先 daily 行情 + clean 全天新闻；无 daily 时用 realtime 兜底指数/板块/龙头。
    """
    daily = _load_daily_market(date_str)
    clean = _load_clean(date_str)
    realtime = _load_realtime(date_str)

    indices = daily.get("indices") or []
    sectors_top = (daily.get("sectors_top") or [])[:5]
    sectors_bottom = (daily.get("sectors_bottom") or [])[:5]
    stocks = daily.get("stocks") or []

    if not indices and realtime:
        indices = _realtime_to_indices_full(realtime)
        if not sectors_top and realtime.get("sectors_top"):
            sectors_top = (realtime.get("sectors_top") or [])[:5]
        if not sectors_bottom and realtime.get("sectors_bottom"):
            sectors_bottom = (realtime.get("sectors_bottom") or [])[:5]
        if not stocks and realtime.get("watchlist"):
            stocks = [
                {"name": x.get("name"), "pct_chg": x.get("pct_chg"), "code": x.get("code")}
                for x in (realtime.get("watchlist") or [])
            ]
        if logger:
            logger.info("postmarket 使用 realtime 兜底（无 daily）")

    entries = clean.get("entries") or []
    news_full = [
        {"title": (e.get("title") or "")[:200], "source": e.get("source_name") or e.get("source_id") or "", "published": e.get("published") or e.get("pub_time") or "", "category": e.get("category") or ""}
        for e in entries[:80]
    ]

    bundle = {
        "date": date_str,
        "indices_full": [{"name": x.get("name"), "close": x.get("close"), "pct_chg": x.get("pct_chg"), "amount_yi": x.get("amount_yi")} for x in indices],
        "breadth": {},
        "sectors_top": [{"name": s.get("name"), "pct_chg": s.get("pct_chg")} for s in sectors_top],
        "sectors_bottom": [{"name": s.get("name"), "pct_chg": s.get("pct_chg")} for s in sectors_bottom],
        "leaders_and_highflyers": [{"name": s.get("name"), "pct_chg": s.get("pct_chg"), "code": s.get("code")} for s in stocks],
        "flows": {},
        "news_full": news_full,
    }

    OUTPUT_BUNDLE_DIR.mkdir(parents=True, exist_ok=True)
    out_path = OUTPUT_BUNDLE_DIR / f"{date_str}_postmarket_bundle.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(bundle, f, ensure_ascii=False, indent=2)
    if logger:
        logger.info("postmarket_bundle.json 已写入 %s", out_path.name)
    return out_path


def run_build_premarket_bundle(date_str: str, logger=None) -> Path | None:
    """盘前 pipeline 调用：生成 premarket_bundle.json。"""
    return build_premarket_bundle_json(date_str, logger=logger)


def run_build_intraday_bundle(date_str: str, snapshot_time: str | None = None, logger=None) -> list[Path]:
    """盘中 pipeline 调用：snapshot_time 为 None 时生成 10:00 与 14:00 两个；否则只生成该时点。"""
    paths = []
    times = (snapshot_time,) if snapshot_time else ("10:00", "14:00")
    for t in times:
        p = build_intraday_bundle_json(date_str, snapshot_time=t, logger=logger)
        if p:
            paths.append(p)
    return paths


if __name__ == "__main__":
    import argparse
    from utils import setup_logging
    p = argparse.ArgumentParser()
    p.add_argument("--date", required=True, help="YYYY-MM-DD")
    p.add_argument("--type", choices=["premarket", "intraday", "midday", "postmarket", "all"], default="all")
    args = p.parse_args()
    log = setup_logging(args.date)
    if args.type in ("premarket", "all"):
        build_premarket_bundle_json(args.date, logger=log)
    if args.type in ("intraday", "all"):
        run_build_intraday_bundle(args.date, logger=log)
    if args.type in ("midday", "all"):
        build_midday_bundle_json(args.date, logger=log)
    if args.type in ("postmarket", "all"):
        build_postmarket_bundle_json(args.date, logger=log)
    print("  ✅ JSON bundles 已生成")
