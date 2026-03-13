# Market Eyes V1 交付结果

## A. 实际落地的目录结构

```
market-eyes/
├── config/
│   ├── sources.json
│   └── watchlist.json
├── scripts/
│   ├── utils.py
│   ├── fetch_rss.py
│   ├── process.py
│   ├── generate_digest.py
│   ├── generate_premarket.py
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
├── n8n-workflow-market-eyes-v1.json
├── DEPLOY_SERVER.md
└── RESULTS.md
```

服务器目标路径：`/opt/market-eyes/`（需在服务器执行 mkdir 后 rsync 或 scp 同步上述内容）。

## B. 修改后的 sources.json

见 `config/sources.json`：

- **active**（骨架源）：财联社·热门 `cls/hot`、金十数据 `jin10/index`
- **experimental**：东方财富·券商研报 `eastmoney/report/brokerreport`、深交所业务规则 `szse/rule/allrules/bussiness`
- **disabled**：示例项，不参与主流程
- **rsshub_base**：默认 `http://127.0.0.1:1200`，可由环境变量 `RSSHUB_BASE` 覆盖

## C. 实际执行的命令

```bash
# 本地验证（已跑通）
cd /Users/felix/Documents/Cursor/market-eyes
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python scripts/pipeline.py --date 2026-03-09
```

服务器部署与验收命令见 `DEPLOY_SERVER.md`（创建目录、同步文件、安装依赖、运行 `python3 scripts/pipeline.py --date 2026-03-09`）。

## D. 运行结果摘要

- **stdout**：Pipeline 依次输出 fetch（active/experimental）、process、digest、premarket 的完成提示。
- **产物**：`clean/20260309.json`、`output/digest/2026-03-09_digest.md`、`output/premarket/2026-03-09_premarket.md` 已生成。
- **日志**：`logs/pipeline_2026-03-09.log`。
- **说明**：本地无 RSSHub 时拉取为 0 条，三个文件仍会生成（digest/premarket 为空或占位内容）；服务器在 RSSHub 可用时会有正常条数。

## E. 生成的 digest 与 premarket 样例前 30 行

**digest（前 30 行）：**

```markdown
# 市场摘要 Digest — 2026-03-09

> 共 0 条（已去重）。

## 未分类
```

**premarket（前 30 行）：**

```markdown
# 盘前卡 Premarket — 2026-03-09

---

## 今日环境

- 数据源：骨架源（财联社、金十）汇总，按日去重。
- 宏观/政策：见下方分类摘要。

## 重点方向

- （暂无分类数据）

## 风险点

- 以当日快讯与公告为准，无额外风险评级。

## 今日必盯


## Top 10


## 持仓速览

暂无持仓/观察列表，请在 config/watchlist.json 配置 symbols。

---
*生成自 Market Eyes V1，date=2026-03-09*
```

## F. 当前未做、留到 Phase 2 的内容

- 接博客、接 LLM、复杂技术指标
- 实验源与主流程的深度整合（当前实验源已写入 raw/experimental 并合并进 clean）
- 数据库、双向同步
- n8n 工作流需在 n8n 中导入并填写飞书凭证；若 n8n 在 Docker 内，需挂载 `/opt/market-eyes` 并确保可执行 `python3 pipeline.py`
