#!/usr/bin/env python3
"""
清洗：读 raw/rss 与 raw/experimental，轻去重、打分类标签，输出 clean/YYYYMMDD.json。
- 轻去重：仅去掉同 link 重复，或同来源+同标题（无 link）重复；不同来源同事件尽量保留。
- 分类仅作辅助标签，不参与是否保留的决策。
"""

import json
import re
from pathlib import Path

from utils import RAW_DIR, CLEAN_DIR, CONFIG_DIR, date_str_to_compact, load_watchlist

_STOCK_CODE_RE = re.compile(
    r'(?:^|[^\d])'
    r'(6\d{5}|0\d{5}|3\d{5}|8[3-9]\d{4}|4[3-9]\d{4})'
    r'(?:\.\w{2})?'
    r'(?:[^\d]|$)'
)


def _load_category_rules():
    p = CONFIG_DIR / "categories.json"
    if not p.exists():
        return None
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def _build_watchlist_names():
    wl = load_watchlist()
    names = []
    for s in wl.get("symbols") or []:
        if isinstance(s, dict):
            for field in ("name", "symbol", "code"):
                v = (s.get(field) or "").strip()
                if v:
                    names.append(v.lower())
        elif isinstance(s, str) and s.strip():
            names.append(s.strip().lower())
    return names


def _is_stock(title, text, raw_text, rules_cfg, watchlist_names):
    """强命中：watchlist → 排除券商晨报 → 股票代码(仅标题) → entity+event"""
    for name in watchlist_names:
        if name in text:
            return True

    exclude_pats = [p.lower() for p in rules_cfg.get("stock_exclude_patterns", [])]
    title_lower = title.lower()
    if any(p in title_lower for p in exclude_pats):
        return False

    if _STOCK_CODE_RE.search(title):
        return True

    entity_words = [w.lower() for w in rules_cfg.get("stock_entity_words", [])]
    event_words = [w.lower() for w in rules_cfg.get("stock_event_words", [])]
    has_entity = any(w in text for w in entity_words)
    has_event = any(w in text for w in event_words)
    return has_entity and has_event


def _classify(entry, rules_cfg, watchlist_names):
    title = (entry.get("title") or "")
    summary = (entry.get("summary") or "")
    text = (title + " " + summary).lower()
    raw_text = title + " " + summary

    if _is_stock(title, text, raw_text, rules_cfg, watchlist_names):
        return "个股"

    for rule in rules_cfg.get("rules", []):
        for kw in rule.get("keywords", []):
            if kw.lower() in text:
                return rule["category"]
    return rules_cfg.get("fallback", "综合")


# 盘中模式：排除低相关、制度类、晨报等噪音
_INTRADAY_EXCLUDE = [
    "晨会", "早班车", "晨报", "周报", "研究早", "早观点", "晨会精粹",
    "财富早", "投资早", "策略早",
    "深圳证券交易所", "上海证券交易所", "北京证券交易所",
    "关于发布", "关于修订", "关于做好", "业务规则", "制度通知",
]


def _load_intraday_config():
    """加载 config/intraday.json，盘中时间窗口用。"""
    p = CONFIG_DIR / "intraday.json"
    if not p.exists():
        return {"premarket_run_time": "08:30", "intraday_run_time": "10:00"}
    try:
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"premarket_run_time": "08:30", "intraday_run_time": "10:00"}


def _in_intraday_window(published: str, date_str: str) -> bool:
    """条目是否在「上次盘前报告 ~ 本次盘中报告」时间窗口内（北京 08:30~10:00）。
    published 通常为 UTC（feedparser 解析），需转为北京时间后比较。"""
    if not published or not date_str:
        return True
    cfg = _load_intraday_config()
    start_h, start_m = _parse_time(cfg.get("premarket_run_time", "08:30"))
    end_h, end_m = _parse_time(cfg.get("intraday_run_time", "10:00"))
    start_min = start_h * 60 + start_m
    end_min = end_h * 60 + end_m
    try:
        from datetime import datetime, timezone, timedelta
        day = date_str[:10]
        if len(published) >= 16:
            pub_d_str = published[:10]
            h, m = int(published[11:13]), int(published[14:16])
            utc_dt = datetime.strptime(f"{pub_d_str} {h:02d}:{m:02d}", "%Y-%m-%d %H:%M").replace(tzinfo=timezone.utc)
            beijing = timezone(timedelta(hours=8))
            bj_dt = utc_dt.astimezone(beijing)
            if bj_dt.strftime("%Y-%m-%d") != day:
                return False
            pub_min = bj_dt.hour * 60 + bj_dt.minute
            return start_min <= pub_min <= end_min
        if len(published) >= 10:
            return published[:10] == day
    except Exception:
        pass
    return True


