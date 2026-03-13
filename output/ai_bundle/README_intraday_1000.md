# 10:00 盘中数据包（素材包）

**用途**：供后续 LLM 按「盘中快报模板」生成正式报告。本包**只提供数据**，不写结论、不定调、不生成快报正文。

**文件名**：`{YYYY-MM-DD}_intraday_1000_bundle.json`

**生成**：`scripts/build_json_bundles.py --type intraday`（或由 `pipeline_intraday.py` 在 10:00 流程中调用）

---

## 字段说明

| 字段 | 说明 |
|------|------|
| `date` | 日期 YYYY-MM-DD |
| `snapshot_time` | 快照时点，固定 "10:00" |
| `generated_at` | 包生成时间（UTC），便于排查 |
| `indices` | 指数列表，每项：`name`, `current`, `pct_chg`, `open`, `pre_close` |
| `sectors_top3` | 当日涨幅前三板块：`name`, `pct_chg` |
| `sectors_bottom3` | 当日跌幅前三板块：`name`, `pct_chg` |
| `leaders` | 龙头/watchlist 快照：`name`, `pct_chg`, `status_summary` |
| `news_increment` | 08:30–10:00 增量快讯列表：`title`, `source`, `published` |
| `premarket_key_points` | 盘前关键点摘要（来自当日盘前预案文本，截取前若干行） |

---

## 数据来源（不扩源）

- 指数 / 板块 / watchlist：`raw/market/realtime_{YYYYMMDD}.json`
- 增量快讯：`clean/{YYYYMMDD}_intraday.json`
- 盘前摘要：`output/premarket/{YYYY-MM-DD}_premarket.md`

---

## 不包含的内容

- 快结论、盘面定调、主线质量、对照盘前、当前提醒
- 盘中快报正文或 5 段式结论

上述内容由下游 LLM 根据本数据包 + 模板生成。
