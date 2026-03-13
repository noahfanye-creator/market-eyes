#!/usr/bin/env python3
"""
盘后 pipeline：拉取当日数据后生成 postmarket bundle + 盘后简报 + 喂模型 MD。
顺序：fetch_rss -> process -> fetch_market -> build_json_bundles(postmarket) -> briefs(postmarket)。
"""
import sys
from pathlib import Path

_scripts_dir = Path(__file__).resolve().parent
sys.path.insert(0, str(_scripts_dir))
try:
    from dotenv import load_dotenv
    load_dotenv(_scripts_dir.parent / ".env")
except ImportError:
    pass

from utils import setup_logging


def main():
    import argparse
    from datetime import datetime, timezone
    parser = argparse.ArgumentParser(description="Market Eyes 盘后 Pipeline")
    parser.add_argument("--date", default=None, help="业务日期 YYYY-MM-DD")
    args = parser.parse_args()
    date_str = args.date or datetime.now(timezone.utc).strftime("%Y-%m-%d")
    log = setup_logging(date_str)
    log.info("pipeline_postmarket start date_str=%s", date_str)
    print(f"📡 盘后 Pipeline — date={date_str}")

    from fetch_rss import run_fetch
    run_fetch(date_str)
    log.info("fetch_rss done")

    from process import run_process
    run_process(date_str)
    log.info("process done")

    from fetch_market import fetch_market_data
    if fetch_market_data(date_str, log):
        log.info("fetch_market done -> raw/market/daily_*.json")
    else:
        log.warning("fetch_market 未执行或失败（如无 TUSHARE_TOKEN），盘后 bundle 可能缺日线数据")

    from build_json_bundles import build_postmarket_bundle_json
    build_postmarket_bundle_json(date_str, logger=log)
    log.info("postmarket bundle done")

    from briefs import write_postmarket_brief_and_llm
    write_postmarket_brief_and_llm(date_str, logger=log)
    log.info("盘后简报与喂模型 MD done")

    from notify_feishu import run_notify_feishu_postmarket
    run_notify_feishu_postmarket(date_str)
    log.info("notify_feishu_postmarket done")

    try:
        from notify_telegram import run_notify_telegram_postmarket
        run_notify_telegram_postmarket(date_str)
        log.info("notify_telegram_postmarket done")
    except Exception as e:
        log.warning("telegram 盘后通知异常: %s", e)

    print("✅ 盘后 Pipeline 完成")
    log.info("pipeline_postmarket finished")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main() or 0)
    except Exception as exc:
        from datetime import datetime as _dt, timezone as _tz
        d = _dt.now(_tz.utc).strftime("%Y-%m-%d")
        try:
            from notify_feishu import run_notify_feishu
            run_notify_feishu(d, success=False, error_msg="盘后: " + str(exc))
        except Exception:
            pass
        raise
