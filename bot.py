import asyncio
import logging
import re
import secrets
import sqlite3
import string
import unicodedata
from datetime import datetime

from telegram import CopyTextButton, InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ChatType, ParseMode
from telegram.error import BadRequest, Forbidden
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

# =========================
# CHỈ SỬA 3 DÒNG BÊN DƯỚI
# =========================
BOT_TOKEN = "8980164536:AAHJEyABIme8yNEfiZ4JPO-Tq5GFrOSSFxM"
ADMIN_CHAT_ID = 0
OWNER_USER_ID = 0
# =========================

DATABASE_FILE = "matkhau.db"
THOI_GIAN_XOA_THONG_BAO = 10

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


def init_db() -> None:
    with sqlite3.connect(DATABASE_FILE) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS tai_khoan_gan_nhat (
                user_id INTEGER PRIMARY KEY,
                tai_khoan TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS mat_khau_cho (
                user_id INTEGER PRIMARY KEY,
                loai TEXT NOT NULL,
                tai_khoan TEXT NOT NULL,
                mat_khau TEXT NOT NULL
            )
            """
        )


def remove_accents(text: str) -> str:
    text = unicodedata.normalize("NFD", text)
    text = "".join(ch for ch in text if unicodedata.category(ch) != "Mn")
    return text.replace("đ", "d").replace("Đ", "D")


def normalize_text(text: str) -> str:
    text = remove_accents(text.lower())
    text = re.sub(r"[，,;|]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def save_last_account(user_id: int, account: str) -> None:
    with sqlite3.connect(DATABASE_FILE) as conn:
        conn.execute(
            "INSERT OR REPLACE INTO tai_khoan_gan_nhat (user_id, tai_khoan) VALUES (?, ?)",
            (user_id, account),
        )


def get_last_account(user_id: int) -> str | None:
    with sqlite3.connect(DATABASE_FILE) as conn:
        row = conn.execute(
            "SELECT tai_khoan FROM tai_khoan_gan_nhat WHERE user_id = ?",
            (user_id,),
        ).fetchone()
    return row[0] if row else None


def save_pending(user_id: int, loai: str, account: str, password: str) -> None:
    with sqlite3.connect(DATABASE_FILE) as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO mat_khau_cho (user_id, loai, tai_khoan, mat_khau)
            VALUES (?, ?, ?, ?)
            """,
            (user_id, loai, account, password),
        )


def get_pending(user_id: int):
    with sqlite3.connect(DATABASE_FILE) as conn:
        return conn.execute(
            "SELECT loai, tai_khoan, mat_khau FROM mat_khau_cho WHERE user_id = ?",
            (user_id,),
        ).fetchone()


def delete_pending(user_id: int) -> None:
    with sqlite3.connect(DATABASE_FILE) as conn:
        conn.execute("DELETE FROM mat_khau_cho WHERE user_id = ?", (user_id,))


def create_login_password() -> str:
    uppercase = secrets.choice(string.ascii_uppercase)
    lowercase = secrets.choice(string.ascii_lowercase)
    digits = "".join(secrets.choice(string.digits) for _ in range(8))
    return uppercase + lowercase + digits


def create_withdraw_password() -> str:
    return "".join(secrets.choice(string.digits) for _ in range(4))


LOGIN_KEYWORDS = [
    "mk dn",
    "mkdn",
    "mk dang nhap",
    "mat khau dang nhap",
    "xin mk dang nhap",
    "xin mat khau dang nhap",
    "xin mk dn",
    "dang nhap",
    "login",
]

WITHDRAW_KEYWORDS = [
    "mk rt",
    "mkrt",
    "mat khau rt",
    "mk rut tien",
    "mat khau rut tien",
    "xin mk rt",
    "xin mat khau rut tien",
    "rut tien",
    "withdraw",
]


def find_keyword(text: str, keywords: list[str]) -> str | None:
    for keyword in sorted(keywords, key=len, reverse=True):
        if re.search(rf"(?<!\w){re.escape(keyword)}(?!\w)", text):
            return keyword
    return None


