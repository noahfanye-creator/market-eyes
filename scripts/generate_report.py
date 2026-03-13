#!/usr/bin/env python3
"""
generate_report.py
读取 ai_bundle → 调 DeepSeek API → 生成盘前报告 → 保存文件
用法：python3 generate_report.py --date 2026-03-13
"""

import os
import sys
import json
import argparse
import requests
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv

# ── 路径配置 ──────────────────────────────────────────────
BASE_DIR = Path(__file__).parent.parent
load_dotenv(BASE_DIR / ".env")

BUNDLE_DIR  = BASE_DIR / "output" / "ai_bundle"
REPORT_DIR  = BASE_DIR / "output" / "report"
REPORT_DIR.mkdir(parents=True, exist_ok=True)

# ── 持仓 / 观察池（固定写在这里，后续可改成读 watchlist.json）──
HOLDINGS = [
    {"code": "300777.SZ", "name": "中简科技"},
    {"code": "601702.SH", "name": "华峰铝业"},
    {"code": "588000.SH", "name": "科创50ETF"},
    {"code": "300474.SZ", "name": "景嘉微"},
    {"code": "600460.SH", "name": "士兰微"},
    {"code": "300623.SZ", "name": "捷捷微电"},
]

WATCHLIST = [
    {"code": "688630.SH", "name": "芯碁微装"},
    {"code": "002173.SZ", "name": "创新医疗"},
    {"code": "300442.SZ", "name": "润泽科技"},
    {"code": "300842.SZ", "name": "帝科股份"},
    {"code": "300672.SZ", "name": "国科微"},
    {"code": "600602.SH", "name": "云赛智联"},
]

# ── DeepSeek API ──────────────────────────────────────────
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")
DEEPSEEK_URL     = "https://api.deepseek.com/chat/completions"
MODEL            = "deepseek-chat"

# ── Prompt ────────────────────────────────────────────────
SYSTEM_PROMPT = """你是一位专业的A股/港股投资研究助手，擅长从财经新闻中提炼投资洞察。
你的任务是根据提供的新闻数据，生成一份结构严谨、判断清晰的盘前报告。

输出规则：
- [事实]：只写已发生、可验证的信息，标注来源
- [观察]：从事实中看到的现象和结构，不夸大因果
- [推断]：明确写成判断，不伪装成事实，必须有事实支撑
- [预案]：基于方法论的行动框架，不等于预测

约束：
- 禁止编造数据（股指点位、成交额等数字如新闻中没有，写"暂无数据"）
- 对不确定信息标注"需验证"
- 持仓/观察池映射只基于提供的名单，禁止自行扩展
- 报告语言：中文，专业简洁

重要补充：
- user prompt中"市场行情数据（结构化，优先使用）"部分包含已验证的结构化行情数据
- 这些数据可以直接作为[事实]填入报告对应字段，无需标注"暂无数据"或"需验证"
- A股收盘数据填入3.3节，美股/大宗商品填入4.1节，中概股填入4.2节，板块ETF填入4.4节"""

