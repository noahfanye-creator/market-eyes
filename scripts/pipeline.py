#!/usr/bin/env python3
"""
Market Eyes V1 唯一入口：--date YYYY-MM-DD，依次执行 fetch -> process -> digest -> premarket。
所有子步骤均使用此处传入的 date_str，子脚本不自行取“今天”。
"""

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

# 确保 scripts 在 path 中
_scripts_dir = Path(__file__).resolve().parent
sys.path.insert(0, str(_scripts_dir))

# 加载项目根目录 .env（TUSHARE_TOKEN 等）
try:
    from dotenv import load_dotenv
    load_dotenv(_scripts_dir.parent / ".env")
except ImportError:
    pass

from utils import setup_logging

# 子步骤以函数形式调用，避免子脚本内取“今天”
def main():
    parser = argparse.ArgumentParser(description="Market Eyes V1 Pipeline")
    parser.add_argument("--date", default=None, help="业务日期 YYYY-MM-DD，默认今天 UTC")
    parser.add_argument(
        "--session",
        default="premarket",
        choices=["premarket", "midday", "intraday", "postmarket"],
        help="运行场景：premarket/midday/intraday/postmarket",
    )
    args = parser.parse_args()
    date_str = args.date
    if not date_str:
        date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    log = setup_logging(date_str)
    log.info("pipeline start date_str=%s", date_str)
    print(f"📡 Market Eyes Pipeline — date={date_str}")

    # 1. 拉取 RSS（仅用 date_str）
    from fetch_rss import run_fetch
    run_fetch(date_str)
    log.info("fetch_rss done")

    # 2. 拉取行情数据（指数 + 观察列表标的）
    try:
        from fetch_market import fetch_market_data
        if fetch_market_data(date_str, log):
            log.info("fetch_market done")
        else:
            log.warning("fetch_market 未执行或失败，盘前卡将使用占位数据")
    except Exception as e:
        log.warning("fetch_market 异常: %s，盘前卡将使用占位数据", e)

    # 3. 清洗去重分类
    from process import run_process
    run_process(date_str)
    log.info("process done")

    # 4. 生成 digest
    from generate_digest import run_generate_digest
    run_generate_digest(date_str)
    log.info("generate_digest done")

    # 5. 生成 premarket
    from generate_premarket import run_generate_premarket
    run_generate_premarket(date_str)
    log.info("generate_premarket done")

    # 6. 生成分类验收抽样表
    from generate_audit import run_generate_audit
    run_generate_audit(date_str)
    log.info("generate_audit done")

    # 7. 生成 AI 原料包（轻去重、按来源分组、供大模型二次提炼）
    from generate_ai_bundle import run_generate_ai_bundle
    run_generate_ai_bundle(date_str)
    log.info("generate_ai_bundle done")

    # 8. 生成 AI Bundle（session 数据包，供 LLM + prompt 使用）
    bundle_filename = None
    try:
        from generate_bundle import generate_bundle
        bundle_path = generate_bundle(date_str, session=args.session, logger=log)
        if bundle_path:
            bundle_filename = bundle_path.name
            log.info("generate_bundle done: %s", bundle_filename)
        else:
            log.info("generate_bundle 未生成（session 未实现或失败）")
    except Exception as e:
        log.warning("generate_bundle 异常: %s", e)

    # 8b. 生成 premarket_bundle.json（最小化 JSON 结构）
    try:
        from build_json_bundles import run_build_premarket_bundle
        run_build_premarket_bundle(date_str, logger=log)
    except Exception as e:
        log.warning("build_json_bundles premarket 异常: %s", e)

    # 9. 飞书通知
    from notify_feishu import run_notify_feishu
    run_notify_feishu(date_str, success=True, bundle_filename=bundle_filename)
    log.info("feishu notify done")

    # 10. Telegram 通知（与飞书一致：摘要 + bundle 附件）
    try:
        from notify_telegram import run_notify_telegram
        run_notify_telegram(date_str, success=True, bundle_filename=bundle_filename)
        log.info("telegram notify done")
    except Exception as e:
        log.warning("telegram notify 异常: %s", e)

    print("✅ Pipeline 完成")
    log.info("pipeline finished")
    # 先抓市场数据
    from fetch_market_data import main as run_fetch
    import sys as _sys
    _sys.argv = [_sys.argv[0], '--date', date_str]
    run_fetch()
    from generate_report import main as run_report
    run_report()
    log.info("report generation done")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main() or 0)
    except Exception as exc:
        from datetime import datetime, timezone as _tz
        d = datetime.now(_tz.utc).strftime("%Y-%m-%d")
        try:
            from notify_feishu import run_notify_feishu
            run_notify_feishu(d, success=False, error_msg=str(exc))
        except Exception:
            pass
        try:
            from notify_telegram import run_notify_telegram
            run_notify_telegram(d, success=False, error_msg=str(exc))
        except Exception:
            pass
        raise
