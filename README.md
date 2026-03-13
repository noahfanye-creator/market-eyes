# Market Eyes V1

A 股盘前情报流水线。自动从 RSSHub 拉取财经快讯，按规则分类（宏观 / 个股 / 行业 / 政策监管），生成盘前卡并推送到飞书。

## 流水线架构

```
RSSHub (财联社·热门、金十数据、东财研报、深交所规则)
  │
  ▼
fetch_rss.py ─── 拉取 + 解析 RSS ──► raw/rss/*.json + raw/experimental/*.json
  │
  ▼
process.py ───── 去重 + 关键词分类 ──► clean/*.json
  │
  ├──► generate_digest.py ──────────► output/digest/*_digest.md
  ├──► generate_premarket.py ───────► output/premarket/*_premarket.md
  ├──► generate_audit.py ───────────► output/category_audit_*.md
  └──► notify_feishu.py ───────────► 飞书消息推送
```

**唯一入口**：`scripts/pipeline.py --date YYYY-MM-DD`，按顺序执行以上 6 个步骤。

## 目录结构

```
market-eyes/
├── config/
│   ├── sources.json        # RSS 源配置（active / experimental / disabled）
│   ├── categories.json     # 分类规则（关键词 + 个股实体/事件词 + 排除模式）
│   └── watchlist.json      # 持仓/自选股列表
├── scripts/
│   ├── pipeline.py         # 主入口，串联所有步骤
│   ├── fetch_rss.py        # 拉取 RSS 源
│   ├── process.py          # 去重、分类
│   ├── generate_digest.py  # 生成市场摘要
│   ├── generate_premarket.py # 生成盘前卡
│   ├── generate_audit.py   # 生成分类抽样审计表
│   ├── notify_feishu.py    # 飞书通知
│   └── utils.py            # 公共工具（路径、配置加载、日志）
├── raw/                    # 原始 RSS 拉取数据
│   ├── rss/                #   骨架源（active）
│   └── experimental/       #   实验源
├── clean/                  # 去重分类后的清洗数据
├── output/
│   ├── digest/             # 市场摘要 Markdown
│   └── premarket/          # 盘前卡 Markdown
├── logs/                   # 运行日志
└── requirements.txt
```

## 快速开始

```bash
# 1. 创建虚拟环境并安装依赖
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# 2. 确保 RSSHub 已启动（默认 http://127.0.0.1:1200）

# 3. 运行 pipeline
python scripts/pipeline.py --date 2026-03-09
```

产物：
- `clean/YYYYMMDD.json` — 去重分类后的结构化数据
- `output/digest/YYYY-MM-DD_digest.md` — 按分类展开的完整摘要
- `output/premarket/YYYY-MM-DD_premarket.md` — 盘前卡（重点方向 + Top 10 + 持仓速览）
- `output/category_audit_YYYY-MM-DD.md` — 分类抽样审计表，用于人工复核
- 飞书消息推送（成功推盘前卡，失败推告警）

## 配置说明

### sources.json — RSS 源

```json
{
  "rsshub_base": "http://127.0.0.1:1200",
  "active": [
    { "id": "cls_hot", "name": "财联社·热门", "path": "cls/hot" },
    { "id": "jin10", "name": "金十数据", "url": "http://127.0.0.1:1200/jin10", "skip_date_filter": true }
  ],
  "experimental": [ ... ],
  "disabled": [ ... ]
}
```

- `active` 源进入盘前卡，`experimental` 源仅存 raw 数据供观察
- 可通过 `url` 字段覆盖默认的 `rsshub_base/path` 拼接
- `skip_date_filter: true` 跳过日期过滤（用于不带标准时间戳的源）
- 环境变量 `RSSHUB_BASE` 可覆盖配置文件中的 `rsshub_base`

### categories.json — 分类规则

分类优先级：**个股 > 宏观 > 行业 > 政策监管 > 综合**

个股判定采用强匹配策略（不走普通关键词规则）：
1. 命中 watchlist 中的持仓/自选股名称 → 个股
2. 标题匹配排除模式（券商晨报、交易所规则文件） → 跳过，不判个股
3. 标题含 A 股股票代码（6 位数字） → 个股
4. 标题+摘要同时命中实体词 + 事件词 → 个股

其余分类按关键词顺序匹配，未命中任何规则的归入"综合"。

### watchlist.json — 持仓/自选股

```json
{
  "symbols": [
    { "symbol": "600519", "name": "贵州茅台", "note": "核心持仓" }
  ],
  "updated_at": "2026-03-09"
}
```

watchlist 中的股票名会在分类时优先命中"个股"，并在盘前卡中显示持仓速览。

## 服务器部署

```bash
# 项目部署到 /opt/market-eyes
scp -r . root@your-server:/opt/market-eyes/

# 安装依赖
ssh root@your-server
cd /opt/market-eyes
pip3 install -r requirements.txt

# 手动验证
cd /opt/market-eyes/scripts && python3 pipeline.py --date $(date +%Y-%m-%d)
```

