#!/usr/bin/env python3
"""
fetch_postmarket_data.py
盘后数据抓取 → 生成 postmarket_data.json
包含：指数、板块，技术指标、个股、筹码峰、斐波那契
用法：python3 fetch_postmarket_data.py --date 2026-03-13
"""

import os
import json
import argparse
import math
from datetime import datetime, timedelta
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).parent.parent
load_dotenv(BASE_DIR / ".env")

OUTPUT_DIR = BASE_DIR / "output" / "postmarket_data"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

TUSHARE_TOKEN = os.getenv("TUSHARE_TOKEN", "")

HOLDINGS = [
    {"code": "300777.SZ", "name": "中简科技"},
    {"code": "601702.SH", "name": "华峰铝业"},
    {"code": "588000.SH", "name": "科创50ETF"},
    {"code": "300474.SZ", "name": "景嘉微"},
    {"code": "600460.SH", "name": "士兰微"},
    {"code": "300623.SZ", "name": "捷捷微电"},
]

WATCHLIST = [
    {"code": "688630.SH", "name": "芯碁微装"},
    {"code": "002173.SZ", "name": "创新医疗"},
    {"code": "300442.SZ", "name": "润泽科技"},
    {"code": "300842.SZ", "name": "帝科股份"},
    {"code": "300672.SZ", "name": "国科微"},
    {"code": "600602.SH", "name": "云赛智联"},
]

INDEX_LIST = [
    {"code": "000001.SH", "name": "上证指数"},
    {"code": "399001.SZ", "name": "深证成指"},
    {"code": "399006.SZ", "name": "创业板指"},
    {"code": "000300.SH", "name": "沪深300"},
    {"code": "000688.SH", "name": "科创50"},
]

# ── 技术指标计算 ──────────────────────────────────────────

def calc_ma(closes, period):
    if len(closes) < period:
        return None
    return round(sum(closes[-period:]) / period, 3)

def calc_macd(closes, fast=12, slow=26, signal=9):
    if len(closes) < slow + signal:
        return None, None, None
    def ema(data, period):
        k = 2 / (period + 1)
        ema_val = data[0]
        for price in data[1:]:
            ema_val = price * k + ema_val * (1 - k)
        return ema_val
    ema_fast = ema(closes, fast)
    ema_slow = ema(closes, slow)
    dif = round(ema_fast - ema_slow, 4)
    # 简化signal计算
    difs = []
    for i in range(signal + 1):
        ef = ema(closes[:-(signal - i) or None], fast)
        es = ema(closes[:-(signal - i) or None], slow)
        difs.append(ef - es)
    dea = round(sum(difs) / len(difs), 4)
    macd_bar = round((dif - dea) * 2, 4)
    return dif, dea, macd_bar

def calc_rsi(closes, period=14):
    if len(closes) < period + 1:
        return None
    deltas = [closes[i] - closes[i-1] for i in range(1, len(closes))]
    gains = [d if d > 0 else 0 for d in deltas[-period:]]
    losses = [-d if d < 0 else 0 for d in deltas[-period:]]
    avg_gain = sum(gains) / period
    avg_loss = sum(losses) / period
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return round(100 - (100 / (1 + rs)), 2)

def calc_bollinger(closes, period=20, std_dev=2):
    if len(closes) < period:
        return None, None, None
    recent = closes[-period:]
    mid = sum(recent) / period
    variance = sum((x - mid) ** 2 for x in recent) / period
    std = math.sqrt(variance)
    upper = round(mid + std_dev * std, 3)
    lower = round(mid - std_dev * std, 3)
    return round(upper, 3), round(mid, 3), round(lower, 3)

def calc_fibonacci(high, low):
    diff = high - low
    return {
        "high": round(high, 3),
        "low": round(low, 3),
        "0.236": round(high - diff * 0.236, 3),
        "0.382": round(high - diff * 0.382, 3),
        "0.500": round(high - diff * 0.500, 3),
        "0.618": round(high - diff * 0.618, 3),
        "0.786": round(high - diff * 0.786, 3),
    }

def calc_chip_peak(df_history):
    """
    简化筹码峰：用近20日成交量加权平均价格区间
    返回主要筹码集中区域（成本区间）
    """
    if df_history is None or len(df_history) < 5:
        return None
    try:
        recent = df_history.tail(20)
        total_vol = recent["vol"].sum()
        if total_vol == 0:
            return None
        vwap = (recent["close"] * recent["vol"]).sum() / total_vol
        # 成交量加权标准差
        variance = ((recent["close"] - vwap) ** 2 * recent["vol"]).sum() / total_vol
        std = math.sqrt(variance)
        return {
            "vwap_20": round(vwap, 3),
            "chip_low": round(vwap - std, 3),
            "chip_high": round(vwap + std, 3),
            "description": f"近20日主要筹码集中区：{round(vwap - std, 2)}-{round(vwap + std, 2)}"
        }
    except:
        return None

