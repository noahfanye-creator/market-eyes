# Market Eyes V1 服务器部署说明

## A. 实际落地的目录结构

在服务器执行以下命令创建目录（与本地 repo 一致）：

```bash
sudo mkdir -p /opt/market-eyes/{config,scripts,raw/rss,raw/market,raw/experimental,clean,output/digest,output/premarket,logs}
sudo chown -R root:root /opt/market-eyes
```

目录结构：

```
/opt/market-eyes/
├── config/
│   ├── sources.json
│   └── watchlist.json
├── scripts/
│   ├── utils.py
│   ├── fetch_rss.py
│   ├── fetch_market.py
│   ├── process.py
│   ├── generate_digest.py
│   ├── generate_premarket.py
│   ├── generate_audit.py
│   ├── generate_ai_bundle.py
│   ├── notify_feishu.py
│   └── pipeline.py
├── raw/
│   ├── rss/
│   ├── market/
│   └── experimental/
├── clean/
├── output/
│   ├── digest/
│   └── premarket/
├── logs/
├── requirements.txt
├── .env          # 服务器上创建，含 TUSHARE_TOKEN（勿提交）
├── .env.example  # 模板
└── n8n-workflow-market-eyes-v1.json
```

## B. 修改后的 sources.json

见 `config/sources.json`（骨架源：财联社、金十；实验源：东方财富券商研报、深交所业务规则）。

## C. 实际执行的命令

```bash
# 1. 创建目录（见上）
# 2. 同步本仓库到服务器（或 scp/rsync）
rsync -avz --exclude .venv --exclude .git /path/to/market-eyes/ root@154.17.3.182:/opt/market-eyes/

# 3. 服务器上安装依赖（建议用 venv）
ssh root@154.17.3.182 "cd /opt/market-eyes && python3 -m venv .venv && .venv/bin/pip install -r requirements.txt"

# 4. 服务器上配置 Tushare Token（行情拉取必选）
ssh root@154.17.3.182 "echo 'TUSHARE_TOKEN=你的token' > /opt/market-eyes/.env"
# 或 scp 本机 .env 到服务器：scp .env root@154.17.3.182:/opt/market-eyes/

# 5. 设置 RSSHub 基地址（若 RSSHub 在服务器本机 1200 端口）
export RSSHUB_BASE=http://127.0.0.1:1200

# 6. 运行 pipeline 验收（使用 venv）
ssh root@154.17.3.182 "cd /opt/market-eyes && .venv/bin/python scripts/pipeline.py --date 2026-03-09"
```

## D. 运行结果摘要

- 成功时生成：`clean/YYYYMMDD.json`、`output/digest/YYYY-MM-DD_digest.md`、`output/premarket/YYYY-MM-DD_premarket.md`
- 日志：`logs/pipeline_YYYY-MM-DD.log`
- 若本机未跑 RSSHub，拉取会失败（0 条），但三个产物仍会生成（内容为空或占位）

## E. digest / premarket 样例

见 `output/digest/` 与 `output/premarket/` 下生成的文件；premarket 含：今日环境、重点方向、风险点、今日必盯、Top 10、持仓速览。

## F. Phase 2 待办（当前未做）

- 接博客、接 LLM、复杂技术指标
- 实验源接入主流程（目前仅写入 raw/experimental，process 会合并进 clean）
- 双向同步、数据库
- n8n 工作流需在 n8n 中导入 `n8n-workflow-market-eyes-v1.json`，并填写飞书 App ID / App Secret / receive_id；若 n8n 在 Docker 内，需挂载 `/opt/market-eyes` 并确保容器内可执行 `python3 pipeline.py`
