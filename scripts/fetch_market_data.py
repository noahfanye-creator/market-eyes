#!/usr/bin/env python3
import os, json, argparse
from datetime import datetime, timedelta
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).parent.parent
load_dotenv(BASE_DIR / ".env")

DATA_DIR = Path("/home/node/market-eyes/output/market_data")
DATA_DIR.mkdir(parents=True, exist_ok=True)

TUSHARE_TOKEN = os.getenv("TUSHARE_TOKEN", "")

def safe(fn, default="暂无数据"):
    try:
        result = fn()
        return default if result is None else result
    except Exception as e:
        print(f"  ⚠ 数据获取失败: {e}")
        return default

def get_tushare_data(trade_date: str) -> dict:
    result = {}
    if not TUSHARE_TOKEN:
        print("  ⚠ TUSHARE_TOKEN 未配置")
        return result
    try:
        import tushare as ts
        ts.set_token(TUSHARE_TOKEN)
        pro = ts.pro_api()
        print("  📊 Tushare: 获取A股指数...")
        d = trade_date.replace("-", "")
        index_map = {
            "000001.SH": "上证指数",
            "399001.SZ": "深证成指",
            "399006.SZ": "创业板指",
            "000300.SH": "沪深300",
            "000688.SH": "科创50",
        }
        a_shares = {}
        for code, name in index_map.items():
            try:
                df = pro.index_daily(ts_code=code, start_date=d, end_date=d)
                if not df.empty:
                    row = df.iloc[0]
                    a_shares[name] = {
                        "close": round(float(row["close"]), 2),
                        "pct_chg": round(float(row["pct_chg"]), 2),
                        "amount": round(float(row["amount"]) / 1e5, 2) if "amount" in row.index else "暂无数据",
                    }
            except Exception as e:
                a_shares[name] = {"error": str(e)}
        result["a_shares"] = a_shares
        try:
            sh = pro.index_daily(ts_code="000001.SH", start_date=d, end_date=d)
            sz = pro.index_daily(ts_code="399001.SZ", start_date=d, end_date=d)
            if not sh.empty and not sz.empty:
                total = round((float(sh.iloc[0]["amount"]) + float(sz.iloc[0]["amount"])) / 1e5, 0)
                result["total_amount"] = f"{total:.0f}亿元"
        except:
            result["total_amount"] = "暂无数据"
        print("  📊 Tushare: 获取涨跌停...")
        try:
            zt = pro.limit_list_d(trade_date=d, limit_type="U")
            dt = pro.limit_list_d(trade_date=d, limit_type="D")
            result["zt_count"] = len(zt) if not zt.empty else 0
            result["dt_count"] = len(dt) if not dt.empty else 0
        except:
            result["zt_count"] = "暂无数据"
            result["dt_count"] = "暂无数据"
        print("  📊 Tushare: 获取北向资金...")
        try:
            mf = pro.moneyflow_hsgt(trade_date=d)
            if not mf.empty:
                row = mf.iloc[0]
                result["north_money"] = round(float(row.get("north_money", 0)) / 1e8, 2)
        except:
            result["north_money"] = "暂无数据"
    except Exception as e:
        print(f"  ⚠ Tushare失败: {e}")
    return result

def get_yfinance_data() -> dict:
    result = {}
    try:
        import yfinance as yf
        print("  📊 yfinance: 获取美股及大宗商品...")
        symbols = {
            "^DJI":    "道琼斯",
            "^IXIC":   "纳斯达克",
            "^GSPC":   "标普500",
            "^VIX":    "VIX恐慌指数",
            "^TNX":    "美债10年期收益率",
            "DX-Y.NYB":"美元指数",
            "CL=F":    "WTI原油",
            "BZ=F":    "布伦特原油",
            "GC=F":    "黄金",
        }
        us = {}
        for sym, name in symbols.items():
            try:
                hist = yf.Ticker(sym).history(period="2d")
                if len(hist) >= 2:
                    c = round(float(hist.iloc[-1]["Close"]), 2)
                    p = round((float(hist.iloc[-1]["Close"]) - float(hist.iloc[-2]["Close"])) / float(hist.iloc[-2]["Close"]) * 100, 2)
                    us[name] = {"close": c, "pct_chg": p}
            except:
                us[name] = "暂无数据"
        result["us_markets"] = us
        print("  📊 yfinance: 获取中概股...")
        cn_adrs = {"^HXC": "金龙中国指数", "BABA": "阿里巴巴", "PDD": "拼多多", "BIDU": "百度", "JD": "京东"}
        cn = {}
        for sym, name in cn_adrs.items():
            try:
                hist = yf.Ticker(sym).history(period="2d")
                if len(hist) >= 2:
                    c = round(float(hist.iloc[-1]["Close"]), 2)
                    p = round((float(hist.iloc[-1]["Close"]) - float(hist.iloc[-2]["Close"])) / float(hist.iloc[-2]["Close"]) * 100, 2)
                    cn[name] = {"close": c, "pct_chg": p}
            except:
                cn[name] = "暂无数据"
        result["cn_adrs"] = cn
        print("  📊 yfinance: 获取板块ETF...")
        etfs = {"SOXX": "费城半导体ETF", "QQQ": "纳指100ETF", "XLE": "能源ETF", "ARKK": "ARKK科技ETF"}
        sec = {}
        for sym, name in etfs.items():
            try:
                hist = yf.Ticker(sym).history(period="2d")
                if len(hist) >= 2:
                    c = round(float(hist.iloc[-1]["Close"]), 2)
                    p = round((float(hist.iloc[-1]["Close"]) - float(hist.iloc[-2]["Close"])) / float(hist.iloc[-2]["Close"]) * 100, 2)
                    sec[name] = {"close": c, "pct_chg": p}
            except:
                sec[name] = "暂无数据"
        result["sector_etfs"] = sec
    except Exception as e:
        print(f"  ⚠ yfinance失败: {e}")
    return result