def calc_volume_ratio(df_history):
    """量比：今日成交量 / 过去5日平均成交量"""
    if df_history is None or len(df_history) < 6:
        return None
    try:
        avg_5 = df_history["vol"].iloc[-6:-1].mean()
        today_vol = df_history["vol"].iloc[-1]
        if avg_5 == 0:
            return None
        return round(today_vol / avg_5, 2)
    except:
        return None

def judge_trend(closes, ma5, ma10, ma20, ma60, macd_bar, rsi):
    """根据技术指标综合判断趋势"""
    signals = []
    close = closes[-1]
    # 均线判断
    if ma5 and ma20:
        if close > ma20:
            signals.append("价格在MA20上方")
        else:
            signals.append("价格跌破MA20⚠️")

    if ma5 and ma10 and ma20:
        if ma5 > ma10 > ma20:
            signals.append("均线多头排列")
        elif ma5 < ma10 < ma20:
            signals.append("均线空头排列⚠️")
        else:
            signals.append("均线纠缠震荡")

    # MACD判断
    if macd_bar is not None:
        if macd_bar > 0:
            signals.append("MACD红柱（多头动能）")
        else:
            signals.append("MACD绿柱（空头动能）⚠️")

    # RSI判断
    if rsi is not None:
        if rsi > 70:
            signals.append(f"RSI={rsi}超买区间")
        elif rsi < 30:
            signals.append(f"RSI={rsi}超卖区间（可能反弹）")
        else:
            signals.append(f"RSI={rsi}正常区间")

    # 趋势定性
    bullish = sum(1 for s in signals if "⚠️" not in s and "空头" not in s and "绿柱" not in s)
    bearish = sum(1 for s in signals if "⚠️" in s or "空头" in s or "绿柱" in s)

    if bullish > bearish:
        trend = "偏多"
    elif bearish > bullish:
        trend = "偏空"
    else:
        trend = "震荡"

    return trend, signals

# ── Tushare数据获取 ───────────────────────────────────────

def get_history(pro, ts_code, date_str, n=65):
    """获取近n个交易日历史数据"""
    try:
        end = date_str.replace("-", "")
        index_codes = ["000001.SH","399001.SZ","399006.SZ","000300.SH","000688.SH"]
        etf_codes = ["588000.SH","510050.SH","510300.SH","159915.SZ","159919.SZ"]
        if ts_code in index_codes:
            df = pro.index_daily(ts_code=ts_code, end_date=end)
        elif ts_code in etf_codes:
            df = pro.fund_daily(ts_code=ts_code, end_date=end)
        else:
            df = pro.daily(ts_code=ts_code, end_date=end)
        df = df.sort_values("trade_date").reset_index(drop=True)
        return df.tail(n)
    except Exception as e:
        print(f"    {ts_code} 失败: {e}")
        return None

def analyze_code(pro, code, name, date_str):
    """分析单只股票/指数的技术指标"""
    result = {"code": code, "name": name}
    try:
        df = get_history(pro, code, date_str)
        if df is None or df.empty:
            result["error"] = "无数据"
            return result
        
        closes = df["close"].tolist()
        volumes = df["vol"].tolist()
        today = df.iloc[-1]

        # 基础数据
        result["close"] = round(float(today["close"]), 3)
        result["pct_chg"] = round(float(today["pct_chg"]), 2)
        result["vol"] = round(float(today["vol"]), 0)
        result["amount"] = round(float(today["amount"]) / 1e5, 2)  # 亿元

        # 均线
        result["ma5"] = calc_ma(closes, 5)
        result["ma10"] = calc_ma(closes, 10)
        result["ma20"] = calc_ma(closes, 20)
        result["ma60"] = calc_ma(closes, 60)

        # MACD
        dif, dea, macd_bar = calc_macd(closes)
        result["macd"] = {"dif": dif, "dea": dea, "bar": macd_bar}

        # RSI
        result["rsi14"] = calc_rsi(closes)

        # 布林带
        upper, mid, lower = calc_bollinger(closes)
        result["bollinger"] = {"upper": upper, "mid": mid, "lower": lower}

        # 斐波那契（取近60日高低点）
        recent_60 = df.tail(60)
        high_60 = float(recent_60["high"].max())
        low_60 = float(recent_60["low"].min())
        result["fibonacci"] = calc_fibonacci(high_60, low_60)

        # 筹码峰（个股用，指数跳过）
        result["chip_peak"] = calc_chip_peak(df)

        # 量比
        result["volume_ratio"] = calc_volume_ratio(df)

        # 趋势判断
        trend, signals = judge_trend(
            closes,
            result["ma5"], result["ma10"], result["ma20"], result["ma60"],
            macd_bar, result["rsi14"]
        )
        result["trend"] = trend
        result["trend_signals"] = signals

        # 破位判断
        result["below_ma20"] = closes[-1] < result["ma20"] if result["ma20"] else None
        result["below_ma60"] = closes[-1] < result["ma60"] if result["ma60"] else None

    except Exception as e:
        result["error"] = str(e)

    return result

