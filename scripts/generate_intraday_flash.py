#!/usr/bin/env python3
"""
盘中 10:00 数据包流水线：只负责产出「素材包」，不写结论、不定调、不生成快报正文。
1. 抓指数 2. 抓板块强弱 3. 抓龙头/watchlist 4. 抓 08:30–10:00 增量快讯 5. 提供盘前关键点摘要。
输出：intraday_1000_bundle.json（固定字段）+ intraday_bundle.md（供转发 LLM）。
若配置 OPENAI_API_KEY，可选用 LLM 生成五段快报正文并写入 盘中快报_xxx.md；未配置则不写占位结论。
"""
import json
import os
import re
from pathlib import Path

from utils import CLEAN_DIR, CONFIG_DIR, OUTPUT_BUNDLE_DIR, OUTPUT_DIR, RAW_DIR, date_str_to_compact

INTRADAY_DIR = OUTPUT_DIR / "intraday"


def _load_realtime(date_str: str) -> dict:
    compact = date_str_to_compact(date_str)
    path = RAW_DIR / "market" / f"realtime_{compact}.json"
    if not path.exists():
        return {}
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _load_intraday_clean(date_str: str) -> dict:
    compact = date_str_to_compact(date_str)
    path = CLEAN_DIR / f"{compact}_intraday.json"
    if not path.exists():
        return {}
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _load_premarket_summary(date_str: str, max_lines: int = 40) -> str:
    path = OUTPUT_DIR / "premarket" / f"{date_str}_premarket.md"
    if not path.exists():
        return "（无盘前摘要）"
    text = path.read_text(encoding="utf-8")
    lines = text.strip().split("\n")[:max_lines]
    return "\n".join(lines)


def _build_data_blob(date_str: str, snapshot_time: str = "10:00") -> str:
    realtime = _load_realtime(date_str)
    clean = _load_intraday_clean(date_str)
    premarket = _load_premarket_summary(date_str)

    parts = [f"日期: {date_str}  报告时点: {snapshot_time}\n"]
    indices = realtime.get("indices") or []
    if indices:
        parts.append("【指数】")
        for x in indices:
            parts.append(f"  {x.get('name','')} 涨跌{x.get('pct_chg',0)}% 状态:{x.get('status','')}")
    sectors_top = realtime.get("sectors_top") or []
    sectors_bottom = realtime.get("sectors_bottom") or []
    if sectors_top:
        parts.append("【最强板块】 " + ", ".join(f"{s.get('name','')}({s.get('pct_chg',0)}%)" for s in sectors_top))
    if sectors_bottom:
        parts.append("【最弱板块】 " + ", ".join(f"{s.get('name','')}({s.get('pct_chg',0)}%)" for s in sectors_bottom))
    watchlist = realtime.get("watchlist") or []
    if watchlist:
        parts.append("【龙头/观察】")
        for x in watchlist:
            parts.append(f"  {x.get('name','')} 涨跌{x.get('pct_chg',0)}% {x.get('status_summary','')}")
    entries = clean.get("entries") or []
    if entries:
        parts.append("【盘中快讯摘要】")
        for e in entries[:15]:
            parts.append(f"  - {e.get('title','')[:80]}")
    parts.append("\n【盘前预案摘要】\n" + premarket)
    return "\n".join(parts)


PROMPT_SYSTEM = """你是盘中快报撰写助手。根据给定的数据，只输出 5 段判断句，每段短、硬、直接。强调变化量，不重复背景。数据不足时保守表述，不编造。"""

PROMPT_USER_TEMPLATE = """请根据以下数据，严格按下面 5 段格式输出，每段只输出一行结论（可带一句补充），不要输出标题或序号以外的内容。

数据：
{data}

输出格式（每段一行，放在 > 引用块内）：
1. 快结论：开盘半小时后市场最重要的变化。
2. 盘面定调：指数状态 + 最强板块 + 最弱板块 + 市场当前在交易什么（修复/避险/高低切/主线强化/兑现/混沌）。
3. 主线质量：龙头承接 + 板块扩散或分化 + 当前更像强化/修复/分歧/兑现/独强。
4. 对照盘前：已验证的一条 + 已偏离或未验证的一条。
5. 当前提醒：和你最相关的一点 + 最不该误判的地方。"""


def _write_intraday_bundle(date_str: str, data_blob: str) -> Path:
    """将盘中数据包（使用说明 + 数据 + Prompt）写入 output/ai_bundle/{date}_intraday_bundle.md，便于整段转发给 LLM。"""
    OUTPUT_BUNDLE_DIR.mkdir(parents=True, exist_ok=True)
    path = OUTPUT_BUNDLE_DIR / f"{date_str}_intraday_bundle.md"
    user_prompt_with_data = PROMPT_USER_TEMPLATE.format(data=data_blob)
    body = f"""# 盘中快报 — 数据包（可整段转发给 LLM）

**使用方式**：将下方「数据」整段 + 「Prompt」一起发给 LLM，即可生成 5 段盘中快报。

---

## 数据

{data_blob}

---

## Prompt（系统消息）

{PROMPT_SYSTEM}

---

## Prompt（用户消息，已填入上方数据）

{user_prompt_with_data}
"""
    path.write_text(body.strip() + "\n", encoding="utf-8")
    return path


