#!/usr/bin/env python3
"""
四类产物的简报版 + 喂模型版 MD 生成。
- 简报版：按模板填数据，缺项用 "-"
- 喂模型版：说明 + 数据视图（从 JSON 渲染）+ 简报模板 + 简短 Prompt
"""
from __future__ import annotations

import json
from pathlib import Path

from utils import OUTPUT_BUNDLE_DIR, OUTPUT_DIR, date_str_to_compact

INTRADAY_DIR = OUTPUT_DIR / "intraday"
MIDDAY_DIR = OUTPUT_DIR / "midday"
POSTMARKET_DIR = OUTPUT_DIR / "postmarket"

# ---------- 简报模板（用户给定） ----------
INTRADAY_BRIEF_TEMPLATE = """# 盘中快报 {{date}} {{time}}

## 一句话变化
- {{一句话变化}}

## 盘面状态
- 指数：{{指数}}
- 最强方向：{{最强方向}}
- 最弱方向：{{最弱方向}}

## 主线观察
- 龙头/核心方向：{{龙头}}
- 现在更像：{{强化/修复/分歧/兑现}}

## 对照前序判断
- 已验证：{{已验证}}
- 已偏离：{{已偏离}}

## 当前提醒
- {{当前提醒}}
"""

MIDDAY_BRIEF_TEMPLATE = """# 午盘简报 {{date}}

## 上午一句话总结
- {{上午一句话总结}}

## 上午盘面
- 指数：{{指数}}
- 最强方向：{{最强方向}}
- 最弱方向：{{最弱方向}}

## 上午验证结果
- 盘前判断验证了什么：{{验证了什么}}
- 哪些地方不及预期：{{不及预期}}

## 下午重点看什么
- {{重点1}}
- {{重点2}}
- {{重点3}}
"""

POSTMARKET_BRIEF_TEMPLATE = """# 盘后简报 {{date}}

## 今日一句话结论
- {{今日一句话结论}}

## 大盘概览
- 指数表现：{{指数表现}}
- 成交额：{{成交额}}
- 情绪/宽度：{{情绪宽度}}

## 今日主线与弱线
- 最强方向：{{最强方向}}
- 最弱方向：{{最弱方向}}
- 龙头表现：{{龙头表现}}

## 今日最关键的盘面信号
- {{信号1}}
- {{信号2}}
- {{信号3}}

## 明日关注
- {{明日重点1}}
- {{明日重点2}}
- {{明日重点3}}
"""


def _fmt_pct(v) -> str:
    if v is None:
        return "-"
    try:
        return f"{float(v)}%"
    except (TypeError, ValueError):
        return "-"


def _format_indices(indices: list) -> str:
    if not indices:
        return "-"
    return "；".join(f"{x.get('name','')} {_fmt_pct(x.get('pct_chg'))}" for x in indices if x.get("name"))


def _format_sectors(sectors: list) -> str:
    if not sectors:
        return "-"
    return "、".join(f"{s.get('name','')}({_fmt_pct(s.get('pct_chg'))})" for s in sectors)


def _format_leaders(leaders: list) -> str:
    if not leaders:
        return "-"
    return "；".join(f"{x.get('name','')} {_fmt_pct(x.get('pct_chg'))}" for x in leaders[:8] if x.get("name"))


def _render_intraday_brief(bundle: dict, time_label: str) -> str:
    indices = bundle.get("indices") or []
    top3 = bundle.get("sectors_top3") or []
    bot3 = bundle.get("sectors_bottom3") or []
    leaders = bundle.get("leaders") or []
    date_str = bundle.get("date", "")
    return INTRADAY_BRIEF_TEMPLATE.replace("{{date}}", date_str).replace("{{time}}", time_label).replace("{{一句话变化}}", "-").replace("{{指数}}", _format_indices(indices)).replace("{{最强方向}}", _format_sectors(top3)).replace("{{最弱方向}}", _format_sectors(bot3)).replace("{{龙头}}", _format_leaders(leaders)).replace("{{强化/修复/分歧/兑现}}", "-").replace("{{已验证}}", "-").replace("{{已偏离}}", "-").replace("{{当前提醒}}", "-")