def get_sector_data(pro, date_str):
    result = {"top5": [], "bottom5": []}
    try:
        d = date_str.replace("-", "")
        df = pro.moneyflow_ind_dc(trade_date=d, content_type="行业")
        df["pct_change"] = df["pct_change"].astype(float)
        df["net_amount"] = df["net_amount"].astype(float)
        df_sorted = df.sort_values("pct_change", ascending=False)
        for item in df_sorted.head(5).to_dict("records"):
            result["top5"].append({
                "name": item.get("name", ""),
                "pct_chg": round(float(item.get("pct_change", 0)), 2),
                "net_amount": round(float(item.get("net_amount", 0)) / 1e8, 2),
            })
        for item in df_sorted.tail(5).to_dict("records"):
            result["bottom5"].append({
                "name": item.get("name", ""),
                "pct_chg": round(float(item.get("pct_change", 0)), 2),
                "net_amount": round(float(item.get("net_amount", 0)) / 1e8, 2),
            })
    except Exception as e:
        print(f"  板块数据失败: {e}")
    return result

def get_moneyflow(pro, date_str):
    """北向资金、主力资金"""
    result = {}
    try:
        d = date_str.replace("-", "")
        mf = pro.moneyflow_hsgt(trade_date=d)
        if not mf.empty:
            row = mf.iloc[0]
            result["north_net"] = round(float(row.get("north_money", 0)) / 1e8, 2)
            result["sh_connect"] = round(float(row.get("sh_money", 0)) / 1e8, 2)
            result["sz_connect"] = round(float(row.get("sz_money", 0)) / 1e8, 2)
    except Exception as e:
        print(f"⚠ 北向资金失败: {e}")
    return result

def get_limit_stats(pro, date_str):
    """涨跌停统计"""
    result = {}
    try:
        d = date_str.replace("-", "")
        zt = pro.limit_list_d(trade_date=d, limit_type="U")
        dt = pro.limit_list_d(trade_date=d, limit_type="D")
        result["zt_count"] = len(zt) if not zt.empty else 0
        result["dt_count"] = len(dt) if not dt.empty else 0
    except Exception as e:
        print(f"⚠ 涨跌停失败: {e}")
    return result

# ── 格式化输出 ────────────────────────────────────────────

def format_tech(item):
    """格式化单只股票技术指标为可读文字"""
    if "error" in item:
        return f"数据获取失败: {item['error']}"
    lines = []
    lines.append(f"收盘：{item.get('close')} ({'+' if item.get('pct_chg',0)>0 else ''}{item.get('pct_chg')}%)")

    ma = f"MA5={item.get('ma5')} MA10={item.get('ma10')} MA20={item.get('ma20')} MA60={item.get('ma60')}"
    lines.append(f"均线：{ma}")

    if item.get("macd"):
        m = item["macd"]
        lines.append(f"MACD：DIF={m.get('dif')} DEA={m.get('dea')} 柱={m.get('bar')}")

    lines.append(f"RSI14：{item.get('rsi14')}")

    if item.get("bollinger"):
        b = item["bollinger"]
        lines.append(f"布林带：上={b.get('upper')} 中={b.get('mid')} 下={b.get('lower')}")

    if item.get("volume_ratio"):
        lines.append(f"量比：{item.get('volume_ratio')}")

    if item.get("chip_peak"):
        lines.append(f"筹码峰：{item['chip_peak'].get('description')}")

    if item.get("fibonacci"):
        fib = item["fibonacci"]
        lines.append(f"斐波那契（近60日）：高={fib.get('high')} 低={fib.get('low')} "
                      f"0.382={fib.get('0.382')} 0.5={fib.get('0.500')} 0.618={fib.get('0.618')}")

    lines.append(f"趋势判断：{item.get('trend')} | {' / '.join(item.get('trend_signals', []))}")

    breakdown = []
    if item.get("below_ma20"):
        breakdown.append("跌破MA20⚠️")
    if item.get("below_ma60"):
        breakdown.append("跌破MA60⚠️")
    if breakdown:
        lines.append(f"破位警示：{'、'.join(breakdown)}")

    return "\n".join(lines)