def _call_llm(data_blob: str, logger=None) -> str:
    api_key = os.environ.get("OPENAI_API_KEY", "").strip()
    if not api_key:
        if logger:
            logger.warning("未配置 OPENAI_API_KEY，使用占位文案")
        return None
    try:
        import requests
        url = os.environ.get("OPENAI_API_BASE", "https://api.openai.com/v1").rstrip("/") + "/chat/completions"
        model = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")
        body = {
            "model": model,
            "messages": [
                {"role": "system", "content": PROMPT_SYSTEM},
                {"role": "user", "content": PROMPT_USER_TEMPLATE.format(data=data_blob)},
            ],
            "max_tokens": 800,
            "temperature": 0.3,
        }
        resp = requests.post(url, headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}, json=body, timeout=60)
        resp.raise_for_status()
        out = resp.json()
        content = (out.get("choices") or [{}])[0].get("message", {}).get("content", "")
        return content.strip() if content else None
    except Exception as e:
        if logger:
            logger.warning("LLM 调用失败: %s", e)
        return None


def _parse_llm_sections(content: str) -> dict:
    if not content or not content.strip():
        return {}
    sections = {}
    current = None
    buf = []
    for line in content.split("\n"):
        if re.match(r"^#\s*[1-5]\.", line) or re.match(r"^[1-5]\.", line):
            if current is not None:
                sections[current] = "\n".join(buf).strip()
            for i in range(1, 6):
                if str(i) in line or (f"#{i}." in line) or (f"# {i}." in line):
                    current = i
                    break
            buf = [line]
        else:
            buf.append(line)
    if current is not None:
        sections[current] = "\n".join(buf).strip()
    return sections


def _placeholder_sections() -> dict:
    return {
        1: "开盘半小时后主要变化待观察。",
        2: "指数与板块数据不足，盘面定调待补充。",
        3: "龙头与主线质量待数据支持后补充。",
        4: "对照盘前：暂无验证/偏离结论。",
        5: "当前提醒：注意仓位与节奏，勿追高杀跌。",
    }


def _fill_template(date_str: str, sections: dict, snapshot_time: str = "10:00") -> str:
    title = f"盘中快报_{date_str}_{snapshot_time}"
    lines = [
        "---",
        f"title: {title}",
        f"date: {date_str}",
        f"time: {snapshot_time}",
        "market: A股 / 港股盘中",
        "tags: [盘中, 快报, 市场观察]",
        "---",
        "",
        "# 1. 快结论",
        "> **" + (sections.get(1) or _placeholder_sections()[1]) + "**",
        "",
        "# 2. 盘面定调",
        "> **" + (sections.get(2) or _placeholder_sections()[2]) + "**",
        "",
        "# 3. 主线质量",
        "> **" + (sections.get(3) or _placeholder_sections()[3]) + "**",
        "",
        "# 4. 对照盘前",
        "- **已验证**：" + (sections.get(4) or _placeholder_sections()[4]).split("。")[0] + "。",
        "- **已偏离**：待补充。",
        "",
        "# 5. 当前提醒",
        "> **" + (sections.get(5) or _placeholder_sections()[5]) + "**",
    ]
    return "\n".join(lines)


def run_generate_intraday_flash(date_str: str, snapshot_time: str = "10:00", logger=None) -> Path:
    # 1. 固定输出数据包（素材），不写结论；仅生成当前时点
    data_blob = _build_data_blob(date_str, snapshot_time=snapshot_time)
    bundle_path = _write_intraday_bundle(date_str, data_blob)
    if logger:
        logger.info("盘中数据包已写入 %s", bundle_path.name)
    try:
        from build_json_bundles import run_build_intraday_bundle
        run_build_intraday_bundle(date_str, snapshot_time=snapshot_time, logger=logger)
    except Exception as e:
        if logger:
            logger.warning("intraday bundle 生成异常: %s", e)
    try:
        from briefs import write_intraday_brief_and_llm
        write_intraday_brief_and_llm(date_str, snapshot_time=snapshot_time, logger=logger)
    except Exception as e:
        if logger:
            logger.warning("盘中简报/喂模型 MD 生成异常: %s", e)

    # 2. 快报正文仅由 LLM 生成；未配置 LLM 时不写占位结论，只写说明
    INTRADAY_DIR.mkdir(parents=True, exist_ok=True)
    time_suffix = snapshot_time.replace(":", "-")
    out_path = INTRADAY_DIR / f"盘中快报_{date_str}_{time_suffix}.md"
    api_key = os.environ.get("OPENAI_API_KEY", "").strip()
    suffix = snapshot_time.replace(":", "")
    if api_key:
        content_llm = _call_llm(data_blob, logger)
        if content_llm:
            sections = _parse_llm_sections(content_llm)
            if not sections:
                sections = {i: s for i, s in _placeholder_sections().items()}
        else:
            sections = _placeholder_sections()
        md = _fill_template(date_str, sections, snapshot_time=snapshot_time)
        out_path.write_text(md, encoding="utf-8")
    else:
        stub = f"""---
title: 盘中快报_{date_str}_{snapshot_time}
date: {date_str}
time: {snapshot_time}
---

# 说明

本文件为占位。正式快报请由 LLM 根据数据包生成。

**数据包**：`output/ai_bundle/{date_str}_intraday_{suffix}_bundle.json` 或 `{date_str}_intraday_bundle.md`
将数据包 + 其中 Prompt 发给 LLM，按模板输出 5 段（快结论、盘面定调、主线质量、对照盘前、当前提醒）。
"""
        out_path.write_text(stub.strip() + "\n", encoding="utf-8")
    print(f"  ✅ {out_path.relative_to(OUTPUT_DIR.parent)}")
    return out_path


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--date", required=True, help="YYYY-MM-DD")
    p.add_argument("--time", default="10:00", choices=("10:00", "14:00"), help="快照时点")
    args = p.parse_args()
    run_generate_intraday_flash(args.date, snapshot_time=args.time)
