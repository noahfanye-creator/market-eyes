#!/usr/bin/env python3
"""
拉取行情数据：四大指数 + 观察列表标的日线（含 MA5/MA20）+ 隔夜外盘 + 申万一级板块 Top3/Bottom3。
输出 raw/market/daily_YYYYMMDD.json，供盘前卡使用。
"""

import json
import os
import re
import time
from pathlib import Path

import requests

from utils import RAW_DIR, load_watchlist, date_str_to_compact

# 新浪外盘：美股、A50、原油、汇率等（隔夜用）
SINA_OVERNIGHT_CODES = {
    "int_dji": "道琼斯",
    "int_nasdaq": "纳斯达克",
    "int_sp500": "标普500",
    "hf_CL": "WTI原油",
    "hf_GC": "COMEX黄金",
    "gb_susdcny": "美元人民币",
}
# 富时 A50 期货（新浪代码可能为 hf_CHA50 或 hk_HSI 等，按实际可调）
SINA_OVERNIGHT_EXTRA = ["hf_CHA50"]
SINA_OVERNIGHT_URL = "http://hq.sinajs.cn/list={codes}"
SINA_HEADERS = {"Referer": "http://finance.sina.com.cn/", "User-Agent": "Mozilla/5.0 (compatible; MarketEyes/1.0)"}

# 四大指数 ts_code -> name
INDICES = {
    "000001.SH": "上证指数",
    "399001.SZ": "深证成指",
    "399006.SZ": "创业板指",
    "000688.SH": "科创50",
}


def _symbol_to_ts_code(symbol: str) -> str:
    """watchlist 纯数字代码转 Tushare ts_code。"""
    s = str(symbol).strip()
    if not s or len(s) < 6:
        return ""
    if s.startswith("6") or s.startswith("688"):
        return s[:6] + ".SH"
    if s.startswith("0") or s.startswith("3"):
        return s[:6] + ".SZ"
    return ""


def _fetch_indices(pro, date_str: str, logger, meta: dict) -> list:
    """拉取四大指数日线，返回 [{code, name, close, pct_chg, amount_yi}, ...]。"""
    compact = date_str_to_compact(date_str)
    end = compact
    # 最近 5 个交易日：往前推约 10 天作为 start 容错
    start = _date_minus_days(compact, 10)
    out = []
    for ts_code, name in INDICES.items():
        try:
            meta["tushare_calls"] += 1
            time.sleep(0.3)
            df = pro.index_daily(ts_code=ts_code, start_date=start, end_date=end)
            if df is None or df.empty:
                meta["errors"].append(f"index_daily {ts_code} 返回空")
                continue
            df = df.sort_values("trade_date", ascending=True)
            row = df.iloc[-1]
            amount = float(row.get("amount", 0) or 0)
            amount_yi = round(amount / 100000.0, 1)  # 千元 -> 亿元
            out.append({
                "code": ts_code,
                "name": name,
                "close": round(float(row["close"]), 2),
                "pct_chg": round(float(row.get("pct_chg", 0) or 0), 2),
                "amount_yi": amount_yi,
            })
        except Exception as e:
            msg = f"index_daily {ts_code}: {e}"
            meta["errors"].append(msg)
            if logger:
                logger.warning(msg)
    return out


def _date_minus_days(ymd: str, days: int) -> str:
    """YYYYMMDD 往前推 days 天（简单实现，不严格按交易日）。"""
    from datetime import datetime, timedelta
    d = datetime.strptime(ymd, "%Y%m%d") - timedelta(days=days)
    return d.strftime("%Y%m%d")


def _fetch_overnight_sina(meta: dict, logger=None) -> list:
    """新浪接口拉取隔夜外盘：美股、原油、汇率等。返回 [{name, close, pct_chg}, ...]。"""
    codes = list(SINA_OVERNIGHT_CODES.keys()) + list(SINA_OVERNIGHT_EXTRA)
    name_by_code = {c: SINA_OVERNIGHT_CODES.get(c, c) for c in SINA_OVERNIGHT_CODES}
    for c in SINA_OVERNIGHT_EXTRA:
        if c not in name_by_code:
            name_by_code[c] = "A50期货" if "A50" in c or "CHA50" in c else c
    try:
        url = SINA_OVERNIGHT_URL.format(codes=",".join(codes))
        resp = requests.get(url, headers=SINA_HEADERS, timeout=15)
        resp.raise_for_status()
        text = resp.text
    except Exception as e:
        meta["errors"].append(f"overnight_sina: {e}")
        if logger:
            logger.warning("新浪外盘请求失败: %s", e)
        return []
    out = []
    for line in text.strip().split("\n"):
        if "hq_str_" not in line or '"' not in line:
            continue
        m = re.search(r"hq_str_([^=]+)=\"([^\"]*)\"", line)
        if not m:
            continue
        code = m.group(1).strip()
        content = (m.group(2) or "").strip()
        if not content:
            continue
        parts = [p.strip() for p in content.split(",")]
        if len(parts) < 2:
            continue
        try:
            name = name_by_code.get(code, parts[0] or code)
            close = float(parts[1])
            pct_chg = float(parts[3]) if len(parts) > 3 else None
            if pct_chg is None and len(parts) > 2:
                try:
                    pct_chg = float(parts[2])
                except ValueError:
                    pass
            out.append({
                "name": name,
                "close": round(close, 2),
                "pct_chg": round(pct_chg, 2) if pct_chg is not None else None,
            })
        except (ValueError, IndexError):
            continue
    return out


