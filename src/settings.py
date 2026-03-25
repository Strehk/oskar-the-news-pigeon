import json

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings

from .models import FeedSource


class Settings(BaseSettings):
    """All app settings, validated at startup from environment variables."""

    # === REQUIRED ===
    telegram_bot_token: str = Field(..., description="Telegram Bot Token")
    telegram_channel_id: str = Field(
        default="", description="Channel (@name or -100xxx), optional if using subscriptions"
    )
    anthropic_api_key: str = Field(..., description="Anthropic API Key")

    # === FEEDS (JSON Array) ===
    feeds: str = Field(
        ...,
        description="JSON array of feed configs",
    )

    # === SCHEDULE ===
    schedule_cron: str = Field(default="30 6 * * *", description="Cron expression (UTC)")
    schedule_timezone: str = Field(default="Europe/Berlin", description="Timezone for display")

    # === LLM ===
    llm_model: str = Field(default="claude-sonnet-4-20250514", description="Anthropic model ID")
    llm_max_tokens: int = Field(default=1500, ge=500, le=4000)

    # === PROCESSING ===
    max_age_hours: int = Field(default=24, ge=1, le=72)
    max_items_to_llm: int = Field(default=30, ge=10, le=100)
    target_stories_min: int = Field(default=5, ge=3, le=10)
    target_stories_max: int = Field(default=7, ge=5, le=15)
    dedup_threshold: float = Field(default=0.7, ge=0.5, le=1.0)

    # === RUNTIME ===
    log_level: str = Field(default="INFO", pattern="^(DEBUG|INFO|WARNING|ERROR)$")
    dry_run: bool = Field(default=False, description="Print instead of send")

    # === VALIDATORS ===
    @field_validator("feeds")
    @classmethod
    def validate_feeds_json(cls, v: str) -> str:
        try:
            feeds = json.loads(v)
            if not isinstance(feeds, list):
                raise ValueError("feeds must be a JSON array")
            if len(feeds) == 0:
                raise ValueError("feeds cannot be empty")
            for f in feeds:
                if "name" not in f or "url" not in f:
                    raise ValueError("each feed needs 'name' and 'url'")
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON in FEEDS: {e}")
        return v

    def get_feeds(self) -> list[FeedSource]:
        return [FeedSource(**f) for f in json.loads(self.feeds)]

    model_config = {
        "env_prefix": "",
        "case_sensitive": False,
    }
