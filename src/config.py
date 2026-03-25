import sys

import structlog

from .settings import Settings

log = structlog.get_logger()


def load_config() -> Settings:
    """Load and validate all settings from environment."""
    try:
        settings = Settings()
        feeds = settings.get_feeds()
        log.info(
            "config.loaded",
            feeds=len(feeds),
            schedule=settings.schedule_cron,
            timezone=settings.schedule_timezone,
            stories=f"{settings.target_stories_min}-{settings.target_stories_max}",
            dry_run=settings.dry_run,
        )
        return settings
    except Exception as e:
        log.error("config.validation_failed", error=str(e))
        sys.exit(1)
