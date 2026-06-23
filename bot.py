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


def split_amount(total, count):
    base = total // count
    remain = total % count

    result = []
    for i in range(count):
        if i < remain:
            result.append(base + 1)
        else:
            result.append(base)

    return result


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

caption = message.get("caption", "")

qr_line = ""
money_line = ""

for line in caption.split("\n"):
    if line.startswith("🏦 QR"):
        qr_line = line

    if line.startswith("💰"):
        money_line = line

send_message(
    chat_id,
    f"✅ Đã chuyển khoản\n\n{qr_line}\n{money_line}\n\nMã QR đã biến mất."
)


def handle_message(message):
    chat_id = message["chat"]["id"]
    text = message.get("text", "").strip()

    if text in ["/start", "/help"]:
        send_message(
            chat_id,
            "🏦 BOT TẠO MÃ QR NGÂN HÀNG\n\n"
            "Mẫu tạo 1 QR:\n\n"
            "TECHCOMBANK\n"
            "1863867979\n"
            "PHANVANCUONG\n"
            "150000\n\n"
            "Mẫu chia ra nhiều QR:\n\n"
            "TECHCOMBANK\n"
            "1863867979\n"
            "PHANVANCUONG\n"
            "1000000\n"
            "/4\n\n"
            "Bot sẽ chia 1,000,000 thành 4 mã QR."
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
            "150000\n\n"
            "Hoặc:\n\n"
            "TECHCOMBANK\n"
            "1863867979\n"
            "PHANVANCUONG\n"
            "1000000\n"
            "/4"
        )
        return

    bank_id = re.sub(r"[^A-Za-z0-9]", "", lines[0])
    account_number = re.sub(r"[^A-Za-z0-9]", "", lines[1])
    account_name = lines[2].upper()

    amount = 0
    qr_count = 1

    if len(lines) >= 4:
        try:
            amount = int(lines[3].replace(",", "").replace(".", ""))
        except ValueError:
            send_message(chat_id, "Số tiền không hợp lệ.")
            return

    if len(lines) >= 5:
        match = re.match(r"^/(\d+)$", lines[4])
        if not match:
            send_message(chat_id, "Dòng cuối phải là dạng /4, /5, /10...")
            return

        qr_count = int(match.group(1))

    description = "CHUYEN KHOAN"

    if not bank_id:
        send_message(chat_id, "Tên ngân hàng không hợp lệ.")
        return

    if not (6 <= len(account_number) <= 19):
        send_message(chat_id, "Số tài khoản không hợp lệ.")
        return

    if amount <= 0:
        send_message(chat_id, "Số tiền phải lớn hơn 0.")
        return

    if qr_count <= 0:
        send_message(chat_id, "Số lượng QR phải lớn hơn 0.")
        return

    if qr_count > 50:
        send_message(chat_id, "Chỉ cho tạo tối đa 50 mã QR mỗi lần.")
        return

    amounts = split_amount(amount, qr_count)

    if qr_count > 1:
        send_message(
            chat_id,
            f"✅ Đang tạo {qr_count} mã QR\n"
            f"💰 Tổng tiền: {amount:,} VND"
        )

    for index, qr_amount in enumerate(amounts, start=1):
        qr_description = description

        if qr_count > 1:
            qr_description = f"{description} {index}"

        qr_url = create_qr_url(
            bank_id,
            account_number,
            account_name,
            qr_amount,
            qr_description,
        )

        caption = (
            f"💵 Ngân hàng: {bank_id.upper()}\n"
            f"💳 Số tài khoản: {account_number}\n"
            f"👤 Chủ tài khoản: {account_name}\n"
            f"💰 Số tiền: {qr_amount:,} VND\n"
            f"📝 Nội dung: {qr_description}"
        )

        if qr_count > 1:
            caption = f"🏦 QR {index}/{qr_count}\n" + caption

        send_qr_photo(chat_id, qr_url, caption)
        time.sleep(0.5)


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
