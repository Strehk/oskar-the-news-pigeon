<p align="center">
  <img src="assets/oskar-portrait.png" alt="Oskar the News Pigeon" width="200">
</p>

# Oskar the News Pigeon 🐦

A daily news digest bot for Telegram. Oskar fetches RSS feeds from German and international sources, deduplicates and ranks them, uses a single Claude API call to curate and summarize the top stories, and delivers a formatted German-language digest to all subscribers.

Users subscribe by messaging the bot `/start` — no channels or groups needed.

<p align="center">
  <img src="assets/oskar-flying.png" alt="Oskar delivering the news" width="600">
</p>

```
📰 News Digest — 25. März 2026

🐦 Guten Morgen! Oskar hat die wichtigsten Nachrichten für euch gesammelt.

🇩🇪 Inland

🏛️ SPD in der Krise: Jusos fordern Führungswechsel
Nach der Schlappe in Rheinland-Pfalz fordert Juso-Chef Türmer eine Neuaufstellung.
Tagesspiegel · Zeit

🌍 International

💣 Iran-Krieg: Widersprüchliche Signale
Trump lobt Gespräche, Teheran widerspricht. Raketen fliegen weiter.
Zeit · BBC

—
Zugestellt von Oskar 🐦
```

## How It Works

```
RSS Feeds (6 sources)
    → Fetch in parallel (httpx + feedparser)
    → Preprocess (age filter, fuzzy dedup, priority sort)
    → Curate (single Claude API call → structured JSON)
    → Format (Telegram MarkdownV2)
    → Send to all subscribers
```

The entire pipeline runs once per day. Cost: ~$0.01/day (~$0.30/month) for the Claude API call.

## Setup

### 1. Create a Telegram Bot

