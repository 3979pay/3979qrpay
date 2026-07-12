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


def parse_money(text):
    text = text.strip().replace(",", "").replace(".", "")
    if not text.isdigit():
        raise ValueError("money invalid")
    return int(text)


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


def create_qr_url(bank_id, account_number, account_name, amount, description):
    params = {
        "amount": amount,
        "addInfo": description,
        "accountName": account_name,
    }

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

    if not message:
        return

    chat_id = message["chat"]["id"]
    message_id = message["message_id"]
    caption = message.get("caption", "")

    qr_line = ""
    money_line = ""

    for line in caption.split("\n"):
        if "QR" in line:
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
    )

    send_message(
        chat_id,
        f"✅ Đã chuyển khoản\n\n{qr_line}\n{money_line}\n\nMã QR đã biến mất."
    )


def help_text():
    return (
        "🏦 BOT TẠO MÃ QR NGÂN HÀNG\n\n"
        "Mẫu dùng:\n\n"
        "VIB\n"
        "843551555\n"
        "TRAN THI DUNG\n"
        "2000000\n"
        "/1\n"
        "500000\n"
        "300000\n\n"
        "Giải thích:\n"
        "Tổng tiền: 2,000,000\n"
        "Đơn tự nhập: 500,000 và 300,000\n"
        "/1 = phần còn lại chia thành 1 QR\n\n"
        "Kết quả:\n"
        "QR 1 = 500,000\n"
        "QR 2 = 300,000\n"
        "QR 3 = 1,200,000"
    )


def handle_message(message):
    chat_id = message["chat"]["id"]
    text = message.get("text", "").strip()

    if text in ["/start", "/help"]:
        send_message(chat_id, help_text())
        return

    lines = [line.strip() for line in text.splitlines() if line.strip()]

    if len(lines) < 5:
        send_message(chat_id, help_text())
        return

    bank_id = re.sub(r"[^A-Za-z0-9]", "", lines[0])
    account_number = re.sub(r"[^A-Za-z0-9]", "", lines[1])
    account_name = lines[2].upper()

    if not bank_id:
        send_message(chat_id, "Tên ngân hàng không hợp lệ.")
        return

    if not (6 <= len(account_number) <= 19):
        send_message(chat_id, "Số tài khoản không hợp lệ.")
        return

    try:
        total_amount = parse_money(lines[3])
    except ValueError:
        send_message(chat_id, "Tổng số tiền không hợp lệ.")
        return

    match = re.match(r"^/(\d+)$", lines[4])
    if not match:
        send_message(chat_id, "Dòng thứ 5 phải là dạng /1, /2, /3...")
        return

    auto_count = int(match.group(1))

    if total_amount <= 0:
        send_message(chat_id, "Tổng tiền phải lớn hơn 0.")
        return

    if auto_count <= 0:
        send_message(chat_id, "Số QR tự chia phải lớn hơn 0.")
        return

    fixed_amounts = []

    for line in lines[5:]:
        try:
            money = parse_money(line)
        except ValueError:
            send_message(chat_id, f"Số tiền đặt riêng không hợp lệ: {line}")
            return

        if money <= 0:
            send_message(chat_id, f"Số tiền đặt riêng phải lớn hơn 0: {line}")
            return

        fixed_amounts.append(money)

    fixed_total = sum(fixed_amounts)
    remain_total = total_amount - fixed_total

    if remain_total < 0:
        send_message(chat_id, "Tổng tiền các đơn đặt riêng lớn hơn tổng tiền.")
        return

    auto_amounts = split_amount(remain_total, auto_count)
    amounts = fixed_amounts + auto_amounts
    qr_count = len(amounts)

    if qr_count > 50:
        send_message(chat_id, "Chỉ cho tạo tối đa 50 mã QR mỗi lần.")
        return

    send_message(
        chat_id,
        f"✅ Đang tạo {qr_count} mã QR\n"
        f"💰 Tổng tiền: {total_amount:,} VND\n"
        f"✍️ Đơn tự nhập: {len(fixed_amounts)}\n"
        f"🤖 Đơn bot tự tính: {auto_count}\n"
        f"💵 Còn lại bot chia: {remain_total:,} VND"
    )

    for index, qr_amount in enumerate(amounts, start=1):
        description = "CHUYEN TIEN"

        qr_url = create_qr_url(
            bank_id,
            account_number,
            account_name,
            qr_amount,
            description,
        )

        caption = (
            f"🏦 QR {index}/{qr_count}\n"
            f"💵 Ngân hàng: {bank_id.upper()}\n"
            f"💳 Số tài khoản: {account_number}\n"
            f"👤 Chủ tài khoản: {account_name}\n"
            f"💰 Số tiền: {qr_amount:,} VND\n"
            f"📝 Nội dung: {description}"
        )

        send_qr_photo(chat_id, qr_url, caption)
        time.sleep(0.5)


def run_bot():
    offset = 0

while True:
    try:
        response = requests.get(
            f"{API}/getUpdates",
            params={"offset": offset, "timeout": 30},
            timeout=35,
        )
        response.raise_for_status()

        data = response.json()
        print("Phản hồi getUpdates:", data, flush=True)

        for update in data.get("result", []):
            print("Đã nhận update:", update, flush=True)
            offset = update["update_id"] + 1

            if "message" in update:
                handle_message(update["message"])

    except Exception as e:
        print("Lỗi bot:", repr(e), flush=True)
        time.sleep(3)
