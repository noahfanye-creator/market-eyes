#!/usr/bin/env python3
"""
generate_postmarket.py
读取盘后数据 + 今日盘前报告 → DeepSeek生成复盘报告
用法：python3 generate_postmarket.py --date 2026-03-13
"""

import os
import sys
import json
import argparse
import requests
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).parent.parent
load_dotenv(BASE_DIR / ".env")

POSTMARKET_DATA_DIR = BASE_DIR / "output" / "postmarket_data"
REPORT_DIR = BASE_DIR / "output" / "postmarket_report"
PREMARKET_REPORT_DIR = BASE_DIR / "output" / "report"
REPORT_DIR.mkdir(parents=True, exist_ok=True)

DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")
DEEPSEEK_URL = "https://api.deepseek.com/chat/completions"
MODEL = "deepseek-chat"

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

SYSTEM_PROMPT = """你是一位专业的A股投资研究助手，擅长技术分析与市场复盘。
你的任务是根据提供的盘后数据，技术指标和今日盘前报告，生成一份结构严谨的复盘报告。

输出规则：
- [事实]：只写已发生、可验证的数据，直接使用提供的技术指标数字
- [观察]：从数据中看到的现象，不夸大因果
- [推断]：明确写成判断，必须有数据支撑
- [评估]：对持仓和操作的客观评价

技术分析规则：
- 均线多头排列（MA5>MA10>MA20）为偏多信号
- 均线空头排列（MA5<MA10<MA20）为偏空信号
- 价格跌破MA20为重要警示，跌破MA60为趋势转空信号
- MACD红柱为多头动能，绿柱为空头动能
- RSI>70超买，RSI<30超卖
- 量比>2为放量，量比<0.5为极度缩量
- 筹码峰区间为主要支撑/压力参考
- 斐波那契0.382/0.5/0.618为关键支撑压力位

约束：
- 禁止编造数据，所有数字必须来自提供的数据
- 持仓/观察池只分析提供的名单
- 第6节必须对照今日盘前报告逐条核查
- 第9节明日关注变量必须具体可执行
- 报告语言：中文，专业简洁"""

REPORT_TEMPLATE = r"""
# 复盘报告_{date}

# 1. 今日市场一句话定性
> **{今日A股整体定性：趋势方向、情绪特征，主要驱动力}**

---

# 2. 指数与情绪

## 2.1 今日收盘数据
| 指数 | 收盘 | 涨跌幅 | 成交额 |
|------|------|--------|--------|
| 上证指数 | | | |
| 深证成指 | | | |
| 创业板指 | | | |
| 沪深300 | | | |
| 科创50 | | | |
| 两市合计 | — | — | |

## 2.2 市场情绪
- 涨停家数：
- 跌停家数：
- 北向资金：
- 情绪定性：**{亢奋 / 正常 / 谨慎 / 恐慌}**

---

# 3. 板块轮动

## 3.1 今日最强板块（TOP5）
| 排名 | 板块 | 涨跌幅 | 驱动逻辑 |
|------|------|--------|----------|
| 1 | | | |
| 2 | | | |
| 3 | | | |
| 4 | | | |
| 5 | | | |

## 3.2 今日最弱板块（TOP5）
| 排名 | 板块 | 涨跌幅 | 原因初判 |
|------|------|--------|----------|
| 1 | | | |
| 2 | | | |
| 3 | | | |
| 4 | | | |
| 5 | | | |

## 3.3 板块轮动观察
- **[观察]** 今日资金主要流向：
- **[观察]** 轮动信号：

---

# 4. 趋势结构判断

## 4.1 大盘结构

**上证指数**
- 收盘：| MA5：| MA20：| MA60：
- MACD：DIF= DEA= 柱=
- RSI14：| 量比：
- 布林带：上= 中= 下=
- 斐波那契关键位（近60日）：0.382= 0.5= 0.618=
- 筹码峰（主要成本区）：
- 今日是否破位：
- **[判断]**：

**创业板指**
- 收盘：| MA5：| MA20：| MA60：
- MACD：DIF= DEA= 柱=
- RSI14：| 量比：
- 今日是否破位：
- **[判断]**：

**科创50**
- 收盘：| MA5：| MA20：| MA60：
- MACD：DIF= DEA= 柱=
- RSI14：| 量比：
- 今日是否破位：
- **[判断]**：

## 4.2 整体结构判断
- **[推断]** 当前大盘处于：
- **[推断]** 值得警惕的信号：
- **[推断]** 值得关注的机会：

---

# 5. 资金面
- 北向资金净流入/流出：
- 沪股通：| 深股通：
- **[观察]** 资金面综合判断：

---

# 6. 盘前预判验证

| 预判内容 | 实际结果 | 验证结论 |
|----------|----------|----------|
| 主线预判1 | | ✅/❌/⚠️ |
| 主线预判2 | | |
| 主要风险 | | |
| 开盘验证点1 | | |
| 开盘验证点2 | | |

- **[总结]** 今日判断准确率：
- **[总结]** 主要偏差：
- **[总结]** 偏差原因：

---

# 7. 持仓复盘

## 7.1 持仓今日表现
| 股票 | 收盘 | 涨跌幅 | MA20上下 | MACD | RSI | 筹码峰成本区 | 逻辑变化 |
|------|------|--------|----------|------|-----|------------|----------|
| 中简科技(300777) | | | | | | | |
| 华峰铝业(601702) | | | | | | | |
| 科创50ETF(588000) | | | | | | | |
| 景嘉微(300474) | | | | | | | |
| 士兰微(600460) | | | | | | | |
| 捷捷微电(300623) | | | | | | | |

## 7.2 观察池今日表现
| 股票 | 收盘 | 涨跌幅 | 趋势判断 | 入场信号 |
|------|------|--------|----------|----------|
| 芯碁微装(688630) | | | | |
| 创新医疗(002173) | | | | |
| 润泽科技(300442) | | | | |
| 帝科股份(300842) | | | | |
| 国科微(300672) | | | | |
| 云赛智联(600602) | | | | |

## 7.3 持仓总体评估
- **[评估]** 今日持仓整体表现：
- **[评估]** 持仓逻辑有无变化：
- **[评估]** 需要关注的风险：

---

# 8. 今日最重要的发现或教训
> **{一句话，必须填}**

- 背景：
- 发现/教训：
- 下次如何改进：

---

# 9. 明日关注变量
> 直接输入明日盘前报告

1. **{变量1}**：
2. **{变量2}**：
3. **{变量3}**：
- 明日核心验证问题：

---

# 10. 三句话复盘总结
1. **[今日最重要的事实]**
2. **[今日最值得跟踪的线索]**
3. **[今日我最需要反思的事]**
"""

