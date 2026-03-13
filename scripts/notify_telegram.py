#!/usr/bin/env python3
"""
与飞书一致：发送盘前卡摘要 + AI 数据包附件、以及盘中快报到 Telegram。需配置 TELEGRAM_BOT_TOKEN、TELEGRAM_CHAT_ID。
"""

import os
from pathlib import Path

import requests
from utils import OUTPUT_DIR

TIMEOUT = 30
TG_MAX_TEXT = 4096  # Telegram 单条消息长度上限


def _api_url(token: str, method: str) -> str:
    return f"https://api.telegram.org/bot{token}/{method}"


def _send_message(token: str, chat_id: str, text: str) -> None:
    if not text.strip():
        return
    # 单条超过 4096 则截断并提示见附件
    if len(text) > TG_MAX_TEXT:
        text = text[: TG_MAX_TEXT - 50] + "\n\n...（完整内容见下方附件）"
    resp = requests.post(
        _api_url(token, "sendMessage"),
        json={"chat_id": chat_id, "text": text},
        timeout=TIMEOUT,
    )
    resp.raise_for_status()
    data = resp.json()
    if not data.get("ok"):
        raise RuntimeError(data.get("description", "sendMessage failed"))


def _send_document(token: str, chat_id: str, file_path) -> None:
    with open(file_path, "rb") as f:
        resp = requests.post(
            _api_url(token, "sendDocument"),
            data={"chat_id": chat_id},
            files={"document": (file_path.name, f)},
            timeout=60,
        )
    resp.raise_for_status()
    data = resp.json()
    if not data.get("ok"):
        raise RuntimeError(data.get("description", "sendDocument failed"))


def run_notify_telegram(
    date_str: str,
    success: bool = True,
    error_msg: str = "",
    bundle_filename: str = None,
) -> None:
    token = (os.environ.get("TELEGRAM_BOT_TOKEN") or "").strip()
    chat_id = (os.environ.get("TELEGRAM_CHAT_ID") or "").strip()
    if not token or not chat_id:
        print("  ⚠ 未配置 TELEGRAM_BOT_TOKEN 或 TELEGRAM_CHAT_ID，跳过 Telegram 通知")
        return

    if success:
        premarket_path = OUTPUT_DIR / "premarket" / f"{date_str}_premarket.md"
        if premarket_path.exists():
            text = premarket_path.read_text(encoding="utf-8")
        else:
            text = f"盘前卡已生成，但文件未找到: {premarket_path}"
        if bundle_filename:
            text = text + "\n\n---\n📎 AI 数据包见下条附件。请下载附件，将附件与你的提示词一起发给 GPT 使用。"
    else:
        text = f"Market Eyes Pipeline 失败\n{error_msg}"

    try:
        _send_message(token, chat_id, text)
        print("  ✅ Telegram 通知已发送")
    except Exception as e:
        print(f"  ⚠ Telegram 发送失败: {e}")
        return

    if success and bundle_filename:
        bundle_path = OUTPUT_DIR / "ai_bundle" / bundle_filename
        if not bundle_path.exists():
            print(f"  ⚠ 未找到 bundle 文件，跳过 Telegram 附件: {bundle_path}")
            return
        try:
            _send_document(token, chat_id, bundle_path)
            print(f"  ✅ Telegram 已发送附件: {bundle_filename}")
        except Exception as e:
            print(f"  ⚠ Telegram 发送附件失败: {e}")


def run_notify_telegram_intraday(date_str: str, flash_path=None) -> None:
    """推送盘中快报 md 到 Telegram；有 intraday_bundle 时同时发附件（与盘前一致）。flash_path 默认 output/intraday/盘中快报_{date_str}_10-00.md"""
    token = (os.environ.get("TELEGRAM_BOT_TOKEN") or "").strip()
    chat_id = (os.environ.get("TELEGRAM_CHAT_ID") or "").strip()
    if not token or not chat_id:
        print("  ⚠ 未配置 TELEGRAM_BOT_TOKEN 或 TELEGRAM_CHAT_ID，跳过 Telegram 盘中快报")
        return
    if flash_path is None:
        flash_path = OUTPUT_DIR / "intraday" / f"盘中快报_{date_str}_10-00.md"
    path = Path(flash_path)
    if not path.exists():
        print(f"  ⚠ 盘中快报文件不存在: {path}")
        return
    text = path.read_text(encoding="utf-8")
    bundle_filename = f"{date_str}_intraday_bundle.md"
    bundle_path = OUTPUT_DIR / "ai_bundle" / bundle_filename
    if bundle_path.exists():
        text = text + "\n\n---\n📎 AI 数据包见下条附件。请下载附件，将附件与你的提示词一起发给 GPT 使用。"
    try:
        _send_message(token, chat_id, text)
        print("  ✅ Telegram 盘中快报已发送")
    except Exception as e:
        print(f"  ⚠ Telegram 盘中快报发送失败: {e}")
        return

    if bundle_path.exists():
        try:
            _send_document(token, chat_id, bundle_path)
            print(f"  ✅ Telegram 已发送盘中数据包附件: {bundle_filename}")
        except Exception as e:
            print(f"  ⚠ Telegram 发送盘中数据包附件失败: {e}")


def run_notify_telegram_postmarket(date_str: str, flash_path=None) -> None:
    """推送盘后简报到 Telegram；有 postmarket_llm_bundle 时同时发附件。"""
    token = (os.environ.get("TELEGRAM_BOT_TOKEN") or "").strip()
    chat_id = (os.environ.get("TELEGRAM_CHAT_ID") or "").strip()
    if not token or not chat_id:
        print("  ⚠ 未配置 TELEGRAM_BOT_TOKEN 或 TELEGRAM_CHAT_ID，跳过 Telegram 盘后通知")
        return
    if flash_path is None:
        flash_path = OUTPUT_DIR / "postmarket" / f"盘后简报_{date_str}.md"
    path = Path(flash_path)
    if not path.exists():
        print(f"  ⚠ 盘后简报文件不存在: {path}")
        return
    text = path.read_text(encoding="utf-8")
    bundle_filename = f"{date_str}_postmarket_llm_bundle.md"
    bundle_path = OUTPUT_DIR / "ai_bundle" / bundle_filename
    if bundle_path.exists():
        text = text + "\n\n---\n📎 盘后喂模型包见下条附件。请下载附件，将附件与你的提示词一起发给 GPT 使用。"
    try:
        _send_message(token, chat_id, text)
        print("  ✅ Telegram 盘后简报已发送")
    except Exception as e:
        print(f"  ⚠ Telegram 盘后简报发送失败: {e}")
        return

    if bundle_path.exists():
        try:
            _send_document(token, chat_id, bundle_path)
            print(f"  ✅ Telegram 已发送盘后喂模型包附件: {bundle_filename}")
        except Exception as e:
            print(f"  ⚠ Telegram 发送盘后附件失败: {e}")


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--date", required=True)
    p.add_argument("--error", default="")
    args = p.parse_args()
    run_notify_telegram(args.date, success=not args.error, error_msg=args.error)
