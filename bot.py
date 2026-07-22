#!/usr/bin/env python3
"""A small, dependency-free Telegram calculator bot."""

from __future__ import annotations

import ast
import json
import math
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request


MAX_EXPRESSION_LENGTH = 200
MAX_AST_NODES = 60
MAX_ABSOLUTE_VALUE = 1e100
MAX_EXPONENT = 100


class CalculatorError(ValueError):
    """Raised when an expression cannot be safely calculated."""


def _normalize(expression: str) -> str:
    expression = expression.strip()
    expression = expression.replace("×", "*").replace("÷", "/").replace("−", "-")
    expression = re.sub(r"(?<=\d)\s*[xX]\s*(?=[\d(])", "*", expression)
    # Accept conventional thousands separators, e.g. 1,000 or 12,345.67.
    expression = re.sub(r"(?<=\d),(?=\d{3}(?:\D|$))", "", expression)
    expression = expression.replace("^", "**")
    return expression


def _check_number(value: int | float) -> int | float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise CalculatorError("Chỉ hỗ trợ số thực.")
    if isinstance(value, float) and not math.isfinite(value):
        raise CalculatorError("Kết quả không hữu hạn.")
    if abs(value) > MAX_ABSOLUTE_VALUE:
        raise CalculatorError("Kết quả quá lớn.")
    return value


def _evaluate(node: ast.AST) -> int | float:
    if isinstance(node, ast.Expression):
        return _evaluate(node.body)

    if isinstance(node, ast.Constant):
        return _check_number(node.value)

    if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
        value = _evaluate(node.operand)
        return _check_number(value if isinstance(node.op, ast.UAdd) else -value)

    if isinstance(node, ast.BinOp):
        left = _evaluate(node.left)
        right = _evaluate(node.right)

        try:
            if isinstance(node.op, ast.Add):
                result = left + right
            elif isinstance(node.op, ast.Sub):
                result = left - right
            elif isinstance(node.op, ast.Mult):
                result = left * right
            elif isinstance(node.op, ast.Div):
                result = left / right
            elif isinstance(node.op, ast.FloorDiv):
                result = left // right
            elif isinstance(node.op, ast.Mod):
                result = left % right
            elif isinstance(node.op, ast.Pow):
                if abs(right) > MAX_EXPONENT:
                    raise CalculatorError("Số mũ quá lớn.")
                result = left**right
            else:
                raise CalculatorError("Phép toán không được hỗ trợ.")
        except ZeroDivisionError as exc:
            raise CalculatorError("Không thể chia cho 0.") from exc
        except (OverflowError, ValueError) as exc:
            raise CalculatorError("Không thể tính biểu thức này.") from exc

        return _check_number(result)

    raise CalculatorError("Biểu thức chứa nội dung không được hỗ trợ.")


def calculate(expression: str) -> int | float:
    """Safely calculate a basic arithmetic expression."""
    expression = _normalize(expression)
    if not expression:
        raise CalculatorError("Hãy nhập một phép tính, ví dụ: 125*8")
    if len(expression) > MAX_EXPRESSION_LENGTH:
        raise CalculatorError("Biểu thức quá dài.")

    try:
        tree = ast.parse(expression, mode="eval")
    except (SyntaxError, ValueError) as exc:
        raise CalculatorError("Biểu thức không hợp lệ.") from exc

    if sum(1 for _ in ast.walk(tree)) > MAX_AST_NODES:
        raise CalculatorError("Biểu thức quá phức tạp.")
    return _evaluate(tree)


def format_result(value: int | float) -> str:
    if isinstance(value, int):
        return format(value, ",")
    if value == 0:
        return "0"
    return format(value, ",.15g")


class TelegramBot:
    def __init__(self, token: str) -> None:
        self.api_base = f"https://api.telegram.org/bot{token}/"
        self.offset: int | None = None

    def call(self, method: str, data: dict[str, object], timeout: int = 70) -> object:
        encoded = urllib.parse.urlencode(data).encode("utf-8")
        request = urllib.request.Request(self.api_base + method, data=encoded)
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                payload = json.load(response)
        except urllib.error.HTTPError as exc:
            try:
                detail = json.load(exc)["description"]
            except Exception:
                detail = str(exc)
            raise RuntimeError(f"Telegram API: {detail}") from exc

        if not payload.get("ok"):
            raise RuntimeError(f"Telegram API: {payload.get('description', 'lỗi không xác định')}")
        return payload["result"]

    def send(self, chat_id: int, text: str) -> None:
        self.call("sendMessage", {"chat_id": chat_id, "text": text})

    def handle_message(self, message: dict[str, object]) -> None:
        text = message.get("text")
        chat = message.get("chat")
        if not isinstance(text, str) or not isinstance(chat, dict):
            return
        chat_id = chat.get("id")
        if not isinstance(chat_id, int):
            return

        command = text.split(maxsplit=1)[0].split("@", 1)[0].lower()
        if command == "/start":
            self.send(
                chat_id,
                "Xin chào! Gửi phép tính cho mình, ví dụ:\n"
                "125*8\n"
                "(25+5)/3\n"
                "2^10\n\n"
                "Dùng /help để xem các phép toán hỗ trợ.",
            )
            return
        if command == "/help":
            self.send(
                chat_id,
                "Các phép toán: +  -  *  /  //  %  ^  ** và ngoặc ().\n"
                "Bạn cũng có thể dùng ×, ÷ hoặc viết /calc 125*8.",
            )
            return

        expression = text
        if command == "/calc":
            parts = text.split(maxsplit=1)
            expression = parts[1] if len(parts) == 2 else ""
        elif command.startswith("/"):
            self.send(chat_id, "Lệnh chưa được hỗ trợ. Gửi /help để xem hướng dẫn.")
            return

        try:
            result = format_result(calculate(expression))
            self.send(chat_id, f"= {result}")
        except CalculatorError as exc:
            self.send(chat_id, f"⚠️ {exc}")

    def run(self) -> None:
        identity = self.call("getMe", {})
        username = identity.get("username", "bot") if isinstance(identity, dict) else "bot"
        print(f"Bot @{username} đang chạy. Nhấn Ctrl+C để dừng.", flush=True)

        while True:
            data: dict[str, object] = {
                "timeout": 50,
                "allowed_updates": json.dumps(["message"]),
            }
            if self.offset is not None:
                data["offset"] = self.offset

            try:
                updates = self.call("getUpdates", data, timeout=60)
                if not isinstance(updates, list):
                    continue
                for update in updates:
                    if not isinstance(update, dict):
                        continue
                    update_id = update.get("update_id")
                    if isinstance(update_id, int):
                        self.offset = update_id + 1
                    message = update.get("message")
                    if isinstance(message, dict):
                        self.handle_message(message)
            except (urllib.error.URLError, TimeoutError, RuntimeError) as exc:
                print(f"Mất kết nối: {exc}. Thử lại sau 3 giây...", file=sys.stderr, flush=True)
                time.sleep(3)


def main() -> None:
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    if not token:
        print(
            "Thiếu TELEGRAM_BOT_TOKEN. Xem hướng dẫn trong README.md.",
            file=sys.stderr,
        )
        raise SystemExit(1)
    try:
        TelegramBot(token).run()
    except KeyboardInterrupt:
        print("\nĐã dừng bot.")


if __name__ == "__main__":
    main()