def build_prompt(date, postmarket_text, premarket_report):
    holdings_str = "、".join([f"{h['name']}({h['code']})" for h in HOLDINGS])
    watchlist_str = "、".join([f"{w['name']}({w['code']})" for w in WATCHLIST])

    premarket_section = ""
    if premarket_report:
        premarket_section = f"""
## 今日盘前报告（用于第6节验证）
{premarket_report[:3000]}
"""

    return f"""今天是 {date}，请根据以下数据生成复盘报告。

## 我的持仓
{holdings_str}

## 我的观察池
{watchlist_str}

## 盘后市场数据（技术指标已计算，直接填入报告）
{postmarket_text}

{premarket_section}

---
请严格按照以下模板结构输出，所有技术指标数字直接从上方数据中提取填写。
没有数据的字段写"暂无数据"。

---
{REPORT_TEMPLATE.replace('{date}', date)}
"""

def call_deepseek(system_prompt, user_prompt):
    headers = {
        "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": MODEL,
        "max_tokens": 6000,
        "temperature": 0.3,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
    }
    resp = requests.post(DEEPSEEK_URL, headers=headers, json=payload, timeout=120)
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"]

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", default=datetime.now().strftime("%Y-%m-%d"))
    args = parser.parse_args()
    date = args.date

    # 读取盘后数据
    data_path = POSTMARKET_DATA_DIR / f"{date}_postmarket_data.json"
    if not data_path.exists():
        print(f"❌ 盘后数据不存在: {data_path}")
        print(" 请先运行 fetch_postmarket_data.py")
        sys.exit(1)

    with open(data_path, encoding="utf-8") as f:
        postmarket_data = json.load(f)
    postmarket_text = postmarket_data.get("formatted_text", "")
    print(f"✅ 已加载盘后数据: {data_path.name}")

    # 读取今日盘前报告（用于验证）
    premarket_path = PREMARKET_REPORT_DIR / f"{date}_premarket_report.md"
    premarket_report = ""
    if premarket_path.exists():
        premarket_report = premarket_path.read_text(encoding="utf-8")
        print(f"✅ 已加载盘前报告: {premarket_path.name}")
    else:
        print(f"⚠ 盘前报告不存在，第6节将无法验证")

    if not DEEPSEEK_API_KEY:
        print("❌ DEEPSEEK_API_KEY 未配置")
        sys.exit(1)

    print(f"🤖 正在调用 DeepSeek 生成 {date} 复盘报告...")
    user_prompt = build_prompt(date, postmarket_text, premarket_report)

    try:
        report = call_deepseek(SYSTEM_PROMPT, user_prompt)
    except Exception as e:
        print(f"❌ DeepSeek API 调用失败: {e}")
        sys.exit(1)

    # 保存报告
    report_path = REPORT_DIR / f"{date}_postmarket_report.md"
    report_path.write_text(report, encoding="utf-8")
    print(f"✅ 复盘报告已生成: {report_path}")
    print(f" 字数：{len(report)} 字")

    return str(report_path)

if __name__ == "__main__":
    main()