def build_user_prompt(date: str, bundle_text: str, market_text: str = "") -> str:
    holdings_str  = "、".join([f"{h['name']}({h['code']})" for h in HOLDINGS])
    watchlist_str = "、".join([f"{w['name']}({w['code']})" for w in WATCHLIST])

    return f"""今天是 {date}，请根据以下新闻数据生成盘前报告。

## 我的持仓
{holdings_str}

## 我的观察池
{watchlist_str}

## 市场行情数据（结构化，优先使用）
{market_text}

## 今日新闻数据（ai_bundle）
{bundle_text}

---

请严格按照以下模板结构输出，所有 {{{{}}}} 占位符都必须填写。
没有数据的字段写"暂无数据"，不确定的标注"需验证"。

---

# 盘前预案_{date}

# 1. 一句话盘前结论
> **[今天盘前最重要的一句判断]**

---

# 2. 盘前快览（1分钟先看这部分）
- **外部环境**：
- **A股基调**：
- **港股基调**：
- **主线机会**：
- **主要风险**：
- **与我最相关**：
- **盲区提醒**：

---

# 3. 事实层：隔夜 / 早间核心信息

## 3.1 宏观 / 政策 / 海外
（列出3-5条最重要的宏观/海外事实，格式：- **[事实]** ...）

## 3.2 产业 / 行业 / 公司
（列出3-5条产业/公司事实）

## 3.3 昨日A股 / 港股客观回顾
（根据新闻中出现的数据填写，无数据写"暂无数据"）
### A股
- 上证指数：
- 深证成指：
- 创业板指：
- 沪深300：
- 科创50：
- 成交额：
- 上涨/下跌/涨停/跌停家数：

### 港股
- 恒生指数：
- 恒生科技：
- 国企指数：
- 港股成交额：
- 南向资金：

---

# 4. 外部市场映射

## 4.1 风险偏好总览
- **[事实] 美股三大指数**：
- **[事实] 美债10年期**：
- **[事实] 原油 / 黄金**：
- **[事实] VIX**：

## 4.2 中概 / 港股映射
- **[事实] 金龙指数**：
- **[事实] 中概代表**：

## 4.3 A股开盘映射
- **[事实] 富时A50期货**：
- **[事实] 离岸人民币**：

## 4.4 与我最相关的美股板块映射
- 半导体：
- AI / 算力：
- 新能源：
- 中概互联网：

## 4.5 外部映射观察
- **[观察]** 外部风险偏好：
- **[观察]** 对A股开盘影响：
- **[观察]** 对港股科技影响：

---

# 5. 观察层

## 5.1 新闻结构观察
- **[观察]** 最密集新闻主线：
- **[观察]** 最被资金关注方向：
- **[观察]** 最容易被忽略方向：
- **[观察]** 噪音/低价值内容：

## 5.2 昨日市场结构
- **[观察] 风格特征**：
- **[观察] 最强方向**：
- **[观察] 最弱方向**：
- **[观察] 资金偏向**：

---

# 6. 推断层

## 6.1 今日关键变量
1. **[推断]**
2. **[推断]**
3. **[推断]**

## 6.2 候选主线（列2-3条）
- **主线1**：
  - 驱动：
  - 性质：
  - 持续性初判：
  - 需验证点：

## 6.3 主要风险点
- **[推断]**
- **[推断]**

## 6.4 今天市场状态初判
- **[推断] A股状态**：
- **[推断] 港股状态**：
- **[推断] 风险偏好**：
- **[推断] 结构判断**：

---

# 7. 与我相关

## 7.1 我的持仓映射
（逐一分析每只持仓今日受影响方向，格式：- **股票名**：偏受益/偏承压/中性，原因：...）

## 7.2 我的观察池映射
（逐一分析每只观察池股票，格式：- **股票名**：今日重点盯/一般/暂不优先，原因：...）

## 7.3 与我最相关的一句话
> **[今天最值得优先关注的方向]**

---

# 8. 盲区提醒
- **[观察]**
- **[观察]**

---

# 9. 开盘后验证点

## 9.1 开盘后最该盯的5件事
1.
2.
3.
4.
5.

## 9.2 关键观察位（根据新闻中出现的价位/点位，无数据写暂无）
### A股
- 上证关键位：
- 创业板关键位：
- 科创50关键位：

## 9.3 最重要的验证问题
> **[开盘后最核心的一个验证问题]**

---

# 10. 预案层

## 10.1 今日预案
- **市场状态预判**：
- **操作倾向**：
- **仓位态度**：
- **港股态度**：

## 10.2 今日不做什么
- 不做1：
- 不做2：
- 不做3：

## 10.3 若出现超预期情况
- 若...，则...
- 若...，则...

## 10.4 当前最重要的一句话
> **[一句真正指导今天行动的话]**

---

# 11. 三句话盘前总结
1. **[今天市场最重要的事实]**
2. **[今天最值得跟踪的主线或变量]**
3. **[今天我最需要克制的事]**
"""


