import os
import sqlite3
from datetime import datetime, timezone

import structlog

log = structlog.get_logger()

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "subscribers.db")


def _get_connection() -> sqlite3.Connection:
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    return sqlite3.connect(DB_PATH)


def init_db() -> None:
    with _get_connection() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS subscribers (
                chat_id INTEGER PRIMARY KEY,
                subscribed_at TEXT NOT NULL
            )
            """
        )
    log.info("db.initialized", path=DB_PATH)


def add_subscriber(chat_id: int) -> bool:
    """Add a subscriber. Returns True if new, False if already exists."""
    try:
        with _get_connection() as conn:
            conn.execute(
                "INSERT INTO subscribers (chat_id, subscribed_at) VALUES (?, ?)",
                (chat_id, datetime.now(timezone.utc).isoformat()),
            )
        log.info("db.subscriber_added", chat_id=chat_id)
        return True
    except sqlite3.IntegrityError:
        return False


def remove_subscriber(chat_id: int) -> bool:
    """Remove a subscriber. Returns True if removed, False if not found."""
    with _get_connection() as conn:
        cursor = conn.execute("DELETE FROM subscribers WHERE chat_id = ?", (chat_id,))
    removed = cursor.rowcount > 0
    if removed:
        log.info("db.subscriber_removed", chat_id=chat_id)
    return removed


def get_all_subscribers() -> list[int]:
    with _get_connection() as conn:
        rows = conn.execute("SELECT chat_id FROM subscribers").fetchall()
    return [row[0] for row in rows]


def subscriber_count() -> int:
    with _get_connection() as conn:
        row = conn.execute("SELECT COUNT(*) FROM subscribers").fetchone()
    return row[0]
