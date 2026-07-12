import os
import re
import time
from urllib.parse import urlencode

import requests
from dotenv import load_dotenv


load_dotenv()

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

if not BOT_TOKEN:
    raise RuntimeError(
        "Khong tim thay TELEGRAM_BOT_TOKEN trong file .env"
    )

API = f"https://api.telegram.org/bot{BOT_TOKEN}"


def send_message(chat_id, text):
    response = requests.post(
        f"{API}/sendMessage",
        json={
            "chat_id": chat_id,
            "text": text,
        },
        timeout=30,
    )
    response.raise_for_status()


def send_qr_photo(chat_id, qr_url, caption):
    keyboard = {
        "inline_keyboard": [
            [
                {
                    "text": "✅ Đã chuyển khoản",
                    "callback_data": "paid",
                }
            ]
        ]
    }

    response = requests.post(
        f"{API}/sendPhoto",
        json={
            "chat_id": chat_id,
            "photo": qr_url,
            "caption": caption,
            "reply_markup": keyboard,
        },
        timeout=30,
    )
    response.raise_for_status()


def parse_money(text):
    cleaned = (
        text.strip()
        .replace(",", "")
        .replace(".", "")
        .replace(" ", "")
    )

    if not cleaned.isdigit():
        raise ValueError("Số tiền không hợp lệ")

    amount = int(cleaned)

    if amount <= 0:
        raise ValueError("Số tiền phải lớn hơn 0")

    return amount


def create_qr_url(
    bank_id,
    account_number,
    account_name,
    amount,
    description,
):
    params = {
        "amount": amount,
        "addInfo": description,
        "accountName": account_name,
    }

    return (
        "https://img.vietqr.io/image/"
        f"{bank_id}-{account_number}-compact2.png?"
        f"{urlencode(params)}"
    )


def handle_callback(callback):
    callback_id = callback["id"]
    callback_data = callback.get("data", "")
    message = callback.get("message")

    requests.post(
        f"{API}/answerCallbackQuery",
        json={
            "callback_query_id": callback_id,
            "text": "Đã ghi nhận chuyển khoản",
        },
        timeout=30,
    ).raise_for_status()

    if callback_data != "paid" or not message:
        return

    chat_id = message["chat"]["id"]
    message_id = message["message_id"]
    caption = message.get("caption", "")

    qr_line = ""
    money_line = ""

    for line in caption.splitlines():
        if line.startswith("🏦 QR"):
            qr_line = line

        if "Số tiền:" in line:
            money_line = line

    requests.post(
        f"{API}/deleteMessage",
        json={
            "chat_id": chat_id,
            "message_id": message_id,
        },
        timeout=30,
    ).raise_for_status()

    send_message(
        chat_id,
        (
            "✅ Đã chuyển khoản\n\n"
            f"{qr_line}\n"
            f"{money_line}\n\n"
            "Mã QR đã được xóa."
        ),
    )


def help_text():
    return (
        "🏦 BOT TẠO MÃ QR NGÂN HÀNG\n\n"
        "Nhập theo mẫu:\n\n"
        "VIB\n"
        "843551555\n"
        "TRAN THI DUNG\n"
        "500000\n"
        "300000\n"
        "1200000\n\n"
        "Kết quả:\n"
        "QR 1 = 500,000 VND\n"
        "QR 2 = 300,000 VND\n"
        "QR 3 = 1,200,000 VND\n\n"
        "Mỗi dòng số tiền sẽ tạo một mã QR riêng."
    )


def handle_message(message):
    chat_id = message["chat"]["id"]
    text = message.get("text", "").strip()

    if text in ("/start", "/help"):
        send_message(chat_id, help_text())
        return

    lines = [
        line.strip()
        for line in text.splitlines()
        if line.strip()
    ]

    if len(lines) < 4:
        send_message(chat_id, help_text())
        return

    bank_id = re.sub(
        r"[^A-Za-z0-9]",
        "",
        lines[0],
    ).upper()

    account_number = re.sub(
        r"[^A-Za-z0-9]",
        "",
        lines[1],
    )

    account_name = lines[2].strip().upper()

    if not bank_id:
        send_message(
            chat_id,
            "Tên hoặc mã ngân hàng không hợp lệ.",
        )
        return

    if not 6 <= len(account_number) <= 19:
        send_message(
            chat_id,
            "Số tài khoản không hợp lệ.",
        )
        return

    if not account_name:
        send_message(
            chat_id,
            "Tên chủ tài khoản không hợp lệ.",
        )
        return

    amount_lines = lines[3:]

    if len(amount_lines) > 50:
        send_message(
            chat_id,
            "Chỉ được tạo tối đa 50 mã QR mỗi lần.",
        )
        return

    amounts = []

    for line_number, line in enumerate(
        amount_lines,
        start=4,
    ):
        try:
            amount = parse_money(line)
        except ValueError:
            send_message(
                chat_id,
                (
                    f"Số tiền tại dòng {line_number} "
                    f"không hợp lệ: {line}"
                ),
            )
            return

        amounts.append(amount)

    total_amount = sum(amounts)
    qr_count = len(amounts)

    send_message(
        chat_id,
        (
            f"✅ Đang tạo {qr_count} mã QR\n"
            f"💰 Tổng số tiền: {total_amount:,} VND\n"
            "Mỗi số tiền tương ứng với một mã QR."
        ),
    )

    for index, qr_amount in enumerate(
        amounts,
        start=1,
    ):
        description = "CHUYEN TIEN"

        qr_url = create_qr_url(
            bank_id=bank_id,
            account_number=account_number,
            account_name=account_name,
            amount=qr_amount,
            description=description,
        )

        caption = (
            f"🏦 QR {index}/{qr_count}\n"
            f"💵 Ngân hàng: {bank_id}\n"
            f"💳 Số tài khoản: {account_number}\n"
            f"👤 Chủ tài khoản: {account_name}\n"
            f"💰 Số tiền: {qr_amount:,} VND\n"
            f"📝 Nội dung: {description}"
        )

        send_qr_photo(
            chat_id,
            qr_url,
            caption,
        )

        time.sleep(0.5)


def run_bot():
    offset = 0

    print("Bot đang chạy...", flush=True)
    print("Nhấn Ctrl + C để dừng bot.", flush=True)

    while True:
        try:
            response = requests.get(
                f"{API}/getUpdates",
                params={
                    "offset": offset,
                    "timeout": 30,
                    "allowed_updates": [
                        "message",
                        "callback_query",
                    ],
                },
                timeout=35,
            )

            response.raise_for_status()
            data = response.json()

            if not data.get("ok"):
                print(
                    "Telegram API trả về lỗi:",
                    data,
                    flush=True,
                )
                time.sleep(3)
                continue

            for update in data.get("result", []):
                offset = update["update_id"] + 1

                print(
                    "Đã nhận update:",
                    update["update_id"],
                    flush=True,
                )

                if "message" in update:
                    handle_message(
                        update["message"]
                    )

                elif "callback_query" in update:
                    handle_callback(
                        update["callback_query"]
                    )

        except KeyboardInterrupt:
            print("\nĐã dừng bot.", flush=True)
            break

        except requests.RequestException as error:
            print(
                "Lỗi kết nối Telegram:",
                repr(error),
                flush=True,
            )
            time.sleep(3)

        except Exception as error:
            print(
                "Lỗi bot:",
                repr(error),
                flush=True,
            )
            time.sleep(3)


if __name__ == "__main__":
    run_bot()