def extract_account(original_text: str, keyword: str) -> str | None:
    text = normalize_text(original_text)
    remaining = re.sub(
        rf"(?<!\w){re.escape(keyword)}(?!\w)",
        " ",
        text,
        count=1,
    )

    remaining = re.sub(
        r"\b(xin|cho|em|anh|chi|oi|voi|giup|cap|doi|lay|can|ho|minh|admin|onbet)\b",
        " ",
        remaining,
    )
    remaining = re.sub(r"[:=\-]+", " ", remaining)
    remaining = re.sub(r"\s+", " ", remaining).strip()

    if not remaining:
        return None

    candidates = remaining.split()
    for item in candidates:
        if re.fullmatch(r"[a-z0-9_.@\-]{2,64}", item, flags=re.IGNORECASE):
            return item

    return None


def detect_request(text: str):
    normalized = normalize_text(text)

    withdraw_keyword = find_keyword(normalized, WITHDRAW_KEYWORDS)
    if withdraw_keyword:
        return "rut_tien", extract_account(text, withdraw_keyword)

    login_keyword = find_keyword(normalized, LOGIN_KEYWORDS)
    if login_keyword:
        return "dang_nhap", extract_account(text, login_keyword)

    return None, None


def is_done(text: str) -> bool:
    normalized = text.strip().upper().replace(" ", "")
    return normalized in {"DONE", "DONE✅", "✅"}


def copy_keyboard(password: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [[
            InlineKeyboardButton(
                text="📋 Sao chép mật khẩu",
                copy_text=CopyTextButton(text=password),
            )
        ]]
    )


async def send_to_user(
    context: ContextTypes.DEFAULT_TYPE,
    user_id: int,
    request_type: str,
    account: str,
    password: str,
) -> None:
    if request_type == "dang_nhap":
        title = "🔐 Thông tin đăng nhập"
        password_label = "Mật khẩu đăng nhập"
    else:
        title = "💰 Thông tin rút tiền"
        password_label = "Mật khẩu rút tiền"

    await context.bot.send_message(
        chat_id=user_id,
        text=(
            f"{title}\n\n"
            f"Tài khoản: <code>{account}</code>\n"
            f"{password_label}: <code>{password}</code>"
        ),
        parse_mode=ParseMode.HTML,
        reply_markup=copy_keyboard(password),
    )


async def send_admin_copy(
    context: ContextTypes.DEFAULT_TYPE,
    request_type: str,
    account: str,
    password: str,
    recipient,
    confirmer,
    group_name: str,
) -> None:
    if ADMIN_CHAT_ID == 0:
        return

    type_name = (
        "Mật khẩu đăng nhập"
        if request_type == "dang_nhap"
        else "Mật khẩu rút tiền"
    )

    await context.bot.send_message(
        chat_id=ADMIN_CHAT_ID,
        text=(
            "📋 <b>BẢN SAO ĐÃ GỬI</b>\n\n"
            f"Loại: <b>{type_name}</b>\n"
            f"Tài khoản: <code>{account}</code>\n"
            f"Mật khẩu: <code>{password}</code>\n\n"
            f"Người nhận: {recipient.full_name}\n"
            f"User ID: <code>{recipient.id}</code>\n"
            f"Người xác nhận: {confirmer.full_name}\n"
            f"Nhóm: {group_name}\n"
            f"Thời gian: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}"
        ),
        parse_mode=ParseMode.HTML,
        reply_markup=copy_keyboard(password),
    )


async def delete_after(
    context: ContextTypes.DEFAULT_TYPE,
    chat_id: int,
    message_id: int,
) -> None:
    await asyncio.sleep(THOI_GIAN_XOA_THONG_BAO)
    try:
        await context.bot.delete_message(chat_id=chat_id, message_id=message_id)
    except (BadRequest, Forbidden):
        pass


