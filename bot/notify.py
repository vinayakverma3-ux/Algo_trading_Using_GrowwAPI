"""Alert delivery. Telegram in production, console when unconfigured."""
import logging
import os

import requests

log = logging.getLogger("bot.notify")

API = "https://api.telegram.org/bot{token}/{method}"


class ConsoleNotifier:
    """Fallback when no token is set — alerts still appear in the log."""

    enabled = False

    def send(self, text: str) -> bool:
        log.info("[alert] %s", text.replace("\n", " | "))
        return True


class TelegramNotifier:
    def __init__(self, token: str, chat_id: str, timeout: int = 10):
        self.token, self.chat_id, self.timeout = token, chat_id, timeout
        self.enabled = True

    def send(self, text: str) -> bool:
        """Post a message. Never raises — an alert failure must not kill the bot."""
        try:
            r = requests.post(
                API.format(token=self.token, method="sendMessage"),
                json={"chat_id": self.chat_id, "text": text,
                      "parse_mode": "HTML", "disable_web_page_preview": True},
                timeout=self.timeout,
            )
            if not r.ok:
                log.error("telegram send failed: %s %s", r.status_code, r.text[:200])
                return False
            return True
        except Exception as exc:
            log.error("telegram unreachable: %s", exc)
            return False


def build() -> "ConsoleNotifier | TelegramNotifier":
    """Construct from env; falls back to console if not configured."""
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    if token and chat_id:
        return TelegramNotifier(token, chat_id)
    log.warning("TELEGRAM_BOT_TOKEN/TELEGRAM_CHAT_ID unset — alerts go to the log only")
    return ConsoleNotifier()


def discover_chat_id(token: str) -> list[tuple[str, str]]:
    """Return (chat_id, description) for recent chats. Message the bot first."""
    r = requests.get(API.format(token=token, method="getUpdates"), timeout=10)
    r.raise_for_status()
    seen = {}
    for upd in r.json().get("result", []):
        msg = upd.get("message") or upd.get("channel_post") or {}
        chat = msg.get("chat")
        if chat:
            name = chat.get("username") or chat.get("title") or chat.get("first_name") or "?"
            seen[str(chat["id"])] = f"{chat.get('type')} · {name}"
    return sorted(seen.items())
