import os
import re
import time
from urllib.parse import urlencode

import requests
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

if not BOT_TOKEN:
    raise RuntimeError("Khong tim thay TELEGRAM_BOT_TOKEN trong file .env")

API = f"https://api.telegram.org/bot{BOT_TOKEN}"


def send_message(chat_id, text):
    requests.post(
        f"{API}/sendMessage",
        json={"chat_id": chat_id, "text": text},
        timeout=30,
    ).raise_for_status()


def send_qr_photo(chat_id, qr_url, caption):
    keyboard = {
        "inline_keyboard": [
            [{"text": "✅ Đã chuyển khoản", "callback_data": "paid"}]
        ]
    }

    requests.post(
        f"{API}/sendPhoto",
        json={
            "chat_id": chat_id,
            "photo": qr_url,
            "caption": caption,
            "reply_markup": keyboard,
        },
        timeout=30,
    ).raise_for_status()


def clean_text(text):
    text = text.upper().strip()
    text = re.sub(r"[^A-Z0-9 ]", "", text)
    text = re.sub(r"\s+", " ", text)
    return text[:50]


def create_qr_url(bank_id, account_number, account_name, amount, description):
    params = {
        "addInfo": description,
        "accountName": account_name,
    }

    if amount > 0:
        params["amount"] = amount

    return (
        f"https://img.vietqr.io/image/"
        f"{bank_id}-{account_number}-compact2.png?"
        f"{urlencode(params)}"
    )


def handle_callback(callback):
    callback_id = callback["id"]
    message = callback.get("message")

    requests.post(
        f"{API}/answerCallbackQuery",
        json={
            "callback_query_id": callback_id,
            "text": "Đã ghi nhận chuyển khoản",
        },
        timeout=30,
    )

    if message:
        chat_id = message["chat"]["id"]
        message_id = message["message_id"]

        requests.post(
            f"{API}/deleteMessage",
            json={
                "chat_id": chat_id,
                "message_id": message_id,
            },
            timeout=30,
        )

        send_message(chat_id, "✅ Đã chuyển khoản\nMã QR đã biến mất.")


def handle_message(message):
    chat_id = message["chat"]["id"]
    text = message.get("text", "").strip()

    if text in ["/start", "/help"]:
        send_message(
            chat_id,
            "🏦 BOT TẠO MÃ QR NGÂN HÀNG\n\n"
            "Gửi theo mẫu:\n\n"
            "TECHCOMBANK\n"
            "1863867979\n"
            "PHANVANCUONG\n\n"
            "Hoặc thêm số tiền:\n\n"
            "TECHCOMBANK\n"
            "1863867979\n"
            "PHANVANCUONG\n"
            "150000\n\n"
            "Nội dung mặc định: CHUYEN KHOAN"
        )
        return

    lines = [line.strip() for line in text.splitlines() if line.strip()]

    if len(lines) < 3:
        send_message(
            chat_id,
            "Gửi đúng mẫu:\n\n"
            "TECHCOMBANK\n"
            "1863867979\n"
            "PHANVANCUONG\n"
            "150000"
        )
        return

    bank_id = re.sub(r"[^A-Za-z0-9]", "", lines[0])
    account_number = re.sub(r"[^A-Za-z0-9]", "", lines[1])
    account_name = lines[2].upper()

    amount = 0
    if len(lines) >= 4:
        try:
            amount = int(lines[3].replace(",", "").replace(".", ""))
        except ValueError:
            send_message(chat_id, "Số tiền không hợp lệ.")
            return

    description = "CHUYEN KHOAN"

    if not bank_id:
        send_message(chat_id, "Tên ngân hàng không hợp lệ.")
        return

    if not (6 <= len(account_number) <= 19):
        send_message(chat_id, "Số tài khoản không hợp lệ.")
        return

    qr_url = create_qr_url(
        bank_id,
        account_number,
        account_name,
        amount,
        description,
    )

    caption = (
        f"💵 Ngân hàng: {bank_id.upper()}\n"
        f"💳 Số tài khoản: {account_number}\n"
        f"👤 Chủ tài khoản: {account_name}\n"
    )

    if amount > 0:
        caption += f"💰 Số tiền: {amount:,} VND\n"

    caption += f"📝 Nội dung: {description}"

    send_qr_photo(chat_id, qr_url, caption)


def run_bot():
    offset = 0

    print("Bot dang chay...")
    print("Nhan Ctrl + C de dung bot.")

    while True:
        try:
            response = requests.get(
                f"{API}/getUpdates",
                params={"offset": offset, "timeout": 30},
                timeout=40,
            )
            response.raise_for_status()

            data = response.json()

            for update in data.get("result", []):
                offset = update["update_id"] + 1

                if "message" in update:
                    handle_message(update["message"])

                if "callback_query" in update:
                    handle_callback(update["callback_query"])

        except KeyboardInterrupt:
            print("\nDa dung bot.")
            break

        except Exception as error:
            print("Loi:", error)
            time.sleep(3)


if __name__ == "__main__":
    run_bot()