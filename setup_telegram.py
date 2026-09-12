#!/usr/bin/env python
"""Find your Telegram chat ID and verify alerts work.

Usage:
  1. In Telegram, message @BotFather -> /newbot -> copy the token
  2. Put TELEGRAM_BOT_TOKEN=<token> in .env
  3. Send any message to your new bot in Telegram
  4. .venv/bin/python setup_telegram.py
"""
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

from bot.notify import TelegramNotifier, discover_chat_id

load_dotenv(Path(__file__).parent / ".env")


def main() -> int:
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        print("TELEGRAM_BOT_TOKEN not set in .env")
        print("Get one from @BotFather in Telegram (/newbot), then add it to .env")
        return 1

    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    if not chat_id:
        print("Looking for chats that have messaged your bot...\n")
        chats = discover_chat_id(token)
        if not chats:
            print("No messages found. Open Telegram, find your bot, send it any")
            print("message (e.g. /start), then run this script again.")
            return 1
        for cid, desc in chats:
            print(f"  chat_id={cid}   {desc}")
        chat_id = chats[0][0]
        print(f"\nAdd this to .env:\n  TELEGRAM_CHAT_ID={chat_id}\n")

    print(f"Sending a test alert to chat {chat_id}...")
    ok = TelegramNotifier(token, chat_id).send(
        "✅ <b>Groww bot connected</b>\nAlerts are working."
    )
    print("sent — check Telegram" if ok else "failed — see the error above")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
