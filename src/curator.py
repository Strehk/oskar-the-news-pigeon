import json
from datetime import datetime, timezone

import anthropic
import structlog

from .models import Digest, DigestStory, FeedItem
from .settings import Settings

log = structlog.get_logger()

SYSTEM_PROMPT = """\
Du bist Oskar, die Nachrichtenbrieftaube. Du bist ein erfahrener \
Nachrichtenredakteur, der jeden Morgen die wichtigsten Nachrichten \
zusammenfasst.

Dein Stil ist:
- Kompakt und informativ
- Sachlich, aber nicht langweilig
- Deutsche Sprache, klare Formulierungen
"""

PUBLISH_DIGEST_TOOL = {
    "name": "publish_digest",
    "description": "Veröffentliche den kuratierten News Digest",
    "input_schema": {
        "type": "object",
        "properties": {
            "greeting": {
                "type": "string",
                "description": "Kurze Begrüßung von Oskar der Brieftaube (1 Satz, mit Persönlichkeit)",
            },
            "stories": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "headline": {
                            "type": "string",
                            "description": "Kurze, prägnante Überschrift",
                        },
                        "summary": {
                            "type": "string",
                            "description": "1-2 Sätze Zusammenfassung",
                        },
                        "category": {
                            "type": "string",
                            "enum": ["inland", "international"],
                        },
                        "source_indices": {
                            "type": "array",
                            "items": {"type": "integer"},
                            "description": "Indices der verwendeten Quellen aus der Input-Liste",
                        },
                        "emoji": {
                            "type": "string",
                            "description": "Ein passendes Emoji für das Thema",
                        },
                    },
                    "required": ["headline", "summary", "category", "source_indices", "emoji"],
                },
            },
        },
        "required": ["greeting", "stories"],
    },
}


def _build_user_message(items: list[FeedItem], settings: Settings) -> str:
    lines = [
        f"Analysiere diese {len(items)} Meldungen und erstelle einen Digest.",
        "",
        "AUFGABEN:",
        f"1. Wähle die {settings.target_stories_min}-{settings.target_stories_max} wichtigsten Stories",
        "2. Gruppiere zusammengehörige Meldungen (gleiches Thema, verschiedene Quellen)",
        "3. Schreibe für jede Story eine knappe Zusammenfassung (1-2 Sätze)",
        '4. Kategorisiere: "inland" oder "international"',
        "",
        "PRIORITÄTEN:",
        "- Quellen mit Priorität 1 sind Top-Quellen — bevorzuge diese",
        "- Politische Relevanz > Sensationalismus",
        "- Aktualität zählt",
        "",
        "MELDUNGEN:",
    ]

    for i, item in enumerate(items):
        lines.append(
            f"[{i}] [{item.source} | Prio {item.source_priority} | {item.category}] "
            f"{item.title}"
        )
        if item.description:
            lines.append(f"    {item.description[:200]}")
        lines.append(f"    URL: {item.link}")
        lines.append("")

    return "\n".join(lines)


def _build_fallback_digest(items: list[FeedItem]) -> Digest:
    """Build a basic digest without LLM when all retries fail."""
    log.warning("curator.using_fallback")
    stories = []
    for item in items[:7]:
        stories.append(
            DigestStory(
                headline=item.title,
                summary=item.description[:200] if item.description else "",
                sources=[{"name": item.source, "url": item.link}],
                category=item.category,
                emoji="📰",
            )
        )
    return Digest(
        date=datetime.now(timezone.utc).strftime("%d. %B %Y"),
        greeting="Guten Morgen! Hier sind die heutigen Nachrichten.",
        stories=stories,
    )


def _parse_tool_result(tool_input: dict, items: list[FeedItem]) -> Digest:
    """Parse the tool call result into a Digest."""
    stories = []
    for story_data in tool_input.get("stories", []):
        # Resolve source indices to actual source info
        sources = []
        for idx in story_data.get("source_indices", []):
            if 0 <= idx < len(items):
                sources.append({"name": items[idx].source, "url": items[idx].link})

        stories.append(
            DigestStory(
                headline=story_data["headline"],
                summary=story_data["summary"],
                sources=sources,
                category=story_data.get("category", "inland"),
                emoji=story_data.get("emoji", "📰"),
            )
        )

    return Digest(
        date=datetime.now(timezone.utc).strftime("%d. %B %Y"),
        greeting=tool_input.get("greeting", "Guten Morgen!"),
        stories=stories,
    )


async def curate(items: list[FeedItem], settings: Settings) -> Digest:
    """Use Claude to select and summarize the top stories."""
    if not items:
        return Digest(
            date=datetime.now(timezone.utc).strftime("%d. %B %Y"),
            greeting="Guten Morgen! Leider keine Nachrichten heute.",
            stories=[],
        )

    client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
    user_message = _build_user_message(items, settings)

    last_error = None
    for attempt in range(1 + 2):  # 1 try + 2 retries
        try:
            response = await client.messages.create(
                model=settings.llm_model,
                max_tokens=settings.llm_max_tokens,
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": user_message}],
                tools=[PUBLISH_DIGEST_TOOL],
                tool_choice={"type": "tool", "name": "publish_digest"},
            )

            # Extract tool use result
            for block in response.content:
                if block.type == "tool_use" and block.name == "publish_digest":
                    digest = _parse_tool_result(block.input, items)
                    log.info("curator.done", stories=len(digest.stories), attempt=attempt + 1)
                    return digest

            log.warning("curator.no_tool_call", attempt=attempt + 1)
            last_error = "No tool call in response"

        except (anthropic.APIError, anthropic.APITimeoutError) as e:
            last_error = e
            log.warning("curator.api_error", error=str(e), attempt=attempt + 1)

    log.error("curator.all_retries_failed", last_error=str(last_error))
    return _build_fallback_digest(items)