def _render_midday_brief(bundle: dict) -> str:
    indices = bundle.get("indices_am") or []
    top = bundle.get("sectors_top_am") or []
    bot = bundle.get("sectors_bottom_am") or []
    leaders = bundle.get("leaders_am") or []
    date_str = bundle.get("date", "")
    return (
        MIDDAY_BRIEF_TEMPLATE.replace("{{date}}", date_str)
        .replace("{{上午一句话总结}}", "-")
        .replace("{{指数}}", _format_indices(indices))
        .replace("{{最强方向}}", _format_sectors(top))
        .replace("{{最弱方向}}", _format_sectors(bot))
        .replace("{{验证了什么}}", "-")
        .replace("{{不及预期}}", "-")
        .replace("{{重点1}}", "-")
        .replace("{{重点2}}", "-")
        .replace("{{重点3}}", "-")
    )


def _render_postmarket_brief(bundle: dict) -> str:
    indices = bundle.get("indices_full") or []
    top = bundle.get("sectors_top") or []
    bot = bundle.get("sectors_bottom") or []
    leaders = bundle.get("leaders_and_highflyers") or []
    date_str = bundle.get("date", "")
    idx_str = _format_indices([{"name": x.get("name"), "pct_chg": x.get("pct_chg")} for x in indices])
    return (
        POSTMARKET_BRIEF_TEMPLATE.replace("{{date}}", date_str)
        .replace("{{今日一句话结论}}", "-")
        .replace("{{指数表现}}", idx_str)
        .replace("{{成交额}}", "-")
        .replace("{{情绪宽度}}", "-")
        .replace("{{最强方向}}", _format_sectors(top))
        .replace("{{最弱方向}}", _format_sectors(bot))
        .replace("{{龙头表现}}", _format_leaders(leaders))
        .replace("{{信号1}}", "-")
        .replace("{{信号2}}", "-")
        .replace("{{信号3}}", "-")
        .replace("{{明日重点1}}", "-")
        .replace("{{明日重点2}}", "-")
        .replace("{{明日重点3}}", "-")
    )


def _bundle_to_data_view(bundle: dict, report_type: str) -> str:
    """把 JSON bundle 转成可读的 Markdown 数据块。"""
    lines = [f"日期: {bundle.get('date', '')}", ""]
    if report_type == "intraday":
        lines.append("【指数】")
        for x in bundle.get("indices") or []:
            lines.append(f"  {x.get('name','')} 现价 {x.get('current')} 涨跌 {x.get('pct_chg')}%")
        lines.append("【最强板块 Top3】 " + _format_sectors(bundle.get("sectors_top3") or []))
        lines.append("【最弱板块 Top3】 " + _format_sectors(bundle.get("sectors_bottom3") or []))
        lines.append("【龙头/观察】")
        for x in bundle.get("leaders") or []:
            lines.append(f"  {x.get('name','')} {x.get('pct_chg')}% {x.get('status_summary','')}")
        lines.append("【本时段增量快讯】")
        for e in (bundle.get("news_increment") or [])[:15]:
            lines.append(f"  - {e.get('title','')[:80]}")
        pre = (bundle.get("premarket_key_points") or "")[:800]
        if pre:
            lines.append("\n【盘前关键点摘要】\n" + pre)
    elif report_type == "midday":
        lines.append("【上午指数】")
        for x in bundle.get("indices_am") or []:
            lines.append(f"  {x.get('name','')} 涨跌 {x.get('pct_chg')}%")
        lines.append("【上午最强/最弱】 " + _format_sectors(bundle.get("sectors_top_am") or []) + " / " + _format_sectors(bundle.get("sectors_bottom_am") or []))
        lines.append("【上午龙头】 " + _format_leaders(bundle.get("leaders_am") or []))
        lines.append("【上午快讯】")
        for e in (bundle.get("news_am") or [])[:10]:
            lines.append(f"  - {e.get('title','')[:80]}")
        pre = (bundle.get("premarket_key_points") or "")[:800]
        if pre:
            lines.append("\n【盘前关键点】\n" + pre)
    else:
        indices_full = bundle.get("indices_full") or []
        news_full = bundle.get("news_full") or []
        if not indices_full and not news_full:
            lines.append("（当日盘后行情未入库或数据源未就绪，以下数据块为空。可仅按模板写占位或简述。）")
            lines.append("")
        lines.append("【指数】")
        for x in indices_full:
            amt = x.get("amount_yi")
            amt_str = f" 成交额 {amt}亿" if amt is not None else ""
            lines.append(f"  {x.get('name','')} 收盘 {x.get('close')} 涨跌 {_fmt_pct(x.get('pct_chg'))}{amt_str}")
        lines.append("【最强/最弱板块】 " + _format_sectors(bundle.get("sectors_top") or []) + " / " + _format_sectors(bundle.get("sectors_bottom") or []))
        lines.append("【龙头/高标】 " + _format_leaders(bundle.get("leaders_and_highflyers") or []))
        lines.append("【全天新闻摘要】")
        for e in news_full[:20]:
            lines.append(f"  - {e.get('title','')[:80]}")
    return "\n".join(lines)