def _parse_time(t: str) -> tuple:
    """解析 "HH:MM" 或 "H:MM"，返回 (h, m)。"""
    if not t or ":" not in t:
        return 8, 30
    parts = t.strip().split(":")
    return int(parts[0] or 8), int(parts[1] or 30)


def _intraday_filter(entry: dict, rules_cfg: dict) -> bool:
    """盘中强过滤：排除噪音。"""
    title = (entry.get("title") or "").lower()
    for pat in _INTRADAY_EXCLUDE:
        if pat in title:
            return False
    exclude = [p.lower() for p in (rules_cfg or {}).get("stock_exclude_patterns", [])]
    if any(p in title for p in exclude):
        return False
    return True


def run_process(date_str: str, mode: str = "premarket") -> None:
    compact = date_str_to_compact(date_str)
    raw_rss = RAW_DIR / "rss" / f"{compact}.json"
    raw_exp = RAW_DIR / "experimental" / f"{compact}.json"

    entries = []
    if raw_rss.exists():
        with open(raw_rss, encoding="utf-8") as f:
            data = json.load(f)
            entries.extend(data.get("entries", []))
    if raw_exp.exists():
        with open(raw_exp, encoding="utf-8") as f:
            data = json.load(f)
            for e in data.get("entries", []):
                e["_experimental"] = True
            entries.extend(data.get("entries", []))

    raw_count = len(entries)

    # 轻去重：同 link 只保留一条；无 link 时按 (source_id, title) 去重
    seen = set()
    deduped = []
    for e in entries:
        link = (e.get("link") or "").strip()
        title = (e.get("title") or "").strip()
        source_id = (e.get("source_id") or "").strip()
        key = link if link else ("__no_link__", source_id, title)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(e)

    rules_cfg = _load_category_rules()
    watchlist_names = _build_watchlist_names() if rules_cfg else []

    if mode == "intraday":
        deduped = [e for e in deduped if _in_intraday_window(e.get("published") or "", date_str)]
        deduped = [e for e in deduped if _intraday_filter(e, rules_cfg or {})]

    if rules_cfg:
        for e in deduped:
            e["category"] = _classify(e, rules_cfg, watchlist_names)

    by_category = {}
    for e in deduped:
        cat = e.get("category") or "综合"
        if cat not in by_category:
            by_category[cat] = []
        by_category[cat].append(e)

    for cat in by_category:
        by_category[cat].sort(key=lambda x: (x.get("published") or ""), reverse=True)

    # 分类统计
    cat_order = ["宏观", "政策监管", "个股", "行业", "综合"]
    print("  📊 分类统计：")
    for cat in cat_order:
        count = len(by_category.get(cat, []))
        if count > 0:
            print(f"     {cat}: {count} 条")
    for cat in sorted(by_category.keys()):
        if cat not in cat_order:
            print(f"     {cat}: {len(by_category[cat])} 条")

    out = {
        "date": date_str,
        "compact_date": compact,
        "raw_count": raw_count,
        "total": len(deduped),
        "by_category": by_category,
        "entries": deduped,
    }
    CLEAN_DIR.mkdir(parents=True, exist_ok=True)
    if mode == "intraday":
        out_path = CLEAN_DIR / f"{compact}_intraday.json"
    else:
        out_path = CLEAN_DIR / f"{compact}.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print(f"  ✅ clean/{out_path.name}: {len(deduped)} 条（轻去重，分类仅作标签）")


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--date", required=True, help="YYYY-MM-DD")
    p.add_argument("--mode", default="premarket", choices=["premarket", "intraday"])
    args = p.parse_args()
    run_process(args.date, mode=args.mode)
