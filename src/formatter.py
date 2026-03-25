import re

from .models import Digest, DigestStory

# Characters that must be escaped in Telegram MarkdownV2
_ESCAPE_CHARS = re.compile(r"([_*\[\]()~`>#+\-=|{}.!])")

# Max Telegram message length
MAX_MESSAGE_LENGTH = 4096


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

    sections: list[str] = []

    if inland:
        section_lines = [f"\n\n🇩🇪 *Inland*\n"]
        for story in inland:
            section_lines.append(_format_story(story))
        sections.append("\n\n".join(section_lines))

    if international:
        section_lines = [f"\n\n🌍 *International*\n"]
        for story in international:
            section_lines.append(_format_story(story))
        sections.append("\n\n".join(section_lines))

    if positive:
        section_lines = [f"\n\n🌟 *Gute Nachrichten*\n"]
        for story in positive:
            section_lines.append(_format_story(story))
        sections.append("\n\n".join(section_lines))

    footer = f"\n\n—\n_Zugestellt von Oskar_ 🐦"

    # Try to fit everything in one message
    full_message = header + "".join(sections) + footer

    if len(full_message) <= MAX_MESSAGE_LENGTH:
        return [full_message]

    # Split into multiple messages if needed
    messages: list[str] = [header]
    current = header

    for section in sections:
        if len(current) + len(section) + len(footer) <= MAX_MESSAGE_LENGTH:
            current += section
        else:
            messages[-1] = current
            current = section
            messages.append(current)

    messages[-1] = current + footer
    return messages
