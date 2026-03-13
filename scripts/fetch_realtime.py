#!/usr/bin/env python3
"""
抓取 10:00 左右盘中数据，输出 raw/market/realtime_YYYYMMDD.json。
V0.2：指数与 watchlist 优先用新浪实时接口（盘中真实数据），失败时回退 Tushare 日线。
"""
from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path

import requests

from utils import CONFIG_DIR, RAW_DIR, date_str_to_compact, load_watchlist

INDICES = {
    "s_sh000001": "上证指数",
    "s_sz399001": "深证成指",
    "s_sz399006": "创业板指",
    "s_sh000688": "科创50",
}

SINA_URL = "http://hq.sinajs.cn/list={codes}"
SINA_HEADERS = {"Referer": "http://finance.sina.com.cn/", "User-Agent": "Mozilla/5.0 (compatible; MarketEyes/1.0)"}
TIMEOUT = 15


def _load_intraday_config():
    p = CONFIG_DIR / "intraday.json"
    if not p.exists():
        return {"indices": list(INDICES.keys()), "top_sectors": 3, "report_time": "10:00"}
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def _symbol_to_sina_code(symbol: str) -> str:
    """600519 -> s_sh600519, 000001 -> s_sz000001"""
    s = str(symbol).strip()
    if not s or len(s) < 6:
        return ""
    code = s[:6]
    if s.startswith("6") or s.startswith("688"):
        return f"s_sh{code}"
    if s.startswith("0") or s.startswith("3"):
        return f"s_sz{code}"
    return ""


def _symbol_to_ts_code(symbol: str) -> str:
    s = str(symbol).strip()
    if not s or len(s) < 6:
        return ""
    if s.startswith("6") or s.startswith("688"):
        return s[:6] + ".SH"
    if s.startswith("0") or s.startswith("3"):
        return s[:6] + ".SZ"
    return ""


def _date_minus_days(ymd: str, days: int) -> str:
    from datetime import datetime, timedelta
    d = datetime.strptime(ymd, "%Y%m%d") - timedelta(days=days)
    return d.strftime("%Y%m%d")


def _fetch_sectors_tushare_realtime(pro, date_str: str, meta: dict, logger=None, top_n: int = 3) -> tuple:
    """盘中申万一级涨跌 Top/Bottom（Tushare 当日若已更新则用当日，否则可能为空）。"""
    compact = date_str_to_compact(date_str)
    start = _date_minus_days(compact, 5)
    try:
        meta["tushare_calls"] = meta.get("tushare_calls", 0) + 1
        time.sleep(0.35)
        df = pro.index_classify(level="L1", src="SW2021")
        if df is None or df.empty:
            return [], []
        code_col = "index_code" if "index_code" in df.columns else df.columns[0]
        codes = df[code_col].dropna().astype(str).unique().tolist()
        name_col = "name" if "name" in df.columns else ("c_name" if "c_name" in df.columns else None)
        name_by_code = dict(zip(df[code_col].astype(str), df[name_col] if name_col else df[code_col], strict=False))
    except Exception as e:
        if logger:
            logger.debug("realtime index_classify: %s", e)
        return [], []
    sector_rows = []
    for ts_code in codes[:35]:
        try:
            meta["tushare_calls"] = meta.get("tushare_calls", 0) + 1
            time.sleep(0.3)
            d = pro.index_daily(ts_code=ts_code, start_date=start, end_date=compact)
            if d is None or d.empty:
                continue
            d = d.sort_values("trade_date", ascending=False)
            row = d.iloc[0]
            name = name_by_code.get(ts_code, ts_code)
            pct = round(float(row.get("pct_chg", 0) or 0), 2)
            sector_rows.append({"name": name, "pct_chg": pct})
        except Exception:
            continue
    sector_rows.sort(key=lambda x: x["pct_chg"], reverse=True)
    top = [{"name": r["name"], "pct_chg": r["pct_chg"]} for r in sector_rows[:top_n]]
    bottom = [{"name": r["name"], "pct_chg": r["pct_chg"]} for r in sector_rows[-top_n:][::-1]]
    return top, bottom


def _index_status(pct_chg: float) -> str:
    if pct_chg >= 0.5:
        return "偏强"
    if pct_chg <= -0.5:
        return "偏弱"
    return "震荡"


def _parse_sina_quote(line: str) -> dict | None:
    """解析新浪返回的一行。指数多为 6 字段：名称,当前,?,涨跌幅,量,额；无开盘/昨收时用 close 与 pct_chg 反推 prev_close。"""
    m = re.search(r'"([^"]+)"', line)
    if not m:
        return None
    parts = m.group(1).strip().split(",")
    if len(parts) < 4:
        return None
    try:
        name = parts[0].strip()
        close = float(parts[1])
        pct_chg = float(parts[3])
        out = {"name": name, "close": round(close, 2), "pct_chg": round(pct_chg, 2)}
        # 反推昨收：prev_close = close / (1 + pct_chg/100)
        if pct_chg != -100:
            prev_close = close / (1 + pct_chg / 100.0)
            out["prev_close"] = round(prev_close, 2)
        else:
            out["prev_close"] = None
        return out
    except (ValueError, IndexError):
        return None


