#!/bin/bash
# 在服务器上执行，排查「定时没有触发」的原因
# 用法：ssh root@你的服务器 "bash -s" < scripts/check_cron.sh

echo "=== 1. 当前时间与时区 ==="
date
echo "TZ=${TZ:-未设置}"
timedatectl 2>/dev/null || true

echo ""
echo "=== 2. crontab 是否包含 market-eyes 任务 ==="
if crontab -l 2>/dev/null | grep -q "market-eyes"; then
  echo "已找到 market-eyes 相关行："
  crontab -l 2>/dev/null | grep "market-eyes"
else
  echo "未找到！请执行: ssh root@服务器 'bash -s' < scripts/setup_cron_830.sh"
fi

echo ""
echo "=== 3. crontab 首行是否有时区（CRON_TZ） ==="
crontab -l 2>/dev/null | head -3 || echo "无 crontab 或无法读取"

echo ""
echo "=== 4. cron 服务状态 ==="
systemctl is-active cron 2>/dev/null || systemctl is-active crond 2>/dev/null || echo "无法获取（可能非 systemd）"

echo ""
echo "=== 5. 盘中 10:00 最近日志（cron_intraday.log） ==="
if [ -f /opt/market-eyes/logs/cron_intraday.log ]; then
  tail -20 /opt/market-eyes/logs/cron_intraday.log
else
  echo "文件不存在，说明 10:00 任务从未被 cron 执行过"
fi

echo ""
echo "=== 5b. 盘中 14:00 最近日志（cron_intraday_1400.log） ==="
if [ -f /opt/market-eyes/logs/cron_intraday_1400.log ]; then
  tail -20 /opt/market-eyes/logs/cron_intraday_1400.log
else
  echo "文件不存在，说明 14:00 任务从未被 cron 执行过"
fi

echo ""
echo "=== 6. 今日 pipeline 日志（若有） ==="
TODAY=$(date +%Y-%m-%d)
if [ -f "/opt/market-eyes/logs/pipeline_${TODAY}.log" ]; then
  tail -15 "/opt/market-eyes/logs/pipeline_${TODAY}.log"
else
  echo "今日 pipeline 日志不存在"
fi
