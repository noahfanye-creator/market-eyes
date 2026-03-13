#!/bin/bash
# 从本机同步到服务器并在服务器跑 pipeline 测试
# 用法：./deploy_and_test.sh [服务器] [日期] [premarket|intraday|postmarket|all]
# 示例：./deploy_and_test.sh root@154.17.3.182 2026-03-09
#       ./deploy_and_test.sh root@154.17.3.182 2026-03-10 intraday
#       ./deploy_and_test.sh root@154.17.3.182 2026-03-10 all   # 同步后跑四类挨个测试
# 使用 -i 指定密钥时免密；也可设置环境变量 MARKET_EYES_SSH_KEY

set -e
SERVER="${1:-root@154.17.3.182}"
DATE="${2:-$(date +%Y-%m-%d)}"
MODE="${3:-premarket}"
ROOT="$(cd "$(dirname "$0")" && pwd)"
SSH_KEY="${MARKET_EYES_SSH_KEY:-$HOME/Documents/ssh_rsa_keys/private_key/id_rsa.pem}"
if [ -f "$SSH_KEY" ]; then
  SSH_OPTS=(-i "$SSH_KEY")
  RSH="ssh -i $SSH_KEY"
else
  SSH_OPTS=()
  RSH="ssh"
fi

echo "=== 1. 同步到 $SERVER ==="
rsync -avz -e "$RSH" --exclude .venv --exclude .git --exclude __pycache__ --exclude "*.pyc" \
  "$ROOT/" "$SERVER:/opt/market-eyes/"

echo ""
if [ "$MODE" = "all" ]; then
  echo "=== 2. 在服务器确保 venv 与依赖 ==="
  ssh "${SSH_OPTS[@]}" "$SERVER" "cd /opt/market-eyes && (test -d .venv || python3 -m venv .venv) && .venv/bin/python -m pip install -q -r requirements.txt"
  echo ""
  echo "=== 3. 在服务器执行四类测试 (date=$DATE) ==="
  ssh "${SSH_OPTS[@]}" "$SERVER" "cd /opt/market-eyes/scripts && chmod +x run_tests.sh && bash run_tests.sh $DATE"
  echo ""
  echo "=== 3. 拉回部分产物到本机 ==="
  mkdir -p "$ROOT/output/ai_bundle" "$ROOT/output/premarket" "$ROOT/output/intraday" "$ROOT/output/midday" "$ROOT/output/postmarket"
  scp "${SSH_OPTS[@]}" "$SERVER:/opt/market-eyes/output/premarket/${DATE}_premarket.md" "$ROOT/output/premarket/" 2>/dev/null && echo "  ✅ 盘前简报" || true
  scp "${SSH_OPTS[@]}" "$SERVER:/opt/market-eyes/output/intraday/盘中快报_${DATE}_1000.md" "$ROOT/output/intraday/" 2>/dev/null && echo "  ✅ 盘中 10:00 简报" || true
  scp "${SSH_OPTS[@]}" "$SERVER:/opt/market-eyes/output/midday/午盘简报_${DATE}.md" "$ROOT/output/midday/" 2>/dev/null && echo "  ✅ 午盘简报" || true
  scp "${SSH_OPTS[@]}" "$SERVER:/opt/market-eyes/output/postmarket/盘后简报_${DATE}.md" "$ROOT/output/postmarket/" 2>/dev/null && echo "  ✅ 盘后简报" || true
  echo ""
  echo "=== 4. 完成 ==="
  echo "四类简报见：output/premarket/ output/intraday/ output/midday/ output/postmarket/"
elif [ "$MODE" = "postmarket" ]; then
  echo "=== 2. 在服务器执行盘后 pipeline (date=$DATE) ==="
  ssh "${SSH_OPTS[@]}" "$SERVER" "cd /opt/market-eyes && (test -d .venv || python3 -m venv .venv) && .venv/bin/python -m pip install -q -r requirements.txt && .venv/bin/python scripts/pipeline_postmarket.py --date $DATE"
  echo ""
  echo "=== 3. 拉回盘后产物到本机 ==="
  mkdir -p "$ROOT/output/postmarket" "$ROOT/output/ai_bundle"
  scp "${SSH_OPTS[@]}" "$SERVER:/opt/market-eyes/output/postmarket/盘后简报_${DATE}.md" "$ROOT/output/postmarket/" 2>/dev/null && echo "  ✅ 盘后简报" || true
  scp "${SSH_OPTS[@]}" "$SERVER:/opt/market-eyes/output/ai_bundle/${DATE}_postmarket_bundle.json" "$ROOT/output/ai_bundle/" 2>/dev/null && echo "  ✅ postmarket_bundle.json" || true
  scp "${SSH_OPTS[@]}" "$SERVER:/opt/market-eyes/output/ai_bundle/${DATE}_postmarket_llm_bundle.md" "$ROOT/output/ai_bundle/" 2>/dev/null && echo "  ✅ postmarket_llm_bundle.md" || true
  echo ""
  echo "=== 完成 ==="
  echo "盘后简报：$ROOT/output/postmarket/盘后简报_${DATE}.md"
  echo "喂模型 MD：$ROOT/output/ai_bundle/${DATE}_postmarket_llm_bundle.md"