def format_for_prompt(data: dict) -> str:
    lines = []
    if "a_shares" in data:
        lines.append("## 昨日A股收盘数据")
        for name, val in data["a_shares"].items():
            if isinstance(val, dict) and "close" in val:
                sign = "+" if val["pct_chg"] > 0 else ""
                lines.append(f"- {name}：{val['close']} ({sign}{val['pct_chg']}%)")
        if data.get("total_amount"):
            lines.append(f"- 两市总成交额：{data['total_amount']}")
        if data.get("zt_count") != "暂无数据":
            lines.append(f"- 涨停：{data['zt_count']}家，跌停：{data['dt_count']}家")
    if data.get("north_money") and data["north_money"] != "暂无数据":
        lines.append(f"\n## 北向资金\n- 北向净流入：{data['north_money']}亿元")
    if "us_markets" in data:
        lines.append("\n## 美股及大宗商品")
        for name, val in data["us_markets"].items():
            if isinstance(val, dict) and "close" in val:
                sign = "+" if val["pct_chg"] > 0 else ""
                lines.append(f"- {name}：{val['close']} ({sign}{val['pct_chg']}%)")
    if "cn_adrs" in data:
        lines.append("\n## 中概股/金龙")
        for name, val in data["cn_adrs"].items():
            if isinstance(val, dict) and "close" in val:
                sign = "+" if val["pct_chg"] > 0 else ""
                lines.append(f"- {name}：{val['close']} ({sign}{val['pct_chg']}%)")
    if "sector_etfs" in data:
        lines.append("\n## 美股板块ETF")
        for name, val in data["sector_etfs"].items():
            if isinstance(val, dict) and "close" in val:
                sign = "+" if val["pct_chg"] > 0 else ""
                lines.append(f"- {name}：{val['close']} ({sign}{val['pct_chg']}%)")
    return "\n".join(lines)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", default=datetime.now().strftime("%Y-%m-%d"))
    args = parser.parse_args()
    input_date = args.date

    # 用Tushare找上一个交易日
    trade_date = input_date
    try:
        import tushare as ts
        ts.set_token(TUSHARE_TOKEN)
        pro = ts.pro_api()
        d = input_date.replace("-", "")
        start = f"{input_date[:4]}0101"
        cal = pro.trade_cal(exchange="SSE", start_date=start, end_date=d)
        open_days = sorted(cal[cal["is_open"] == 1]["cal_date"].tolist())
        # 永远取input_date的上一个交易日（盘前报告用昨收数据）
        candidates = [x for x in open_days if x < d]
        if candidates:
            prev = candidates[-1]
            trade_date = f"{prev[:4]}-{prev[4:6]}-{prev[6:]}"
        print(f"  📅 报告日期={input_date}，使用交易日数据={trade_date}")
    except Exception as e:
        print(f"  ⚠ 交易日计算失败({e})，使用昨天日期")
        trade_date = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
    print(f"📡 开始抓取市场数据 trade_date={trade_date}")
    data = {"trade_date": trade_date, "fetch_time": datetime.now().isoformat()}
    data.update(get_tushare_data(trade_date))
    data.update(get_yfinance_data())
    data["formatted_text"] = format_for_prompt(data)
    out_path = DATA_DIR / f"{trade_date}_market_data.json"
    # 同时保存一份以report_date命名，供generate_report.py读取
    report_date = args.date
    report_out = DATA_DIR / f"{report_date}_market_data.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"\n✅ 已保存: {out_path}")
    if report_date != trade_date:
        import shutil
        shutil.copy(out_path, report_out)
        print("已同步: " + str(report_out))
    print("\n--- 数据预览 ---")
    print(data["formatted_text"])
    return str(out_path)

if __name__ == "__main__":
    main()
