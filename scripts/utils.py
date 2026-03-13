#!/usr/bin/env python3
"""Market Eyes 工具：项目路径、配置、日期、日志。"""

import json
import logging
from pathlib import Path

# 项目根目录（脚本在 scripts/ 下）
ROOT = Path(__file__).resolve().parent.parent

CONFIG_DIR = ROOT / "config"
RAW_DIR = ROOT / "raw"
CLEAN_DIR = ROOT / "clean"
OUTPUT_DIR = ROOT / "output"
LOGS_DIR = ROOT / "logs"
OUTPUT_BUNDLE_DIR = OUTPUT_DIR / "ai_bundle"


def ensure_dirs():
    """确保 pipeline 所需目录存在（含 output/ai_bundle）。"""
    for d in (
        LOGS_DIR,
        CLEAN_DIR,
        RAW_DIR,
        RAW_DIR / "rss",
        RAW_DIR / "market",
        RAW_DIR / "experimental",
        OUTPUT_DIR,
        OUTPUT_BUNDLE_DIR,
        OUTPUT_DIR / "premarket",
        OUTPUT_DIR / "intraday",
        OUTPUT_DIR / "midday",
        OUTPUT_DIR / "postmarket",
        OUTPUT_DIR / "digest",
    ):
        d.mkdir(parents=True, exist_ok=True)


def date_str_to_compact(date_str: str) -> str:
    """YYYY-MM-DD -> YYYYMMDD"""
    if not date_str:
        return ""
    return date_str.replace("-", "")


def load_sources():
    """加载 config/sources.json"""
    p = CONFIG_DIR / "sources.json"
    if not p.exists():
        return {}
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def load_watchlist():
    """加载 config/watchlist.json"""
    p = CONFIG_DIR / "watchlist.json"
    if not p.exists():
        return {"symbols": [], "updated_at": ""}
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def setup_logging(date_str: str) -> logging.Logger:
    """配置日志，写入 logs/pipeline_YYYY-MM-DD.log"""
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    log_file = LOGS_DIR / f"pipeline_{date_str}.log"
    logger = logging.getLogger("market_eyes")
    logger.setLevel(logging.INFO)
    if logger.handlers:
        logger.handlers.clear()
    fh = logging.FileHandler(log_file, encoding="utf-8")
    fh.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
    logger.addHandler(fh)
    return logger