async def can_use_done(
    context: ContextTypes.DEFAULT_TYPE,
    chat_id: int,
    user_id: int,
) -> bool:
    if OWNER_USER_ID != 0:
        return user_id == OWNER_USER_ID

    try:
        member = await context.bot.get_chat_member(chat_id, user_id)
        return member.status in {"administrator", "creator"}
    except Exception:
        return False


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    chat = update.effective_chat
    message = update.effective_message

    if not user or not chat or not message:
        return

    if chat.type != ChatType.PRIVATE:
        await message.reply_text("Hãy mở chat riêng với bot rồi bấm Start.")
        return

    pending = get_pending(user.id)

    if pending:
        request_type, account, password = pending
        await send_to_user(
            context,
            user.id,
            request_type,
            account,
            password,
        )
        delete_pending(user.id)
        return

    await message.reply_text(
        "✅ Bạn đã kết nối với bot.\n\n"
        f"Telegram ID của bạn: <code>{user.id}</code>\n\n"
        "Bot chỉ xử lý khi admin reply DONE vào tin nhắn yêu cầu.",
        parse_mode=ParseMode.HTML,
    )


async def myid(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    message = update.effective_message

    if user and message:
        await message.reply_text(
            f"Telegram ID của bạn: <code>{user.id}</code>",
            parse_mode=ParseMode.HTML,
        )


async def handle_done(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    message = update.effective_message
    admin = update.effective_user
    chat = update.effective_chat

    if not message or not admin or not chat:
        return

    if chat.type not in (ChatType.GROUP, ChatType.SUPERGROUP):
        return

    if not is_done(message.text or ""):
        return

    if not message.reply_to_message:
        return

    if not await can_use_done(context, chat.id, admin.id):
        return

    original_message = message.reply_to_message
    original_user = original_message.from_user

    if not original_user or original_user.is_bot:
        return

    request_type, account = detect_request(original_message.text or "")

    if request_type is None:
        await message.reply_text("⚠️ Bot không nhận diện được loại mật khẩu.")
        return

    if not account:
        account = get_last_account(original_user.id)

    if not account:
        await message.reply_text(
            "⚠️ Không tìm thấy tên tài khoản trong tin nhắn."
        )
        return

    save_last_account(original_user.id, account)

    if request_type == "dang_nhap":
        password = create_login_password()
        group_notice = "✅ Đã gửi mật khẩu đăng nhập vào tin nhắn riêng."
    else:
        password = create_withdraw_password()
        group_notice = "✅ Đã gửi mật khẩu rút tiền vào tin nhắn riêng."

    try:
        await send_to_user(
            context,
            original_user.id,
            request_type,
            account,
            password,
        )

        await send_admin_copy(
            context,
            request_type,
            account,
            password,
            original_user,
            admin,
            chat.title or "Không rõ",
        )

        reply = await original_message.reply_text(
            f"{original_user.mention_html()} {group_notice}",
            parse_mode=ParseMode.HTML,
        )

        asyncio.create_task(
            delete_after(context, reply.chat_id, reply.message_id)
        )

    except Forbidden:
        save_pending(
            original_user.id,
            request_type,
            account,
            password,
        )

        bot_info = await context.bot.get_me()
        open_bot_url = f"https://t.me/{bot_info.username}?start=nhanmatkhau"

        keyboard = InlineKeyboardMarkup(
            [[InlineKeyboardButton(
                text="🔐 Nhận mật khẩu riêng",
                url=open_bot_url,
            )]]
        )

        await original_message.reply_text(
            f"{original_user.mention_html()} hãy nhấn nút bên dưới rồi bấm Start.",
            parse_mode=ParseMode.HTML,
            reply_markup=keyboard,
        )


def main() -> None:
    if BOT_TOKEN == "DAN_TOKEN_MOI_VAO_DAY":
        raise ValueError("Bạn chưa dán BOT_TOKEN vào file bot.py")

    init_db()

    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("myid", myid))
    app.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            handle_done,
        )
    )

    print("Bot đang chạy...")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