def call_deepseek(system_prompt: str, user_prompt: str) -> str:
    headers = {
        "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user",   "content": user_prompt},
        ],
        "max_tokens": 4096,
        "temperature": 0.3,
    }
    resp = requests.post(DEEPSEEK_URL, headers=headers, json=payload, timeout=120)
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", default=datetime.now().strftime("%Y-%m-%d"))
    args = parser.parse_args()
    date = args.date

    # 读 ai_bundle
    bundle_path = BUNDLE_DIR / f"{date}_ai_bundle.md"
    if not bundle_path.exists():
        print(f"❌ ai_bundle 不存在: {bundle_path}")
        print("   请先运行 pipeline.py 生成数据")
        sys.exit(1)

    bundle_text = bundle_path.read_text(encoding="utf-8")
    # 截断防止超token（保留前15000字符）
    if len(bundle_text) > 15000:
        bundle_text = bundle_text[:15000] + "\n\n[...数据已截断...]"

    if not DEEPSEEK_API_KEY:
        print("❌ DEEPSEEK_API_KEY 未配置")
        sys.exit(1)

    print(f"🤖 正在调用 DeepSeek 生成 {date} 盘前报告...")
    # 读取市场数据
    import json
    from pathlib import Path
    market_text = ""
    market_data_path = Path("/home/node/market-eyes/output/market_data") / f"{date}_market_data.json"
    if market_data_path.exists():
        try:
            md = json.loads(market_data_path.read_text(encoding="utf-8"))
            market_text = md.get("formatted_text", "")
            print(f"  已加载市场数据: {market_data_path.name}")
        except Exception as e:
            print(f"  市场数据读取失败: {e}")
    else:
        print(f"  市场数据不存在，将仅使用新闻数据")
    user_prompt = build_user_prompt(date, bundle_text, market_text)

    try:
        report = call_deepseek(SYSTEM_PROMPT, user_prompt)
    except Exception as e:
        print(f"❌ DeepSeek API 调用失败: {e}")
        sys.exit(1)

    # 保存报告

    # 后处理：结构化数据强制覆盖报告中对应行
    try:
        import json as _json, re as _re
        _md_path = Path("/home/node/market-eyes/output/market_data") / f"{date}_market_data.json"
        if _md_path.exists():
            _md = _json.loads(_md_path.read_text(encoding="utf-8"))
            _a = _md.get("a_shares", {})
            def _fmt(name):
                v = _a.get(name)
                if isinstance(v, dict) and "close" in v:
                    sign = "+" if v["pct_chg"] > 0 else ""
                    return f"{v['close']} ({sign}{v['pct_chg']}%)"
                return None
            _fixes = {
                "上证指数": _fmt("上证指数"),
                "深证成指": _fmt("深证成指"),
                "创业板指": _fmt("创业板指"),
                "沪深300": _fmt("沪深300"),
                "科创50": _fmt("科创50"),
            }
            for name, val in _fixes.items():
                if val:
                    report = _re.sub(
                        rf"(- {name}：)[^\n]*",
                        rf"\g<1>{val}",
                        report
                    )
            total = _md.get("total_amount")
            if total:
                report = _re.sub(r"(- 成交额：)[^\n]*", rf"\g<1>{total}", report)
            print("  ✅ 结构化数据已填入报告")
    except Exception as _e:
        print(f"  ⚠ 后处理失败: {_e}")
    report_path = REPORT_DIR / f"{date}_premarket_report.md"
    report_path.write_text(report, encoding="utf-8")
    print(f"✅ 报告已生成: {report_path}")
    print(f"   字数：{len(report)} 字")

    return report_path


if __name__ == "__main__":
    main()
