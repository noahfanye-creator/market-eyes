#!/usr/bin/env python3
"""
读取 premarket.md 并推送到飞书。有 bundle 时同时上传为附件，方便手机端下载后直接给 GPT。
"""

import json
from pathlib import Path
import requests

from utils import OUTPUT_DIR

APP_ID = "cli_a9271f9ada78dcc2"
APP_SECRET = "7oLTQrRJI1DcTvgX0KitghcqsmXJeKJT"
RECEIVE_ID = "ou_c227153e4ea07569dc8bc07f9f7c23d7"
TIMEOUT = 15
FEISHU_IM_FILES = "https://open.feishu.cn/open-apis/im/v1/files"
FEISHU_IM_MESSAGES = "https://open.feishu.cn/open-apis/im/v1/messages?receive_id_type=open_id"


def _get_token():
    resp = requests.post(
        "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal",
        json={"app_id": APP_ID, "app_secret": APP_SECRET},
        timeout=TIMEOUT,
    )
    resp.raise_for_status()
    return resp.json().get("tenant_access_token", "")


def _send_message(token: str, text: str):
    resp = requests.post(
        FEISHU_IM_MESSAGES,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        json={
            "receive_id": RECEIVE_ID,
            "msg_type": "text",
            "content": json.dumps({"text": text}),
        },
        timeout=TIMEOUT,
    )
    resp.raise_for_status()
    return resp.json()


def _upload_file(token: str, file_name: str, content: bytes) -> dict:
    """上传文件到飞书 IM，返回 data（含 file_key），失败抛异常。"""
    resp = requests.post(
        FEISHU_IM_FILES,
        headers={"Authorization": f"Bearer {token}"},
        files={
            "file_type": (None, "stream"),
            "file_name": (None, file_name),
            "file": (file_name, content, "text/markdown; charset=utf-8"),
        },
        timeout=60,
    )
    resp.raise_for_status()
    data = resp.json()
    if data.get("code") != 0:
        raise RuntimeError(data.get("msg", "upload failed"))
    return data.get("data", {})


def _send_file_message(token: str, file_data: dict):
    """发送文件消息，file_data 为上传接口返回的 data。"""
    resp = requests.post(
        FEISHU_IM_MESSAGES,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        json={
            "receive_id": RECEIVE_ID,
            "msg_type": "file",
            "content": json.dumps(file_data),
        },
        timeout=TIMEOUT,
    )
    resp.raise_for_status()
    return resp.json()


def run_notify_feishu(
    date_str: str,
    success: bool = True,
    error_msg: str = "",
    bundle_filename: str = None,
) -> None:
    try:
        token = _get_token()
    except Exception as e:
        print(f"  ⚠ 飞书 Token 获取失败: {e}")
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
        _send_message(token, text)
        print(f"  ✅ 飞书通知已发送")
    except Exception as e:
        print(f"  ⚠ 飞书发送失败: {e}")
        return

    if success and bundle_filename:
        bundle_path = OUTPUT_DIR / "ai_bundle" / bundle_filename
        if not bundle_path.exists():
            print(f"  ⚠ 未找到 bundle 文件，跳过附件: {bundle_path}")
            return
        try:
            content = bundle_path.read_bytes()
            if not content:
                print(f"  ⚠ bundle 文件为空，跳过附件")
                return
            file_data = _upload_file(token, bundle_filename, content)
            _send_file_message(token, file_data)
            print(f"  ✅ 飞书已发送附件: {bundle_filename}")
        except Exception as e:
            print(f"  ⚠ 飞书发送附件失败: {e}")


def run_notify_feishu_intraday(date_str: str, flash_path=None) -> None:
    """推送盘中快报 md 到飞书；有 intraday_bundle 时同时发附件（与盘前一致）。flash_path 默认 output/intraday/盘中快报_{date_str}_10-00.md"""
    try:
        token = _get_token()
    except Exception as e:
        print(f"  ⚠ 飞书 Token 获取失败: {e}")
        return
    if flash_path is None:
        flash_path = OUTPUT_DIR / "intraday" / f"盘中快报_{date_str}_10-00.md"
    path = Path(flash_path) if not isinstance(flash_path, Path) else flash_path
    if not path.exists():
        print(f"  ⚠ 盘中快报文件不存在: {path}")
        return
    text = path.read_text(encoding="utf-8")
    bundle_filename = f"{date_str}_intraday_bundle.md"
    bundle_path = OUTPUT_DIR / "ai_bundle" / bundle_filename
    if bundle_path.exists():
        text = text + "\n\n---\n📎 AI 数据包见下条附件。请下载附件，将附件与你的提示词一起发给 GPT 使用。"
    try:
        _send_message(token, text)
        print("  ✅ 飞书盘中快报已发送")
    except Exception as e:
        print(f"  ⚠ 飞书发送失败: {e}")
        return

    if bundle_path.exists():
        try:
            content = bundle_path.read_bytes()
            if content:
                file_data = _upload_file(token, bundle_filename, content)
                _send_file_message(token, file_data)
                print(f"  ✅ 飞书已发送盘中数据包附件: {bundle_filename}")
            else:
                print(f"  ⚠ 盘中数据包为空，跳过附件")
        except Exception as e:
            print(f"  ⚠ 飞书发送盘中数据包附件失败: {e}")


def run_notify_feishu_postmarket(date_str: str, flash_path=None) -> None:
    """推送盘后简报到飞书；有 postmarket_llm_bundle 时同时发附件。"""
    try:
        token = _get_token()
    except Exception as e:
        print(f"  ⚠ 飞书 Token 获取失败: {e}")
        return
    if flash_path is None:
        flash_path = OUTPUT_DIR / "postmarket" / f"盘后简报_{date_str}.md"
    path = Path(flash_path) if not isinstance(flash_path, Path) else flash_path
    if not path.exists():
        print(f"  ⚠ 盘后简报文件不存在: {path}")
        return
    text = path.read_text(encoding="utf-8")
    bundle_filename = f"{date_str}_postmarket_llm_bundle.md"
    bundle_path = OUTPUT_DIR / "ai_bundle" / bundle_filename
    if bundle_path.exists():
        text = text + "\n\n---\n📎 盘后喂模型包见下条附件。请下载附件，将附件与你的提示词一起发给 GPT 使用。"
    try:
        _send_message(token, text)
        print("  ✅ 飞书盘后简报已发送")
    except Exception as e:
        print(f"  ⚠ 飞书盘后发送失败: {e}")
        return

    if bundle_path.exists():
        try:
            content = bundle_path.read_bytes()
            if content:
                file_data = _upload_file(token, bundle_filename, content)
                _send_file_message(token, file_data)
                print(f"  ✅ 飞书已发送盘后喂模型包附件: {bundle_filename}")
            else:
                print(f"  ⚠ 盘后喂模型包为空，跳过附件")
        except Exception as e:
            print(f"  ⚠ 飞书发送盘后附件失败: {e}")


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--date", required=True)
    p.add_argument("--error", default="")
    args = p.parse_args()
    run_notify_feishu(args.date, success=not args.error, error_msg=args.error)