1. Open Telegram and message [@BotFather](https://t.me/BotFather)
2. Send `/newbot`
3. Choose a **name** (e.g. `Oskar the News Pigeon`)
4. Choose a **username** (must end in `bot`, e.g. `oskar_news_pigeon_bot`)
5. BotFather will reply with a **token** like `7123456789:AAH...` — save it

Optional BotFather setup (recommended):
```
/setdescription → Deine tägliche Nachrichtenbrieftaube 🐦
/setabouttext   → Jeden Morgen die wichtigsten Nachrichten aus Deutschland und der Welt.
/setcommands    → start - Nachrichten-Digest abonnieren
                  stop - Abo beenden
```

### 2. Get an Anthropic API Key

1. Go to [console.anthropic.com](https://console.anthropic.com)
2. Create an API key
3. Add credits (the bot uses ~$0.30/month)

### 3. Configure Environment

```bash
cp .env.example .env
```

Edit `.env` and fill in your keys:

```bash
TELEGRAM_BOT_TOKEN=7123456789:AAH...
ANTHROPIC_API_KEY=sk-ant-...
```

All other settings have sensible defaults. See [Configuration](#configuration) for the full list.

### 4. Run

#### Local (Python 3.12+)

```bash
# Create venv and install
python -m venv .venv
source .venv/bin/activate
pip install -e .

# Start the bot (polling + scheduler)
python -m src.main
```

#### Docker (pre-built image)

```bash
docker run -d --restart unless-stopped \
  -e TELEGRAM_BOT_TOKEN=your-token \
  -e ANTHROPIC_API_KEY=sk-ant-... \
  -v ./data:/app/data \
  ghcr.io/strehk/oskar-the-news-pigeon:latest
```

#### Docker (build locally)

```bash
docker compose up -d
```

#### Docker on Dokploy

1. Connect your Git repo in Dokploy
2. Select "Docker Compose" as build method
3. Set environment variables in the Dokploy UI:
   - `TELEGRAM_BOT_TOKEN`
   - `ANTHROPIC_API_KEY`
   - Optionally: `FEEDS`, `SCHEDULE_CRON`, etc.
4. Deploy

## Usage

Once the bot is running, users interact via Telegram:

| Command | Effect |
|---------|--------|
| `/start` | Subscribe to the daily digest |
| `/stop` | Unsubscribe |

The digest is sent automatically every morning at **8:30 Berlin time** (configurable via `SCHEDULE_CRON`).

### CLI Flags

```bash
# Run the full pipeline once immediately
python -m src.main --now

# Run the full pipeline but print instead of sending
python -m src.main --now --dry-run

# Only fetch and preprocess (no LLM, no sending)
python -m src.main --fetch-only

# Normal mode: bot polling + daily scheduler
python -m src.main
```

## Configuration

All settings are via environment variables. No config files needed.

### Required

| Variable | Description |
|----------|-------------|
| `TELEGRAM_BOT_TOKEN` | Bot token from BotFather |
| `ANTHROPIC_API_KEY` | Anthropic API key |

### Optional

| Variable | Default | Description |
|----------|---------|-------------|
| `TELEGRAM_CHANNEL_ID` | _(empty)_ | Also send to a channel (e.g. `@my_channel`) |
| `FEEDS` | 6 default feeds | JSON array of feed configs (see below) |
| `SCHEDULE_CRON` | `30 6 * * *` | Cron expression in UTC (6:30 UTC = 8:30 Berlin) |
| `SCHEDULE_TIMEZONE` | `Europe/Berlin` | Timezone for display |
| `LLM_MODEL` | `claude-sonnet-4-20250514` | Anthropic model ID |
| `LLM_MAX_TOKENS` | `1500` | Max tokens for LLM response (500–4000) |
| `MAX_AGE_HOURS` | `24` | Only include articles from last N hours (1–72) |
| `MAX_ITEMS_TO_LLM` | `30` | Max items to send to LLM (10–100) |
| `TARGET_STORIES_MIN` | `5` | Minimum stories in digest (3–10) |
| `TARGET_STORIES_MAX` | `7` | Maximum stories in digest (5–15) |
| `DEDUP_THRESHOLD` | `0.7` | Title similarity threshold for dedup (0.5–1.0) |
| `LOG_LEVEL` | `INFO` | `DEBUG`, `INFO`, `WARNING`, or `ERROR` |
| `DRY_RUN` | `false` | Print digest instead of sending |

### Custom Feeds

Override the default feeds by setting `FEEDS` as a JSON array:

```bash
FEEDS='[
  {"name": "Tagesspiegel", "url": "https://www.tagesspiegel.de/contentexport/feed/politik", "priority": 1, "category": "inland"},
  {"name": "BBC World", "url": "https://feeds.bbci.co.uk/news/world/rss.xml", "priority": 2, "category": "international"}
]'
```

Each feed has:
- `name` — Display name (required)
- `url` — RSS feed URL (required)
- `priority` — `1` (high) or `2` (normal), default `2`
- `category` — `inland` or `international`, default `inland`

### Default Feeds

| Source | Category | Priority |
|--------|----------|----------|
| Tagesspiegel Politik | Inland | 1 (high) |
| Zeit Politik | Inland | 1 (high) |
| FAZ Politik | Inland | 2 |
| Süddeutsche Politik | Inland | 2 |
| BBC World | International | 2 |
| The Guardian World | International | 2 |

## Architecture

```
src/
├── main.py              # Entry point: bot polling + scheduler + CLI
├── settings.py          # Pydantic Settings (env var validation)
├── config.py            # Config loader
├── models.py            # Data models (FeedItem, DigestStory, Digest)
├── fetcher.py           # Async RSS fetching (httpx + feedparser)
├── preprocessor.py      # Age filter, fuzzy dedup (rapidfuzz), sorting
├── curator.py           # Claude API call (tool-use for structured output)
├── formatter.py         # Telegram MarkdownV2 formatting
├── sender.py            # Telegram delivery with retry
└── db.py                # SQLite subscriber store
```

### Error Handling

- **Feed unreachable**: Skipped with warning, continues with other feeds
- **All feeds down**: Empty digest, logged as warning
- **Claude API error**: Retries 2x, then falls back to raw headlines
- **Telegram error**: Retries 3x with exponential backoff
- **User blocked bot**: Automatically unsubscribed

## Tech Stack

| Component | Technology |
|-----------|-----------|
| Runtime | Python 3.12+ |
| RSS Parsing | feedparser |
| HTTP | httpx |
| LLM | Anthropic Claude API |
| Telegram | python-telegram-bot |
| Config | pydantic-settings |
| Dedup | rapidfuzz |
| Scheduling | APScheduler 3.x |
| Logging | structlog |
| Subscribers | SQLite |
| Container | Docker |
