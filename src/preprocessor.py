from datetime import datetime, timedelta, timezone

import structlog
from rapidfuzz import fuzz

from .models import FeedItem
from .settings import Settings

log = structlog.get_logger()


def _filter_by_age(items: list[FeedItem], max_age_hours: int) -> list[FeedItem]:
    """Remove items older than max_age_hours."""
    cutoff = datetime.now(timezone.utc) - timedelta(hours=max_age_hours)
    filtered = [item for item in items if item.published >= cutoff]
    log.debug("preprocessor.age_filter", before=len(items), after=len(filtered))
    return filtered


def _deduplicate(items: list[FeedItem], threshold: float) -> list[FeedItem]:
    """Remove near-duplicate titles, keeping higher-priority sources.

    Uses rapidfuzz token_sort_ratio which handles word reordering well
    (e.g. "OpenAI releases GPT-5" vs "GPT-5 released by OpenAI").
    """
    # Sort by priority (lower number = higher priority) so we keep the best source
    sorted_items = sorted(items, key=lambda x: (x.source_priority, x.published))

    # threshold is 0.0-1.0 in settings, rapidfuzz uses 0-100
    score_threshold = threshold * 100

    accepted: list[FeedItem] = []
    for item in sorted_items:
        is_duplicate = False
        for existing in accepted:
            score = fuzz.token_sort_ratio(item.title, existing.title)
            if score >= score_threshold:
                is_duplicate = True
                log.debug(
                    "preprocessor.dedup_match",
                    dropped=item.title[:60],
                    kept=existing.title[:60],
                    score=round(score, 1),
                )
                break
        if not is_duplicate:
            accepted.append(item)

    log.debug("preprocessor.dedup", before=len(items), after=len(accepted))
    return accepted


def preprocess(items: list[FeedItem], settings: Settings) -> list[FeedItem]:
    """Filter, deduplicate, sort, and cap the item list.

    Regular and positive items are processed separately to ensure
    positive stories aren't crowded out by the news cycle.
    """
    # Split into regular and positive pools
    regular = [i for i in items if i.category != "positive"]
    positive = [i for i in items if i.category == "positive"]

    # Process each pool independently
    for pool_name, pool in [("regular", regular), ("positive", positive)]:
        pool[:] = _filter_by_age(pool, settings.max_age_hours)
        pool[:] = _deduplicate(pool, settings.dedup_threshold)
        pool.sort(key=lambda x: (-x.published.timestamp(), x.source_priority))

    # Cap each pool
    regular = regular[: settings.max_items_to_llm]
    positive = positive[:10]  # Don't need many positive candidates

    combined = regular + positive
    log.info("preprocessor.done", regular=len(regular), positive=len(positive))
    return combined