def _fetch_indices_sina(meta: dict, logger=None) -> list:
    """新浪实时接口抓取四大指数。"""
    codes = ",".join(INDICES.keys())
    try:
        resp = requests.get(SINA_URL.format(codes=codes), headers=SINA_HEADERS, timeout=TIMEOUT)
        resp.raise_for_status()
        text = resp.text
    except Exception as e:
        meta["errors"].append(f"sina_indices: {e}")
        if logger:
            logger.warning("新浪指数请求失败: %s", e)
        return []

    out = []
    for line in text.strip().split("\n"):
        if "hq_str_" not in line:
            continue
        row = _parse_sina_quote(line)
        if not row:
            continue
        name = row["name"]
        if name in INDICES.values():
            item = {
                "name": name,
                "close": row["close"],
                "pct_chg": row["pct_chg"],
                "status": _index_status(row["pct_chg"]),
            }
            if row.get("prev_close") is not None:
                item["prev_close"] = row["prev_close"]
            if row.get("open") is not None:
                item["open"] = row["open"]
            out.append(item)
    meta["sina_calls"] = meta.get("sina_calls", 0) + 1
    return out


def _fetch_watchlist_sina(meta: dict, logger=None) -> list:
    """新浪实时接口抓取 watchlist 个股。"""
    watchlist = load_watchlist()
    symbols_raw = watchlist.get("symbols") or []
    codes = []
    name_by_code = {}
    for s in symbols_raw:
        if isinstance(s, dict):
            sym = (s.get("symbol") or s.get("code") or "").strip()
            if sym:
                sc = _symbol_to_sina_code(sym)
                if sc and sc not in codes:
                    codes.append(sc)
                    name_by_code[sc] = s.get("name", sym)
        elif isinstance(s, str) and s.strip():
            sc = _symbol_to_sina_code(s.strip())
            if sc and sc not in codes:
                codes.append(sc)
                name_by_code[sc] = s.strip()
    if not codes:
        return []

    try:
        url = SINA_URL.format(codes=",".join(codes))
        resp = requests.get(url, headers=SINA_HEADERS, timeout=TIMEOUT)
        resp.raise_for_status()
        text = resp.text
    except Exception as e:
        meta["errors"].append(f"sina_watchlist: {e}")
        if logger:
            logger.warning("新浪个股请求失败: %s", e)
        return []

    out = []
    for line in text.strip().split("\n"):
        if "hq_str_" not in line:
            continue
        m = re.search(r"hq_str_(s_\w+)=(.+)", line)
        if not m:
            continue
        sina_code = m.group(1)
        row = _parse_sina_quote(line)
        if not row:
            continue
        name = name_by_code.get(sina_code) or row["name"]
        out.append({
            "name": name,
            "pct_chg": row["pct_chg"],
            "status_summary": _index_status(row["pct_chg"]),
        })
    meta["sina_calls"] = meta.get("sina_calls", 0) + 1
    return out


def _fetch_indices_tushare(pro, date_str: str, meta: dict, logger=None) -> list:
    """Tushare 日线（回退用，盘中为昨日数据）。"""
    ts_map = {"000001.SH": "上证指数", "399001.SZ": "深证成指", "399006.SZ": "创业板指", "000688.SH": "科创50"}
    compact = date_str_to_compact(date_str)
    start = _date_minus_days(compact, 10)
    out = []
    for ts_code, name in ts_map.items():
        try:
            meta["tushare_calls"] = meta.get("tushare_calls", 0) + 1
            time.sleep(0.3)
            df = pro.index_daily(ts_code=ts_code, start_date=start, end_date=compact)
            if df is None or df.empty:
                meta["errors"].append(f"index_daily {ts_code} 返回空")
                continue
            df = df.sort_values("trade_date", ascending=True)
            row = df.iloc[-1]
            pct = round(float(row.get("pct_chg", 0) or 0), 2)
            out.append({"name": name, "close": round(float(row["close"]), 2), "pct_chg": pct, "status": _index_status(pct)})
        except Exception as e:
            meta["errors"].append(f"index_daily {ts_code}: {e}")
            if logger:
                logger.warning("index_daily %s: %s", ts_code, e)
    return out


