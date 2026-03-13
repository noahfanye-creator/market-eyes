#!/usr/bin/env python3
"""
10:00 盘中快报 V0.1 入口：fetch_realtime -> fetch_rss -> process(intraday) -> generate_intraday_flash -> notify_feishu_intraday -> notify_telegram_intraday。
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
    parser = argparse.ArgumentParser(description="Market Eyes 盘中快报 Pipeline")
    parser.add_argument("--date", default=None, help="业务日期 YYYY-MM-DD")
    parser.add_argument("--time", default="10:00", choices=("10:00", "14:00"), help="快照时点，用于 10:00 或 14:00 定时任务")
    args = parser.parse_args()
    date_str = args.date or datetime.now(timezone.utc).strftime("%Y-%m-%d")
    snapshot_time = args.time
    log = setup_logging(date_str)
    log.info("pipeline_intraday start date_str=%s snapshot_time=%s", date_str, snapshot_time)
    print("📡 盘中快报 Pipeline — date=%s time=%s" % (date_str, snapshot_time))

    from fetch_realtime import fetch_realtime_data
    if not fetch_realtime_data(date_str, log):
        log.warning("fetch_realtime 未执行或失败，继续后续步骤")
    else:
        # 校验：盘中行情数据来源（新浪实时 或 Tushare 日线）
        from utils import RAW_DIR, date_str_to_compact
        compact = date_str_to_compact(date_str)
        realtime_path = RAW_DIR / "market" / f"realtime_{compact}.json"
        if realtime_path.exists():
            import json
            with open(realtime_path, encoding="utf-8") as f:
                data = json.load(f)
            meta = data.get("meta", {})
            src = meta.get("data_source", "sina")
            n_idx = len(data.get("indices", []))
            if n_idx == 0:
                log.warning("⚠ 盘中指数数据为空，请检查网络或 TUSHARE_TOKEN")
            else:
                log.info("盘中行情已确认: %s, 指数 %d 个", src, n_idx)

    from fetch_rss import run_fetch
    run_fetch(date_str)
    log.info("fetch_rss done")

    from process import run_process
    run_process(date_str, mode="intraday")
    log.info("process intraday done")

    from generate_intraday_flash import run_generate_intraday_flash
    run_generate_intraday_flash(date_str, snapshot_time=snapshot_time, logger=log)
    log.info("generate_intraday_flash done")

    from utils import OUTPUT_DIR
    time_suffix = snapshot_time.replace(":", "-")
    flash_path = OUTPUT_DIR / "intraday" / f"盘中快报_{date_str}_{time_suffix}.md"

    from notify_feishu import run_notify_feishu_intraday
    run_notify_feishu_intraday(date_str, flash_path=flash_path)
    log.info("notify_feishu_intraday done")

    try:
        from notify_telegram import run_notify_telegram_intraday
        run_notify_telegram_intraday(date_str, flash_path=flash_path)
        log.info("notify_telegram_intraday done")
    except Exception as e:
        log.warning("telegram intraday notify 异常: %s", e)

    print("✅ 盘中快报 Pipeline 完成")
    log.info("pipeline_intraday finished")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main() or 0)
    except Exception as exc:
        from datetime import datetime, timezone as _tz
        d = datetime.now(_tz.utc).strftime("%Y-%m-%d")
        try:
            from notify_feishu import run_notify_feishu
            run_notify_feishu(d, success=False, error_msg="盘中快报: " + str(exc))
        except Exception:
            pass
        try:
            from notify_telegram import run_notify_telegram
            run_notify_telegram(d, success=False, error_msg="盘中快报: " + str(exc))
        except Exception:
            pass
        raise