elif [ "$MODE" = "intraday" ]; then
  echo "=== 2. 在服务器执行盘中 pipeline (date=$DATE) ==="
  ssh "${SSH_OPTS[@]}" "$SERVER" "cd /opt/market-eyes && (test -d .venv || python3 -m venv .venv) && .venv/bin/python -m pip install --upgrade pip && .venv/bin/pip install -q -r requirements.txt && .venv/bin/python scripts/pipeline_intraday.py --date $DATE"

  echo ""
  echo "=== 3. 拉回盘中快报与数据包到本机 ==="
  mkdir -p "$ROOT/output/ai_bundle" "$ROOT/output/intraday"
  scp "${SSH_OPTS[@]}" "$SERVER:/opt/market-eyes/output/ai_bundle/${DATE}_intraday_bundle.md" "$ROOT/output/ai_bundle/" 2>/dev/null && echo "  ✅ 已拉回 ${DATE}_intraday_bundle.md" || echo "  ⚠ 未找到 intraday_bundle"
  scp "${SSH_OPTS[@]}" "$SERVER:/opt/market-eyes/output/ai_bundle/${DATE}_intraday_1000_bundle.json" "$ROOT/output/ai_bundle/" 2>/dev/null && echo "  ✅ 已拉回 ${DATE}_intraday_1000_bundle.json" || true
  scp "${SSH_OPTS[@]}" "$SERVER:/opt/market-eyes/output/intraday/盘中快报_${DATE}_10-00.md" "$ROOT/output/intraday/" 2>/dev/null && echo "  ✅ 已拉回盘中快报" || true
  scp "${SSH_OPTS[@]}" "$SERVER:/opt/market-eyes/raw/market/realtime_${DATE//-/}.json" "$ROOT/raw/market/" 2>/dev/null && echo "  ✅ 已拉回 realtime 数据（可检查 meta.tushare_calls）" || true

  echo ""
  echo "=== 完成 ==="
  echo "盘中数据包：$ROOT/output/ai_bundle/${DATE}_intraday_bundle.md"
  echo "盘中快报：$ROOT/output/intraday/盘中快报_${DATE}_10-00.md"
else
  echo "=== 2. 在服务器执行盘前 pipeline (date=$DATE) ==="
  ssh "${SSH_OPTS[@]}" "$SERVER" "cd /opt/market-eyes && (test -d .venv || python3 -m venv .venv) && .venv/bin/python -m pip install --upgrade pip && .venv/bin/pip install -q -r requirements.txt && .venv/bin/python scripts/pipeline.py --date $DATE"

  echo ""
  echo "=== 3. 拉回 AI 数据包与盘前卡到本机（供附加给 LLM）==="
  mkdir -p "$ROOT/output/ai_bundle" "$ROOT/output/premarket"
  scp "${SSH_OPTS[@]}" "$SERVER:/opt/market-eyes/output/ai_bundle/${DATE}_premarket_bundle.md" "$ROOT/output/ai_bundle/" 2>/dev/null && echo "  ✅ 已拉回 output/ai_bundle/${DATE}_premarket_bundle.md" || echo "  ⚠ 未找到 bundle，可能未生成"
  scp "${SSH_OPTS[@]}" "$SERVER:/opt/market-eyes/output/ai_bundle/${DATE}_premarket_bundle.json" "$ROOT/output/ai_bundle/" 2>/dev/null && echo "  ✅ 已拉回 ${DATE}_premarket_bundle.json" || true
  scp "${SSH_OPTS[@]}" "$SERVER:/opt/market-eyes/output/premarket/${DATE}_premarket.md" "$ROOT/output/premarket/" 2>/dev/null && echo "  ✅ 已拉回 output/premarket/${DATE}_premarket.md" || true

  echo ""
  echo "=== 完成 ==="
  echo "AI 数据包（附加给 LLM）：$ROOT/output/ai_bundle/${DATE}_premarket_bundle.md"
  echo "盘前卡：$ROOT/output/premarket/${DATE}_premarket.md"
fi
