import re

from .models import Digest, DigestStory

# Characters that must be escaped in Telegram MarkdownV2
_ESCAPE_CHARS = re.compile(r"([_*\[\]()~`>#+\-=|{}.!])")


def _escape(text: str) -> str:
    """Escape special characters for Telegram MarkdownV2."""
    return _ESCAPE_CHARS.sub(r"\\\1", text)


def _format_source_link(source: dict) -> str:
    """Format a single source as a MarkdownV2 link."""
    name = _escape(source.get("name", "Quelle"))
    url = source.get("url", "")
    # In MarkdownV2 links, only ) and \ need escaping inside the URL
    url = url.replace("\\", "\\\\").replace(")", "\\)")
    return f"[{name}]({url})"


def _format_story(story: DigestStory) -> str:
    """Format a single story."""
    emoji = story.emoji or "📰"
    headline = _escape(story.headline)
    summary = _escape(story.summary)

    source_links = " · ".join(_format_source_link(s) for s in story.sources)

    lines = [f"{emoji} *{headline}*", summary]
    if source_links:
        lines.append(source_links)

    return "\n".join(lines)


def format_digest(digest: Digest) -> list[str]:
    """Convert a Digest into Telegram MarkdownV2 messages.

    Returns a list of messages (usually 1) to handle the 4096-char limit.
    """
    header = f"📰 *News Digest — {_escape(digest.date)}*\n\n{_escape(digest.greeting)}"

    # Group stories by category
    inland = [s for s in digest.stories if s.category == "inland"]
    international = [s for s in digest.stories if s.category == "international"]
    positive = [s for s in digest.stories if s.category == "positive"]

    messages: list[str] = [header]

    for label, stories in [("🇩🇪 *Inland*", inland), ("🌍 *International*", international), ("🌟 *Gute Nachrichten*", positive)]:
        if not stories:
            continue
        section_lines = [label, ""]
        for story in stories:
            section_lines.append(_format_story(story))
            section_lines.append("")
        messages.append("\n".join(section_lines).strip())

    messages[-1] += f"\n\n—\n_Zugestellt von Oskar_ 🐦"

    return messages
