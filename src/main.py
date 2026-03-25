import argparse
import asyncio

import structlog
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

from . import db, setup_logging
from .config import load_config
from .curator import curate
from .fetcher import fetch_all_feeds
from .formatter import format_digest
from .preprocessor import preprocess
from .sender import send_digest
from .settings import Settings

log = structlog.get_logger()


# ── Pipeline ──────────────────────────────────────────────


async def run_pipeline(settings: Settings, fetch_only: bool = False) -> None:
    """Run the full news digest pipeline."""
    log.info("pipeline.start")

    # 1. Fetch
    feeds = settings.get_feeds()
    items = await fetch_all_feeds(feeds)
    log.info("pipeline.fetched", count=len(items))

    if not items:
        log.warning("pipeline.no_items")
        return

    # 2. Preprocess
    processed = preprocess(items, settings)
    log.info("pipeline.preprocessed", count=len(processed))

    if fetch_only:
        for item in processed:
            print(f"[{item.source}] {item.title}")
        return

    # 3. Curate
    digest = await curate(processed, settings)
    log.info("pipeline.curated", stories=len(digest.stories))

    # 4. Format
    messages = format_digest(digest)

    # 5. Send
    await send_digest(messages, settings)
    log.info("pipeline.complete")


# ── Telegram Command Handlers ─────────────────────────────


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /start — subscribe to daily digest."""
    chat_id = update.effective_chat.id
    is_new = db.add_subscriber(chat_id)

    if is_new:
        await update.message.reply_text(
            "🐦 Gurr gurr! Ich bin Oskar, deine Nachrichtenbrieftaube!\n\n"
            "Ab jetzt bringe ich dir jeden Morgen die wichtigsten Nachrichten. "
            "Schreibe /stop um dich abzumelden."
        )
    else:
        await update.message.reply_text(
            "🐦 Du bist bereits angemeldet! "
            "Jeden Morgen flattern die Nachrichten zu dir."
        )


async def cmd_stop(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /stop — unsubscribe from daily digest."""
    chat_id = update.effective_chat.id
    removed = db.remove_subscriber(chat_id)

    if removed:
        await update.message.reply_text(
            "🐦 Schade! Oskar fliegt davon... "
            "Schreibe /start wenn du mich vermisst!"
        )
    else:
        await update.message.reply_text("🐦 Du warst gar nicht angemeldet!")


# ── Scheduler callback ────────────────────────────────────


def _make_scheduled_job(settings: Settings):
    """Create a scheduler-compatible callback."""

    async def job():
        try:
            await run_pipeline(settings)
        except Exception:
            log.exception("scheduler.job_failed")

    return job


# ── Entry Point ───────────────────────────────────────────


def main() -> None:
    parser = argparse.ArgumentParser(description="Oskar the News Pigeon 🐦")
    parser.add_argument("--dry-run", action="store_true", help="Print digest, don't send")
    parser.add_argument("--now", action="store_true", help="Run pipeline once immediately")
    parser.add_argument("--fetch-only", action="store_true", help="Only fetch and show items")
    args = parser.parse_args()

    # Load config and setup logging
    setup_logging()
    settings = load_config()
    setup_logging(settings.log_level)

    if args.dry_run:
        settings = settings.model_copy(update={"dry_run": True})

    # fetch-only needs only FEEDS
    if args.fetch_only:
        asyncio.run(run_pipeline(settings, fetch_only=True))
        return

    # Everything else needs API keys
    missing = []
    if not settings.anthropic_api_key:
        missing.append("ANTHROPIC_API_KEY")
    if not settings.telegram_bot_token:
        missing.append("TELEGRAM_BOT_TOKEN")
    if missing:
        log.error("config.missing_required", vars=missing)
        raise SystemExit(1)

    # Init subscriber DB
    db.init_db()

    # One-shot mode
    if args.now:
        asyncio.run(run_pipeline(settings))
        return

    # Scheduled mode with bot polling
    log.info("main.starting", mode="scheduled", cron=settings.schedule_cron)

    # Python 3.12+ / 3.14 no longer auto-creates an event loop
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    # Build the telegram Application
    app = Application.builder().token(settings.telegram_bot_token).build()
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("stop", cmd_stop))

    # Setup APScheduler
    scheduler = AsyncIOScheduler()
    scheduler.add_job(
        _make_scheduled_job(settings),
        trigger=CronTrigger.from_crontab(settings.schedule_cron),
        id="daily_digest",
        name="Daily News Digest",
    )

    # Run bot with scheduler
    async def post_init(application: Application) -> None:
        scheduler.start()
        subs = db.subscriber_count()
        log.info("main.ready", subscribers=subs, cron=settings.schedule_cron)

    async def post_shutdown(application: Application) -> None:
        scheduler.shutdown()

    app.post_init = post_init
    app.post_shutdown = post_shutdown
    app.run_polling()


if __name__ == "__main__":
    main()