def _llm_section(report_type: str) -> tuple[str, str]:
    """返回 (简报模板全文, 写作要求一两句)."""
    if report_type == "intraday":
        return INTRADAY_BRIEF_TEMPLATE, "请仅根据上方数据，按模板填空输出。一句话变化、对照前序、当前提醒需结合数据写一句结论，勿编造。"
    if report_type == "midday":
        return MIDDAY_BRIEF_TEMPLATE, "请仅根据上方数据，按模板填空。上午验证结果需对照盘前关键点；下午重点写 2～3 条可观察点。"
    return POSTMARKET_BRIEF_TEMPLATE, "请仅根据上方数据，按模板填空。今日结论与盘面信号需有数据支撑；明日关注写 2～3 条可验证命题。"


def _load_bundle(path: Path) -> dict:
    if not path.exists():
        return {}
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def write_intraday_brief_and_llm(date_str: str, snapshot_time: str = "10:00", logger=None) -> tuple[Path | None, Path | None]:
    """写盘中快报简报版 + 喂模型版。snapshot_time 为 10:00 或 14:00。"""
    suffix = snapshot_time.replace(":", "")
    bundle_path = OUTPUT_BUNDLE_DIR / f"{date_str}_intraday_{suffix}_bundle.json"
    bundle = _load_bundle(bundle_path)
    time_label = "10:00" if snapshot_time == "10:00" else "14:00"

    INTRADAY_DIR.mkdir(parents=True, exist_ok=True)
    brief_path = INTRADAY_DIR / f"盘中快报_{date_str}_{suffix}.md"
    brief_content = _render_intraday_brief(bundle, time_label)
    brief_path.write_text(brief_content.strip() + "\n", encoding="utf-8")
    if logger:
        logger.info("盘中简报已写入 %s", brief_path.name)

    template_full, prompt = _llm_section("intraday")
    data_view = _bundle_to_data_view(bundle, "intraday")
    llm_content = f"""# 盘中快报 — 喂模型包（{date_str} {time_label}）

**使用方式**：将本文件整体发给大语言模型，模型只输出一份《盘中快报》，严格按下方模板填空。

---

## 一、数据（只读）

{data_view}

---

## 二、简报模板（模型须严格遵守）

{template_full}

---

## 三、写作要求

{prompt}
"""
    llm_path = OUTPUT_BUNDLE_DIR / f"{date_str}_intraday_{suffix}_llm_bundle.md"
    OUTPUT_BUNDLE_DIR.mkdir(parents=True, exist_ok=True)
    llm_path.write_text(llm_content.strip() + "\n", encoding="utf-8")
    if logger:
        logger.info("盘中喂模型 MD 已写入 %s", llm_path.name)
    return brief_path, llm_path