def _fetch_sectors_tushare(pro, date_str: str, logger, meta: dict, top_n: int = 3) -> tuple:
    """申万一级行业日涨跌，返回 (sectors_top, sectors_bottom) 各 top_n 个。"""
    compact = date_str_to_compact(date_str)
    start = _date_minus_days(compact, 15)
    try:
        meta["tushare_calls"] += 1
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
            logger.warning("index_classify 申万一级失败: %s", e)
        meta["errors"].append(f"index_classify: {e}")
        return [], []
    sector_rows = []
    for ts_code in codes[:35]:
        try:
            meta["tushare_calls"] += 1
            time.sleep(0.3)
            d = pro.index_daily(ts_code=ts_code, start_date=start, end_date=compact)
            if d is None or d.empty:
                continue
            d = d.sort_values("trade_date", ascending=False)
            row = d.iloc[0]
            if str(row["trade_date"]) != compact:
                continue
            name = name_by_code.get(ts_code, ts_code)
            pct = round(float(row.get("pct_chg", 0) or 0), 2)
            sector_rows.append({"name": name, "pct_chg": pct, "code": ts_code})
        except Exception as e:
            if logger:
                logger.debug("index_daily %s: %s", ts_code, e)
            continue
    sector_rows.sort(key=lambda x: x["pct_chg"], reverse=True)
    top = [{"name": r["name"], "pct_chg": r["pct_chg"]} for r in sector_rows[:top_n]]
    bottom = [{"name": r["name"], "pct_chg": r["pct_chg"]} for r in sector_rows[-top_n:][::-1]]
    return top, bottom


def _fetch_watchlist_stocks(pro, date_str: str, logger, meta: dict) -> list:
    """拉取观察列表标的日线，计算 close/pct_chg/ma5/ma20。"""
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

    # 解析为 ts_code 并去重
    ts_codes = []
    code_to_symbol = {}
    for sym in symbols:
        ts_code = _symbol_to_ts_code(sym)
        if ts_code and ts_code not in code_to_symbol:
            ts_codes.append(ts_code)
            code_to_symbol[ts_code] = sym

    if not ts_codes:
        return []

    # 用 stock_basic 补全名称（一次调用，ts_code -> name）
    name_by_ts_code = {}
    try:
        meta["tushare_calls"] += 1
        time.sleep(0.3)
        basic_df = pro.stock_basic(exchange="", list_status="L", fields="ts_code,name")
        if basic_df is not None and not basic_df.empty:
            for _, row in basic_df.iterrows():
                tc = row.get("ts_code")
                if tc in code_to_symbol:
                    name_by_ts_code[tc] = (row.get("name") or "").strip()
    except Exception as e:
        if logger:
            logger.debug("stock_basic 跳过: %s", e)

    compact = date_str_to_compact(date_str)
    end = compact
    start = _date_minus_days(compact, 45)  # 30 日线 + 余量
    out = []

    for ts_code in ts_codes:
        sym = code_to_symbol.get(ts_code, ts_code)
        name = name_by_code.get(sym) or name_by_ts_code.get(ts_code) or sym
        try:
            meta["tushare_calls"] += 1
            time.sleep(0.3)
            df = pro.daily(ts_code=ts_code, start_date=start, end_date=end)
            if df is None or df.empty:
                if logger:
                    logger.warning("daily %s 返回空", ts_code)
                continue
            df = df.sort_values("trade_date", ascending=True)
            row = df.iloc[-1]
            close = round(float(row["close"]), 2)
            pct_chg = round(float(row.get("pct_chg", 0) or 0), 2)
            closes = df["close"].astype(float)
            ma5 = round(float(closes.tail(5).mean()), 2) if len(closes) >= 5 else None
            ma20 = round(float(closes.tail(20).mean()), 2) if len(closes) >= 20 else None
            out.append({
                "code": sym,
                "name": name or sym,
                "close": close,
                "pct_chg": pct_chg,
                "ma5": ma5,
                "ma20": ma20,
            })
        except Exception as e:
            if logger:
                logger.warning("daily %s: %s", ts_code, e)
            meta["errors"].append(f"daily {ts_code}: {e}")

    return out


def fetch_market_data(date_str: str, logger=None):
    """
    总调度：拉取指数 + 观察列表标的，写入 raw/market/daily_YYYYMMDD.json。
    返回 True 成功，False 表示未配置 token 或失败。
    """
    token = os.environ.get("TUSHARE_TOKEN", "").strip()
    if not token:
        if logger:
            logger.error("未配置 TUSHARE_TOKEN，请设置环境变量")
        return False

    try:
        import tushare as ts
        ts.set_token(token)
        pro = ts.pro_api()
    except Exception as e:
        if logger:
            logger.error("Tushare 初始化失败: %s", e)
        return False

    compact = date_str_to_compact(date_str)
    from datetime import datetime, timezone
    fetch_time = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

    result = {
        "date": date_str,
        "indices": [],
        "stocks": [],
        "sectors_top": [],
        "sectors_bottom": [],
        "overnight": [],
        "money_flow": {},
        "meta": {
            "fetch_time": fetch_time,
            "tushare_calls": 0,
            "errors": [],
        },
    }

    result["indices"] = _fetch_indices(pro, date_str, logger, result["meta"])
    result["stocks"] = _fetch_watchlist_stocks(pro, date_str, logger, result["meta"])
    result["sectors_top"], result["sectors_bottom"] = _fetch_sectors_tushare(
        pro, date_str, logger, result["meta"], top_n=3
    )
    result["overnight"] = _fetch_overnight_sina(result["meta"], logger)

    out_dir = RAW_DIR / "market"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"daily_{compact}.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    if logger:
        logger.info("fetch_market 完成: indices=%s stocks=%s -> %s",
                    len(result["indices"]), len(result["stocks"]), out_path.name)
    return True


if __name__ == "__main__":
    import argparse
    from pathlib import Path
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
    ok = fetch_market_data(args.date, log)
    raise SystemExit(0 if ok else 1)
