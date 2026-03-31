import asyncio

import structlog
from telegram import Bot
from telegram.error import Forbidden, RetryAfter, TelegramError

from . import db
from .settings import Settings

log = structlog.get_logger()

MAX_RETRIES = 3
BACKOFF_BASE = 2.0


async def _send_with_retry(bot: Bot, chat_id: int, text: str) -> bool:
    """Send a message with exponential backoff retry. Returns True on success."""
    for attempt in range(MAX_RETRIES):
        try:
            await bot.send_message(
                chat_id=chat_id,
                text=text,
                parse_mode="MarkdownV2",
                disable_web_page_preview=True,
            )
            return True
        except Forbidden:
            # User blocked the bot — remove them
            log.warning("sender.user_blocked", chat_id=chat_id)
            db.remove_subscriber(chat_id)
            return False
        except RetryAfter as e:
            wait = e.retry_after
            log.warning("sender.rate_limited", chat_id=chat_id, wait=wait)
            await asyncio.sleep(wait)
        except TelegramError as e:
            log.warning(
                "sender.error", chat_id=chat_id, error=str(e), attempt=attempt + 1
            )
            if attempt < MAX_RETRIES - 1:
                await asyncio.sleep(BACKOFF_BASE ** (attempt + 1))

    log.error("sender.failed_after_retries", chat_id=chat_id)
    return False


async def send_digest(messages: list[str], settings: Settings) -> None:
    """Send digest messages to all subscribers (and optional channel)."""
    if settings.dry_run:
        for i, msg in enumerate(messages, 1):
            print(f"--- message {i}/{len(messages)} ---")
            print(msg)
            print()
        log.info("sender.dry_run_complete")
        return

    bot = Bot(token=settings.telegram_bot_token)

    # Collect all targets: subscribers + optional channel
    targets: list[int | str] = list(db.get_all_subscribers())
    if settings.telegram_channel_id:
        targets.append(settings.telegram_channel_id)

    if not targets:
        log.warning("sender.no_targets")
        return

    log.info("sender.sending", targets=len(targets), messages=len(messages))

    success = 0
    for target in targets:
        all_sent = True
        for msg in messages:
            if not await _send_with_retry(bot, target, msg):
                all_sent = False
                break
        if all_sent:
            success += 1

    log.info("sender.done", success=success, total=len(targets))
