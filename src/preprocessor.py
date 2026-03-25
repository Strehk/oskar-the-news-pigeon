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
    """Filter, deduplicate, sort, and cap the item list."""
    # 1. Filter by age
    items = _filter_by_age(items, settings.max_age_hours)

    # 2. Deduplicate
    items = _deduplicate(items, settings.dedup_threshold)

    # 3. Sort: priority first (lower = better), then newest first
    items.sort(key=lambda x: (x.source_priority, -x.published.timestamp()))

    # 4. Cap
    items = items[: settings.max_items_to_llm]

    log.info("preprocessor.done", items=len(items))
    return items
