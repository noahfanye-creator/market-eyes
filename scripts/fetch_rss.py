#!/usr/bin/env python3
"""
拉取 RSS：仅使用 pipeline 传入的 date_str，不取“今天”。
使用 requests.get(timeout=15, User-Agent) 后 feedparser.parse(content)。
"""
from __future__ import annotations

import os
import time
from datetime import datetime, timezone

import feedparser
import requests

from utils import (
    CONFIG_DIR,
    RAW_DIR,
    date_str_to_compact,
    load_sources,
)

USER_AGENT = "Mozilla/5.0 (compatible; MarketEyes/1.0)"
TIMEOUT = 25


def _full_url(rsshub_base: str, path: str) -> str:
    base = (rsshub_base or "http://127.0.0.1:1200").rstrip("/")
    p = path.lstrip("/")
    return f"{base}/{p}"


def _parse_published(entry) -> str:
    for key in ("published", "updated", "created"):
        val = entry.get(key)
        if val:
            if hasattr(val, "tm_isdst"):
                return datetime(*val[:6], tzinfo=timezone.utc).strftime("%Y-%m-%d %H:%M")
            if isinstance(val, str):
                return val[:19] if len(val) >= 19 else val
    return ""


def _in_date_range(pub_str: str, date_str: str) -> bool:
    """条目是否在 date_str 前后一天内（含当天），便于跨时区。"""
    if not pub_str or not date_str:
        return True
    try:
        from datetime import timedelta
        day = pub_str[:10]  # "2026-03-09"
        pub_d = datetime.strptime(day, "%Y-%m-%d").date()
        ref_d = datetime.strptime(date_str[:10], "%Y-%m-%d").date()
        return (ref_d - timedelta(days=1)) <= pub_d <= (ref_d + timedelta(days=1))
    except Exception:
        return True


def fetch_feed(name: str, url: str, date_str: str, max_items: int = 50, skip_date_filter: bool = False, fallback_url: str | None = None) -> list[dict]:
    """requests.get + feedparser.parse，按 date_str 过滤（除非 skip_date_filter）。主 URL 失败时尝试 fallback_url。"""
    for attempt_url in [url, fallback_url] if fallback_url else [url]:
        if not attempt_url:
            continue
        try:
            resp = requests.get(attempt_url, timeout=TIMEOUT, headers={"User-Agent": USER_AGENT})
            resp.raise_for_status()
            content = resp.content
            print(f"    → {name}: HTTP {resp.status_code}, body {len(content)} bytes")
            feed = feedparser.parse(content)
            break
        except Exception as e:
            if attempt_url == url:
                print(f"  ⚠ {name}: 请求/解析失败 - {e}")
            if fallback_url and attempt_url == url:
                print(f"    → {name}: 尝试公网 RSSHub 回退...")
                continue
            return []
    else:
        return []

    entry_count = len(feed.entries) if getattr(feed, "entries", None) else 0
    print(f"    → {name}: feedparser 解析到 {entry_count} 条 entry")
    if entry_count == 0:
        return []

    no_link = 0
    date_filtered = 0
    out = []
    for e in feed.entries[:max_items]:
        link = (e.get("link") or "").strip()
        if not link:
            links_list = e.get("links") or []
            for lk in links_list:
                href = (lk.get("href") or "").strip()
                if href:
                    link = href
                    break
        if not link:
            link = (e.get("id") or "").strip()
        if not link:
            no_link += 1
            continue
        published = _parse_published(e)
        if not skip_date_filter and date_str and not _in_date_range(published, date_str):
            date_filtered += 1
            continue
        out.append({
            "title": (e.get("title") or "").strip() or "(无标题)",
            "link": link,
            "published": published,
            "summary": (e.get("summary", "") or "")[:300].strip(),
            "source_name": name,
        })

    print(f"    → {name}: 保留 {len(out)} 条, 无link跳过 {no_link}, 日期过滤 {date_filtered}")
    if entry_count > 0 and len(out) == 0:
        sample = feed.entries[0]
        print(f"    → {name}: 首条 entry keys={list(sample.keys())}")
        print(f"    → {name}: 首条 link={sample.get('link', '__MISSING__')!r}")
        print(f"    → {name}: 首条 published={sample.get('published', '__MISSING__')!r}")
        print(f"    → {name}: 首条 title={str(sample.get('title', '__MISSING__'))[:80]!r}")
    return out


def run_fetch(date_str: str) -> None:
    """拉取 active 源到 raw/rss，experimental 到 raw/experimental。date_str 由 pipeline 传入。"""
    cfg = load_sources()
    if not cfg:
        print("  ⚠ 未找到 config/sources.json")
        return
    rsshub_base = os.environ.get("RSSHUB_BASE") or cfg.get("rsshub_base") or "http://127.0.0.1:1200"
    fallback_base = "https://rsshub.app" if "127.0.0.1" in rsshub_base or "localhost" in rsshub_base else None
    compact = date_str_to_compact(date_str)

    raw_rss = RAW_DIR / "rss"
    raw_exp = RAW_DIR / "experimental"
    raw_rss.mkdir(parents=True, exist_ok=True)
    raw_exp.mkdir(parents=True, exist_ok=True)

    all_entries = []

    for src in cfg.get("active", []):
        name = src.get("name", "unknown")
        path = src.get("path", "")
        url = src.get("url", "").strip() or ( _full_url(rsshub_base, path) if path else "" )
        if not url:
            continue
        print(f"  [active] {name} ...")
        fallback_url = _full_url(fallback_base, path) if fallback_base and path and "127.0.0.1" in url else None
        items = fetch_feed(name, url, date_str, skip_date_filter=src.get("skip_date_filter", False), fallback_url=fallback_url)
        for it in items:
            it["category"] = src.get("category", "未分类")
            it["source_id"] = src.get("id", "")
        all_entries.extend(items)
        time.sleep(0.5)

    # 写入 raw/rss/YYYYMMDD.json（active 汇总）
    out_path = raw_rss / f"{compact}.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        import json
        json.dump({"date": date_str, "entries": all_entries}, f, ensure_ascii=False, indent=2)
    print(f"  ✅ raw/rss/{compact}.json: {len(all_entries)} 条")

    exp_entries = []
    for src in cfg.get("experimental", []):
        name = src.get("name", "unknown")
        path = src.get("path", "")
        url = src.get("url", "").strip() or ( _full_url(rsshub_base, path) if path else "" )
        if not url:
            continue
        print(f"  [experimental] {name} ...")
        fallback_url = _full_url(fallback_base, path) if fallback_base and path and "127.0.0.1" in url else None
        items = fetch_feed(name, url, date_str, max_items=30, skip_date_filter=src.get("skip_date_filter", False), fallback_url=fallback_url)
        for it in items:
            it["category"] = src.get("category", "未分类")
            it["source_id"] = src.get("id", "")
        exp_entries.extend(items)
        time.sleep(0.5)

    exp_path = raw_exp / f"{compact}.json"
    with open(exp_path, "w", encoding="utf-8") as f:
        import json
        json.dump({"date": date_str, "entries": exp_entries}, f, ensure_ascii=False, indent=2)
    print(f"  ✅ raw/experimental/{compact}.json: {len(exp_entries)} 条")


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--date", required=True, help="YYYY-MM-DD")
    args = p.parse_args()
    run_fetch(args.date)
