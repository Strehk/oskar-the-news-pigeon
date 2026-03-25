import asyncio
from calendar import timegm
from datetime import datetime, timezone

import feedparser
import httpx
import structlog

from .models import FeedItem, FeedSource

log = structlog.get_logger()

FETCH_TIMEOUT = 15.0


def _parse_date(entry: dict) -> datetime:
    """Extract publication date from a feedparser entry."""
    for field in ("published_parsed", "updated_parsed"):
        parsed = entry.get(field)
        if parsed:
            try:
                return datetime.fromtimestamp(timegm(parsed), tz=timezone.utc)
            except (ValueError, OverflowError):
                continue
    return datetime.now(timezone.utc)


def _parse_feed(feed_data: str, source: FeedSource) -> list[FeedItem]:
    """Parse raw feed XML into FeedItem objects."""
    parsed = feedparser.parse(feed_data)
    items = []
    for entry in parsed.entries:
        title = entry.get("title", "").strip()
        if not title:
            continue
        items.append(
            FeedItem(
                title=title,
                description=entry.get("summary", "").strip(),
                link=entry.get("link", ""),
                source=source.name,
                source_priority=source.priority,
                category=source.category,
                published=_parse_date(entry),
            )
        )
    return items


async def _fetch_single(client: httpx.AsyncClient, source: FeedSource) -> list[FeedItem]:
    """Fetch and parse a single feed. Returns empty list on failure."""
    try:
        response = await client.get(source.url)
        response.raise_for_status()
        items = _parse_feed(response.text, source)
        log.info("fetcher.feed_ok", source=source.name, items=len(items))
        return items
    except Exception as e:
        log.warning("fetcher.feed_failed", source=source.name, error=str(e))
        return []


async def fetch_all_feeds(feeds: list[FeedSource]) -> list[FeedItem]:
    """Fetch all configured feeds in parallel."""
    async with httpx.AsyncClient(timeout=FETCH_TIMEOUT, follow_redirects=True) as client:
        tasks = [_fetch_single(client, feed) for feed in feeds]
        results = await asyncio.gather(*tasks)

    all_items = [item for result in results for item in result]
    log.info("fetcher.done", total_items=len(all_items), feeds_attempted=len(feeds))
    return all_items
