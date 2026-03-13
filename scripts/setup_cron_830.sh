#!/bin/bash
# 在服务器上执行：写入盘前 8:30 + 盘中 10:00 + 盘中 14:00 三条 market-eyes 定时任务（周一至周五，北京时间）
# 用法：ssh root@你的服务器 "bash -s" < scripts/setup_cron_830.sh
# 脚本会在 crontab 首行写入 CRON_TZ=Asia/Shanghai，保证 8:30/10:00/14:00 按北京时区触发

set -e
BACKUP="/opt/market-eyes/logs/crontab.bak.$(date +%Y%m%d%H%M%S)"
CRON_830="30 8 * * 1-5 cd /opt/market-eyes/scripts && .venv/bin/python pipeline.py --date \$(date +%Y-%m-%d) >> /opt/market-eyes/logs/cron.log 2>&1"
CRON_1000="0 10 * * 1-5 cd /opt/market-eyes/scripts && .venv/bin/python pipeline_intraday.py --date \$(date +%Y-%m-%d) --time 10:00 >> /opt/market-eyes/logs/cron_intraday.log 2>&1"
CRON_1400="0 14 * * 1-5 cd /opt/market-eyes/scripts && .venv/bin/python pipeline_intraday.py --date \$(date +%Y-%m-%d) --time 14:00 >> /opt/market-eyes/logs/cron_intraday_1400.log 2>&1"

mkdir -p /opt/market-eyes/logs
crontab -l 2>/dev/null > "$BACKUP" || true
# 去掉旧 market-eyes 行和已有 CRON_TZ，再写入 CRON_TZ + 三条任务（保证按北京时间触发）
REST=$(crontab -l 2>/dev/null | grep -v "market-eyes" | grep -v "^CRON_TZ=" || true)
{
  echo "CRON_TZ=Asia/Shanghai"
  echo "$REST"
  echo "$CRON_830"
  echo "$CRON_1000"
  echo "$CRON_1400"
} | crontab -
echo "已更新 crontab：CRON_TZ=Asia/Shanghai，8:30 盘前 + 10:00/14:00 盘中，原配置已备份到 $BACKUP"
crontab -l
