from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class FeedSource:
    name: str
    url: str
    priority: int = 2
    category: str = "inland"


@dataclass
class FeedItem:
    title: str
    description: str
    link: str
    source: str
    source_priority: int
    category: str
    published: datetime


@dataclass
class DigestStory:
    headline: str
    summary: str
    sources: list[dict] = field(default_factory=list)  # [{"name": "Zeit", "url": "..."}]
    category: str = "inland"
    emoji: str = ""


@dataclass
class Digest:
    date: str
    greeting: str
    stories: list[DigestStory] = field(default_factory=list)
