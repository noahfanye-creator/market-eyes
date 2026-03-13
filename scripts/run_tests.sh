#!/bin/bash
# 四类产物挨个测试：盘前 -> 盘中 -> 午盘 -> 盘后
# 在服务器上执行：cd /opt/market-eyes/scripts && bash run_tests.sh [YYYY-MM-DD]
# 不传日期则用当天（按服务器时区 date +%Y-%m-%d）

set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$SCRIPT_DIR"
DATE="${1:-$(date +%Y-%m-%d)}"
PY="${PY:-$ROOT/.venv/bin/python}"

echo "=========================================="
echo "Market Eyes 四类产物测试 — date=$DATE"
echo "=========================================="

# 1. 盘前
echo ""
echo "[1/4] 盘前 pipeline ..."
if "$PY" "$ROOT/scripts/pipeline.py" --date "$DATE"; then
  echo "  ✅ 盘前 完成"
else
  echo "  ❌ 盘前 失败"
  exit 1
fi

# 2. 盘中（10:00/14:00 简报 + 喂模型 MD）
echo ""
echo "[2/4] 盘中快报 pipeline ..."
if "$PY" "$ROOT/scripts/pipeline_intraday.py" --date "$DATE"; then
  echo "  ✅ 盘中 完成"
else
  echo "  ❌ 盘中 失败"
  exit 1
fi

# 3. 午盘（仅 bundle + 简报 + 喂模型，不拉数据）
echo ""
echo "[3/4] 午盘 bundle + 简报 ..."
if "$PY" "$ROOT/scripts/build_json_bundles.py" --date "$DATE" --type midday && "$PY" "$ROOT/scripts/briefs.py" --date "$DATE" --type midday; then
  echo "  ✅ 午盘 完成"
else
  echo "  ❌ 午盘 失败"
  exit 1
fi

# 4. 盘后（先拉数据再生成 bundle + 简报 + 喂模型 MD）
echo ""
echo "[4/4] 盘后 pipeline（抓取数据 -> bundle -> 简报）..."
if "$PY" "$ROOT/scripts/pipeline_postmarket.py" --date "$DATE"; then
  echo "  ✅ 盘后 完成"
else
  echo "  ❌ 盘后 失败"
  exit 1
fi

echo ""
echo "=========================================="
echo "全部 4 类测试通过"
echo "可检查：output/premarket/ output/intraday/ output/midday/ output/postmarket/ output/ai_bundle/"
echo "=========================================="