def format_for_prompt(data):
    """格式化为LLM可用的文字"""
    lines = []
    # 指数
    lines.append("## 今日指数收盘与技术指标")
    for idx in data.get("indices", []):
        lines.append(f"\n### {idx['name']}（{idx['code']}）")
        lines.append(format_tech(idx))

    # 板块
    lines.append("\n## 板块涨跌")
    sectors = data.get("sectors", {})
    if sectors.get("top5"):
        lines.append("**今日最强板块TOP5：**")
        for i, s in enumerate(sectors["top5"], 1):
            lines.append(f"{i}. {s['name']} {'+' if s['pct_chg']>0 else ''}{s['pct_chg']}%")
    if sectors.get("bottom5"):
        lines.append("**今日最弱板块TOP5：**")
        for i, s in enumerate(sectors["bottom5"], 1):
            lines.append(f"{i}. {s['name']} {s['pct_chg']}%")

    # 资金
    lines.append("\n## 资金面")
    mf = data.get("moneyflow", {})
    if mf:
        lines.append(f"北向资金净流入：{mf.get('north_net', '暂无')}亿元")
        lines.append(f"沪股通：{mf.get('sh_connect', '暂无')}亿元")
        lines.append(f"深股通：{mf.get('sz_connect', '暂无')}亿元")

    ls = data.get("limit_stats", {})
    if ls:
        lines.append(f"涨停：{ls.get('zt_count', 0)}家 / 跌停：{ls.get('dt_count', 0)}家")

    # 持仓
    lines.append("\n## 持仓个股技术分析")
    for stock in data.get("holdings", []):
        lines.append(f"\n### {stock['name']}（{stock['code']}）")
        lines.append(format_tech(stock))

    # 观察池
    lines.append("\n## 观察池个股技术分析")
    for stock in data.get("watchlist", []):
        lines.append(f"\n### {stock['name']}（{stock['code']}）")
        lines.append(format_tech(stock))

    return "\n".join(lines)

# ── 主函数 ────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", default=datetime.now().strftime("%Y-%m-%d"))
    args = parser.parse_args()
    date_str = args.date
    print(f"📡 开始抓取盘后数据 date={date_str}")

    import tushare as ts
    ts.set_token(TUSHARE_TOKEN)
    pro = ts.pro_api()

    data = {
        "date": date_str,
        "fetch_time": datetime.now().isoformat(),
        "indices": [],
        "sectors": {},
        "moneyflow": {},
        "limit_stats": {},
        "holdings": [],
        "watchlist": [],
    }

    # 指数技术分析
    print("📊 指数技术分析...")
    for idx in INDEX_LIST:
        print(f" → {idx['name']}")
        result = analyze_code(pro, idx["code"], idx["name"], date_str)
        data["indices"].append(result)

    # 板块
    data["sectors"] = get_sector_data(pro, date_str)

    # 资金
    print("📊 资金面数据...")
    data["moneyflow"] = get_moneyflow(pro, date_str)
    data["limit_stats"] = get_limit_stats(pro, date_str)

    # 持仓个股
    print("📊 持仓个股分析...")
    for stock in HOLDINGS:
        print(f" → {stock['name']}")
        result = analyze_code(pro, stock["code"], stock["name"], date_str)
        data["holdings"].append(result)

    # 观察池
    print("📊 观察池个股分析...")
    for stock in WATCHLIST:
        print(f" → {stock['name']}")
        result = analyze_code(pro, stock["code"], stock["name"], date_str)
        data["watchlist"].append(result)

    # 格式化
    data["formatted_text"] = format_for_prompt(data)

    # 保存
    out_path = OUTPUT_DIR / f"{date_str}_postmarket_data.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print(f"\n✅ 已保存: {out_path}")
    print(f" 数据条目：指数{len(data['indices'])}个 / 持仓{len(data['holdings'])}只 / 观察池{len(data['watchlist'])}只")

    return str(out_path)

if __name__ == "__main__":
    main()