### 定时任务

通过宿主机 crontab 自动执行（每周一至周五）：

| 时点 | 脚本 | 日志 |
|------|------|------|
| 北京 8:30 | `pipeline.py` 盘前卡 | `logs/cron.log` |
| 北京 10:00 | `pipeline_intraday.py --time 10:00` 盘中快报 | `logs/cron_intraday.log` |
| 北京 14:00 | `pipeline_intraday.py --time 14:00` 盘中快报 | `logs/cron_intraday_1400.log` |

若服务器时区为 **Asia/Shanghai**（或使用脚本写入的 `CRON_TZ=Asia/Shanghai`）：

```bash
# 8:30 盘前卡
30 8 * * 1-5 cd /opt/market-eyes/scripts && .venv/bin/python pipeline.py --date $(date +\%Y-\%m-\%d) >> /opt/market-eyes/logs/cron.log 2>&1

# 10:00 盘中快报
0 10 * * 1-5 cd /opt/market-eyes/scripts && .venv/bin/python pipeline_intraday.py --date $(date +\%Y-\%m-\%d) --time 10:00 >> /opt/market-eyes/logs/cron_intraday.log 2>&1

# 14:00 盘中快报
0 14 * * 1-5 cd /opt/market-eyes/scripts && .venv/bin/python pipeline_intraday.py --date $(date +\%Y-\%m-\%d) --time 14:00 >> /opt/market-eyes/logs/cron_intraday_1400.log 2>&1
```

若服务器时区为 **UTC**（北京 8:30 = UTC 0:30，10:00 = UTC 2:00，14:00 = UTC 6:00）：

```bash
30 0 * * 1-5 cd /opt/market-eyes/scripts && .venv/bin/python pipeline.py --date $(date +\%Y-\%m-\%d) >> /opt/market-eyes/logs/cron.log 2>&1
0 2 * * 1-5 cd /opt/market-eyes/scripts && .venv/bin/python pipeline_intraday.py --date $(date +\%Y-\%m-\%d) --time 10:00 >> /opt/market-eyes/logs/cron_intraday.log 2>&1
0 6 * * 1-5 cd /opt/market-eyes/scripts && .venv/bin/python pipeline_intraday.py --date $(date +\%Y-\%m-\%d) --time 14:00 >> /opt/market-eyes/logs/cron_intraday_1400.log 2>&1
```

- 盘前 / 盘中 Pipeline 内部均集成飞书通知；异常时推送失败告警。
- 一键配置脚本：`scripts/setup_cron_830.sh`（会在 crontab 首行写入 `CRON_TZ=Asia/Shanghai`，并写入 8:30 盘前 + 10:00/14:00 盘中三条任务）。

### 定时没有触发时怎么查

常见原因与对应检查：

| 原因 | 检查方式 |
|------|----------|
| 从未在服务器上配置过 cron | 在服务器执行一次：`ssh root@你的服务器 "bash -s" < scripts/setup_cron_830.sh` |
| 服务器是 UTC，未设时区，10:00 变成 18:00 北京 | 用 `setup_cron_830.sh` 会写入 `CRON_TZ=Asia/Shanghai`；或手动在 crontab 第一行加该行 |
| 当天是周六/日 | 任务为 `1-5`（周一至周五），周末不会跑 |
| cron 服务未运行 | `systemctl status cron` 或 `systemctl status crond` |
| 路径或 .venv 错误 | 日志里有 Python 报错；确认 `/opt/market-eyes/scripts/.venv/bin/python` 存在 |

**一键诊断（在服务器上跑）：**

```bash
ssh root@你的服务器 "bash -s" < scripts/check_cron.sh
```

会输出：当前时间/时区、crontab 是否含 market-eyes、是否有 CRON_TZ、cron 服务状态、盘中日志尾行。

### 日常运维检查

| 检查项 | 命令 |
|--------|------|
| 盘前 cron | `tail -50 /opt/market-eyes/logs/cron.log` |
| 盘中 10:00 | `tail -50 /opt/market-eyes/logs/cron_intraday.log` |
| 盘中 14:00 | `tail -50 /opt/market-eyes/logs/cron_intraday_1400.log` |
| 当日 pipeline 日志 | `cat /opt/market-eyes/logs/pipeline_$(date +%Y-%m-%d).log` |
| 分类分布 | 查看 `output/category_audit_*.md` |
| Jin10 是否有数据 | cron.log 中搜索 `金十数据: 保留` |

## 依赖

- Python 3.10+
- [RSSHub](https://docs.rsshub.app/) 实例（本地 `127.0.0.1:1200`）
- `feedparser` — RSS 解析
- `requests` — HTTP 请求 + 飞书 API