def _fetch_watchlist_tushare(pro, date_str: str, meta: dict, logger=None) -> list:
    """Tushare 日线（回退用）。"""
    watchlist = load_watchlist()
    symbols_raw = watchlist.get("symbols") or []
    symbols = []
    name_by_code = {}
    for s in symbols_raw:
        if isinstance(s, dict):
            sym = (s.get("symbol") or s.get("code") or "").strip()
            if sym:
                symbols.append(sym)
                if s.get("name"):
                    name_by_code[sym] = s["name"]
        elif isinstance(s, str) and s.strip():
            symbols.append(s.strip())
    if not symbols:
        return []

    ts_codes = []
    code_to_symbol = {}
    for sym in symbols:
        tc = _symbol_to_ts_code(sym)
        if tc and tc not in code_to_symbol:
            ts_codes.append(tc)
            code_to_symbol[tc] = sym
    if not ts_codes:
        return []

    name_by_ts_code = {}
    try:
        meta["tushare_calls"] = meta.get("tushare_calls", 0) + 1
        time.sleep(0.3)
        basic_df = pro.stock_basic(exchange="", list_status="L", fields="ts_code,name")
        if basic_df is not None and not basic_df.empty:
            for _, row in basic_df.iterrows():
                if row.get("ts_code") in code_to_symbol:
                    name_by_ts_code[row["ts_code"]] = (row.get("name") or "").strip()
    except Exception as e:
        if logger:
            logger.debug("stock_basic 跳过: %s", e)

    compact = date_str_to_compact(date_str)
    start = _date_minus_days(compact, 45)
    out = []
    for ts_code in ts_codes:
        sym = code_to_symbol.get(ts_code, ts_code)
        name = name_by_code.get(sym) or name_by_ts_code.get(ts_code) or sym
        try:
            meta["tushare_calls"] = meta.get("tushare_calls", 0) + 1
            time.sleep(0.3)
            df = pro.daily(ts_code=ts_code, start_date=start, end_date=compact)
            if df is None or df.empty:
                continue
            df = df.sort_values("trade_date", ascending=True)
            row = df.iloc[-1]
            pct = round(float(row.get("pct_chg", 0) or 0), 2)
            out.append({"name": name or sym, "pct_chg": pct, "status_summary": _index_status(pct)})
        except Exception as e:
            meta["errors"].append(f"daily {ts_code}: {e}")
            if logger:
                logger.warning("daily %s: %s", ts_code, e)
    return out


def fetch_realtime_data(date_str: str, logger=None) -> bool:
    """
    拉取盘中数据，写入 raw/market/realtime_YYYYMMDD.json。
    优先新浪实时（盘中真实数据），失败时回退 Tushare 日线。
    """
    from datetime import datetime, timezone
    compact = date_str_to_compact(date_str)
    fetch_time = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    meta = {"fetch_time": fetch_time, "tushare_calls": 0, "sina_calls": 0, "errors": [], "data_source": "sina"}

    # 1. 优先新浪实时
    indices = _fetch_indices_sina(meta, logger)
    watchlist = _fetch_watchlist_sina(meta, logger)

    pro = None
    if len(indices) < 4:
        token = os.environ.get("TUSHARE_TOKEN", "").strip()
        if token:
            try:
                import tushare as ts
                ts.set_token(token)
                pro = ts.pro_api()
                indices = _fetch_indices_tushare(pro, date_str, meta, logger)
                if not watchlist:
                    watchlist = _fetch_watchlist_tushare(pro, date_str, meta, logger)
                meta["data_source"] = "tushare"
                if logger:
                    logger.info("新浪指数不足，已回退 Tushare 日线")
            except Exception as e:
                meta["errors"].append(f"tushare_fallback: {e}")
                if logger:
                    logger.warning("Tushare 回退失败: %s", e)
        else:
            if logger:
                logger.warning("新浪指数 %d 条不足 4，且未配置 TUSHARE_TOKEN", len(indices))

    sectors_top = []
    sectors_bottom = []
    token = os.environ.get("TUSHARE_TOKEN", "").strip()
    if token and (pro is not None or len(indices) >= 4):
        try:
            if pro is None:
                import tushare as ts
                ts.set_token(token)
                pro = ts.pro_api()
            sectors_top, sectors_bottom = _fetch_sectors_tushare_realtime(pro, date_str, meta, logger, top_n=3)
        except Exception as e:
            if logger:
                logger.debug("盘中板块 Tushare: %s", e)
    money_flow = {}

    result = {
        "date": date_str,
        "indices": indices,
        "sectors_top": sectors_top,
        "sectors_bottom": sectors_bottom,
        "money_flow": money_flow,
        "watchlist": watchlist,
        "meta": meta,
    }

    out_dir = RAW_DIR / "market"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"realtime_{compact}.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    if logger:
        logger.info("fetch_realtime 完成 -> %s", out_path.name)
    print(f"  ✅ raw/market/realtime_{compact}.json")
    src = meta.get("data_source", "sina")
    n_idx = len(indices)
    n_wl = len(watchlist)
    print(f"  ✅ 盘中数据已抓取 ({src}): 指数 {n_idx} 个, 观察池 {n_wl} 个")
    return True


if __name__ == "__main__":
    import argparse
    try:
        from dotenv import load_dotenv
        load_dotenv(Path(__file__).resolve().parent.parent / ".env")
    except ImportError:
        pass
    from utils import setup_logging
    p = argparse.ArgumentParser()
    p.add_argument("--date", required=True, help="YYYY-MM-DD")
    args = p.parse_args()
    log = setup_logging(args.date)
    ok = fetch_realtime_data(args.date, log)
    raise SystemExit(0 if ok else 1)
