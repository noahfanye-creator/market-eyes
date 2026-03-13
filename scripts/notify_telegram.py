import requests
import sys

TELEGRAM_BOT_TOKEN = "8692057353:AAFpIi9M1PJrA0R8Bnz-rhIuM6IpC3QswG8"
TELEGRAM_CHAT_ID = "5920715689"

def send_message(text, parse_mode="Markdown"):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    # Telegram单条消息限制4096字符，超过则分段发送
    max_len = 4000
    chunks = [text[i:i+max_len] for i in range(0, len(text), max_len)]
    for chunk in chunks:
        resp = requests.post(url, json={
            "chat_id": TELEGRAM_CHAT_ID,
            "text": chunk,
            "parse_mode": parse_mode
        })
        if not resp.ok:
            print(f"发送失败: {resp.text}")
            return False
    return True

def send_report(report_path, title):
    try:
        content = open(report_path, encoding="utf-8").read()
        header = f"{title}\n\n"
        send_message(header + content, parse_mode="")
        print(f"✅ 已推送: {title}")
    except Exception as e:
        print(f"❌ 推送失败: {e}")

if __name__ == "__main__":
    send_message("✅ Telegram推送测试成功！Felix的MaxClaw Bot已就绪。")


def run_notify_telegram(date, success=True, error_msg=None, bundle_filename=None):
    if not success:
        send_message(f"❌ {date} 盘前报告生成失败\n错误：{error_msg}")
        return
    report_path = f"/home/node/market-eyes/output/report/{date}_premarket_report.md"
    send_report(report_path, f"📈 {date} 盘前报告")

def run_notify_postmarket(date, success=True, error_msg=None):
    if not success:
        send_message(f"❌ {date} 复盘报告生成失败\n错误：{error_msg}")
        return
    report_path = f"/home/node/market-eyes/output/postmarket_report/{date}_postmarket_report.md"
    send_report(report_path, f"📊 {date} 复盘报告")