def write_midday_brief_and_llm(date_str: str, logger=None) -> tuple[Path | None, Path | None]:
    """写午盘简报版 + 喂模型版。"""
    bundle_path = OUTPUT_BUNDLE_DIR / f"{date_str}_midday_bundle.json"
    bundle = _load_bundle(bundle_path)

    MIDDAY_DIR.mkdir(parents=True, exist_ok=True)
    brief_path = MIDDAY_DIR / f"午盘简报_{date_str}.md"
    brief_content = _render_midday_brief(bundle)
    brief_path.write_text(brief_content.strip() + "\n", encoding="utf-8")
    if logger:
        logger.info("午盘简报已写入 %s", brief_path.name)

    template_full, prompt = _llm_section("midday")
    data_view = _bundle_to_data_view(bundle, "midday")
    llm_content = f"""# 午盘简报 — 喂模型包（{date_str}）

**使用方式**：将本文件整体发给大语言模型，模型只输出一份《午盘简报》，严格按下方模板填空。

---

## 一、数据（只读）

{data_view}

---

## 二、简报模板（模型须严格遵守）

{template_full}

---

## 三、写作要求

{prompt}
"""
    llm_path = OUTPUT_BUNDLE_DIR / f"{date_str}_midday_llm_bundle.md"
    OUTPUT_BUNDLE_DIR.mkdir(parents=True, exist_ok=True)
    llm_path.write_text(llm_content.strip() + "\n", encoding="utf-8")
    if logger:
        logger.info("午盘喂模型 MD 已写入 %s", llm_path.name)
    return brief_path, llm_path


def write_postmarket_brief_and_llm(date_str: str, logger=None) -> tuple[Path | None, Path | None]:
    """写盘后简报版 + 喂模型版。"""
    bundle_path = OUTPUT_BUNDLE_DIR / f"{date_str}_postmarket_bundle.json"
    bundle = _load_bundle(bundle_path)

    POSTMARKET_DIR.mkdir(parents=True, exist_ok=True)
    brief_path = POSTMARKET_DIR / f"盘后简报_{date_str}.md"
    brief_content = _render_postmarket_brief(bundle)
    brief_path.write_text(brief_content.strip() + "\n", encoding="utf-8")
    if logger:
        logger.info("盘后简报已写入 %s", brief_path.name)

    template_full, prompt = _llm_section("postmarket")
    data_view = _bundle_to_data_view(bundle, "postmarket")
    llm_content = f"""# 盘后简报 — 喂模型包（{date_str}）

**使用方式**：将本文件整体发给大语言模型，模型只输出一份《盘后简报》，严格按下方模板填空。

---

## 一、数据（只读）

{data_view}

---

## 二、简报模板（模型须严格遵守）

{template_full}

---

## 三、写作要求

{prompt}
"""
    llm_path = OUTPUT_BUNDLE_DIR / f"{date_str}_postmarket_llm_bundle.md"
    OUTPUT_BUNDLE_DIR.mkdir(parents=True, exist_ok=True)
    llm_path.write_text(llm_content.strip() + "\n", encoding="utf-8")
    if logger:
        logger.info("盘后喂模型 MD 已写入 %s", llm_path.name)
    return brief_path, llm_path


def run_all_briefs(date_str: str, logger=None) -> None:
    """生成盘中(10:00/14:00)、午盘、盘后的简报 + 喂模型 MD。依赖对应 JSON bundle 已存在。"""
    for t in ("10:00", "14:00"):
        write_intraday_brief_and_llm(date_str, snapshot_time=t, logger=logger)
    write_midday_brief_and_llm(date_str, logger=logger)
    write_postmarket_brief_and_llm(date_str, logger=logger)


if __name__ == "__main__":
    import argparse
    from utils import setup_logging
    p = argparse.ArgumentParser()
    p.add_argument("--date", required=True, help="YYYY-MM-DD")
    p.add_argument("--type", choices=["intraday", "midday", "postmarket", "all"], default="all")
    args = p.parse_args()
    log = setup_logging(args.date)
    if args.type in ("intraday", "all"):
        for t in ("10:00", "14:00"):
            write_intraday_brief_and_llm(args.date, snapshot_time=t, logger=log)
    if args.type in ("midday", "all"):
        write_midday_brief_and_llm(args.date, logger=log)
    if args.type in ("postmarket", "all"):
        write_postmarket_brief_and_llm(args.date, logger=log)
    print("  ✅ 简报与喂模型 MD 已生成")
