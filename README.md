# seoscout

> **From keywords to multilingual articles — in one command.**

seoscout is a CLI tool for SEO professionals and content creators. Feed it a list of keywords, and it will:

- 🔍 **Search** YouTube (via yt-dlp) and Google (via Serper API) in parallel
- 📥 **Collect** YouTube video transcripts and full web page text (via Jina Reader)
- ✍️ **Generate** SEO-optimized MDX articles using LLM (with JS export metadata)
- 🌍 **Translate** articles into multiple languages

No more manually opening every search result, copy-pasting, or paying for expensive content tools.

## Features

- **Full pipeline** — keywords → search → collect → generate → translate
- **Parallel search** — YouTube + Google at the same time
- **LLM-powered writing** — generate SEO articles from collected material
- **Multi-language** — translate articles to any language (Spanish, Japanese, Arabic, and more)
- **Smart filtering** — filter by duration, topic relevance, and block competitor/spam domains
- **Caching** — each source is only extracted once; re-runs skip cached content
- **Proxy support** — rotating proxy for YouTube transcript extraction when IP-blocked
- **Configurable** — control concurrency, batch size, LLM model via `.env`

## Quick Start

### Prerequisites

- Python 3.10+
- [yt-dlp](https://github.com/yt-dlp/yt-dlp) installed (`pip install yt-dlp`)
- A [Serper API](https://serper.dev/) key (free tier available) — for search
- A [Jina AI](https://jina.ai/) API key (optional, but recommended) — for web extraction
- An LLM API key (e.g. [Gemini](https://ai.google.dev/) via OpenAI-compatible endpoint) — for generate & translate

### Install

```bash
git clone https://github.com/Claire1940/seoscout.git
cd seoscout
pip install -e .
```

### Configure

```bash
cp .env.example .env
# Edit .env — add your API keys
```

### Prepare your keywords file

Create a JSON file with your keywords:

**Categorized format** (articles organized into category directories):

```json
{
  "topic_name": "My Game",
  "languages": ["es", "pt", "de", "fr"],
  "categories": [
    {
      "category": "Guide",
      "keywords": [
        "My Game beginner guide",
        "My Game walkthrough",
        "My Game how to level up fast"
      ]
    },
    {
      "category": "Tier List",
      "keywords": [
        "My Game best characters tier list",
        "My Game best weapons"
      ]
    }
  ]
}
```

**Flat format** (all articles in one directory):

```json
{
  "topic_name": "My Game",
  "keywords": [
    "My Game beginner guide",
    "My Game best characters tier list",
    "My Game tips and tricks"
  ]
}
```

> - `topic_name` is optional. When set, search results that don't mention the topic in their title or snippet are automatically filtered out. The categorized format organizes output into subdirectories: `articles/en/guide/`, `articles/en/tier-list/`, etc.
> - `languages` is optional. When set in the keywords JSON, `seoscout run` will automatically translate articles to the specified languages after generation. If not set, `seoscout translate` requires the `--lang` flag.

### Run

```bash
# Step 1: Search keywords on YouTube + Google
seoscout search --keywords keywords.json

# Step 2: Collect transcripts and web content
seoscout collect --keywords keywords.json

# Step 3: Generate articles from collected material
seoscout generate --keywords keywords.json

# Step 4: Translate to other languages
seoscout translate --keywords keywords.json --lang es,pt,de,fr
```

Or do search + collect + generate (and translate if `languages` is set) in one command:

```bash
seoscout run --keywords keywords.json
```

The project name is auto-derived from `topic_name` in your keywords file (lowercased, spaces replaced with `_`). If no `topic_name` is set, the filename is used instead.

You can also use it as a Python module:

```bash
python -m seoscout run --keywords keywords.json
```

## How It Works

### Reviewed writing samples (2026-10-27)

For the source-grounded V2 writing prompt, pass it explicitly after reviewing search and collected sources:

```bash
seoscout generate --keywords keywords.json --prompt seoscout/templates/generate_v2.md
```

The V2 prompt does not force word counts, keyword repetitions or tables. The legacy built-in prompt remains available; V2 is selected with `--prompt` in this workflow.

`LLM_THINKING` may be empty (preserve provider defaults), `enabled`, or `disabled`. Set it only for a provider that supports the `thinking` field, such as DeepSeek. For an initial DeepSeek writing sample, `LLM_THINKING=disabled`, `LLM_MAX_TOKENS=8192` and `GENERATE_BATCH_SIZE=1` provide a conservative starting configuration; verify the output before expanding.

If Jina extraction fails for a Steam community App/news page, the collector can use Steam's public news API. This fallback is limited to the matching AppID's `steam_community_announcements` feed; third-party news is excluded. It does not provide a general fallback for store pages or other websites.

Install with Python 3.10+ and install `yt-dlp` as well if using YouTube search. Keep API keys in the ignored `.env` file. Source collection failures must be reviewed before generation; a command's completion message alone is not proof that usable source files were produced.

```
keywords.json
     │
     ▼
┌─────────────────────────────┐
│  seoscout search             │  ← auto project name from topic_name
│  ┌───────────┐ ┌──────────┐ │
│  │  YouTube   │ │  Google  │ │
│  │  (yt-dlp)  │ │ (Serper) │ │
│  └─────┬─────┘ └────┬─────┘ │
│        └──────┬──────┘       │
│               ▼              │
│    search_results.json       │
│    (review & filter)         │
└─────────────────────────────┘
              │
              ▼
┌─────────────────────────────┐
│  seoscout collect            │
│  ┌───────────┐ ┌──────────┐ │
│  │  YouTube   │ │   Web    │ │
│  │ transcripts│ │  (Jina)  │ │
│  └─────┬─────┘ └────┬─────┘ │
│        └──────┬──────┘       │
│               ▼              │
│     collected/*.json         │
│     (per-keyword material)   │
└─────────────────────────────┘
              │
              ▼
┌─────────────────────────────┐
│  seoscout generate           │
│        ┌──────────┐          │
│        │   LLM    │          │
│        └────┬─────┘          │
│             ▼                │
│     articles/en/*.mdx        │
│     (MDX articles w/ JS      │
│      export metadata)        │
└─────────────────────────────┘
              │
              ▼
┌─────────────────────────────┐
│  seoscout translate          │
│  --lang es,pt,de,fr,ja,...  │
│        ┌──────────┐          │
│        │   LLM    │          │
│        └────┬─────┘          │
│             ▼                │
│  articles/{lang}/*.mdx       │
│  (multilingual articles)     │
└─────────────────────────────┘
```

## Output Format

### search_results.json (Step 1 output)

```json
{
  "version": "2.0",
  "created_at": "2026-06-10T12:00:00",
  "keywords": [
    {
      "keyword": "My Game beginner guide",
      "youtube": {
        "count": 2,
        "items": [
          {
            "title": "My Game Beginner Guide 2026",
            "url": "https://youtube.com/watch?v=xxx",
            "video_id": "xxx",
            "channel": "Gamer",
            "duration": "15:30",
            "duration_seconds": 930,
            "view_count": 50000,
            "selected": true
          }
        ]
      },
      "web": {
        "count": 5,
        "items": [
          {
            "title": "Complete Beginner Guide - My Game Wiki",
            "url": "https://example.com/guide",
            "domain": "example.com",
            "snippet": "Everything you need to know...",
            "selected": true
          }
        ]
      }
    }
  ]
}
```

Set `"selected": false` on items you don't want, then run `seoscout collect`.

### collected/*.json (Step 2 output)

One file per keyword (e.g. `my_game_beginner_guide.json`):

```json
{
  "keyword": "My Game beginner guide",
  "collected_at": "2026-06-10T12:05:00",
  "sources": {
    "youtube": {
      "count": 1,
      "videos": [
        {
          "type": "youtube",
          "title": "My Game Beginner Guide 2026",
          "url": "https://youtube.com/watch?v=xxx",
          "content": "Full transcript text here..."
        }
      ]
    },
    "web": {
      "count": 1,
      "pages": [
        {
          "type": "web",
          "title": "Complete Beginner Guide",
          "url": "https://example.com/guide",
          "content": "Cleaned web page content here..."
        }
      ]
    }
  },
  "total_sources": 2
}
```

### articles/en/*.mdx (Step 3 output)

One MDX file per keyword (e.g. `my-game-beginner-guide.mdx`). Uses JavaScript `export const metadata` syntax for compatibility with Next.js MDX wiki projects:

```mdx
export const metadata = {
  title: "My Game Beginner Guide: Everything You Need to Know in 2026",
  description: "Complete beginner guide for My Game with tips, strategies, and walkthrough.",
  category: "guide",
  date: "2026-06-10",
}

## Getting Started

Your article content here...

## Tips and Tricks

- Tip 1...
- Tip 2...

## FAQ

**Q: Is My Game free to play?**
A: Yes, My Game is...
```

With categorized keywords, articles are organized into subdirectories: `articles/en/guide/`, `articles/en/bosses/`, `articles/en/tier-list/`, etc.

### articles/{lang}/*.mdx (Step 4 output)

Same structure as English articles, translated to the target language. Any language code works — common ones:

| Code | Language | Code | Language |
|------|----------|------|----------|
| `es` | Spanish | `ko` | Korean |
| `pt` | Portuguese (Brazil) | `ru` | Russian |
| `de` | German | `zh` | Chinese |
| `fr` | French | `vi` | Vietnamese |
| `ja` | Japanese | `th` | Thai |
| `ar` | Arabic | `id` | Indonesian |
| `it` | Italian | `tr` | Turkish |
| `pl` | Polish | `nl` | Dutch |
| `hi` | Hindi | `tl` | Tagalog |

## Configuration Reference

All settings go in `.env` (copy from `.env.example` and fill in your keys):

```bash
cp .env.example .env
```

### 🔑 Required — API Keys

You need at least one API key to use seoscout:

```bash
# Google search via Serper — REQUIRED
# Get your free key at https://serper.dev/
SERPER_API_KEY=your_serper_api_key_here

# Web page content extraction via Jina — RECOMMENDED
# Without this, you get lower rate limits
# Get your free key at https://jina.ai/
JINA_API_KEY=your_jina_api_key_here
```

| Variable | Required | Where to get |
|----------|:--------:|--------------|
| `SERPER_API_KEY` | ✅ Yes | [serper.dev](https://serper.dev/) (free tier available) |
| `JINA_API_KEY` | Recommended | [jina.ai](https://jina.ai/) (free tier available) |
| `LLM_API_KEY` | For generate/translate | Any OpenAI-compatible API (Gemini, OpenAI, etc.) |

### 🌐 Proxy — For YouTube Transcript Extraction

YouTube blocks IPs that request too many transcripts. If you see `RequestBlocked` errors, enable a proxy.

**With rotating proxy (e.g. 青果网络 / Qingguo):**

```bash
USE_PROXY=true
TUNNEL_HOST=overseas.tunnel.qg.net
TUNNEL_PORT=16660
TUNNEL_USER=your_username
TUNNEL_PASS=your_password
TUNNEL_PROXY_FORMAT=tagged
TUNNEL_CHANNEL_PREFIX=channel
TUNNEL_TTL=60
```

**With standard HTTP proxy:**

```bash
USE_PROXY=true
TUNNEL_HOST=proxy.example.com
TUNNEL_PORT=8080
TUNNEL_USER=your_username
TUNNEL_PASS=your_password
TUNNEL_PROXY_FORMAT=standard
```

**Control proxy per stage** (optional):

```bash
# Only use proxy for YouTube transcript extraction, not for search
USE_PROXY=false
USE_PROXY_FOR_SEARCH=false
USE_PROXY_FOR_EXTRACT=true
```

### 📁 Output

| Variable | Default | Description |
|----------|---------|-------------|
| `OUTPUT_DIR` | `./output` | Root directory for all project data |

### 🎬 YouTube Tuning

| Variable | Default | Description |
|----------|---------|-------------|
| `YOUTUBE_INITIAL_SEARCH_RESULTS` | `2` | Videos to fetch per keyword |
| `YOUTUBE_MAX_DURATION` | `3600` | Skip videos longer than this (seconds) |
| `YOUTUBE_EXTRACT_TOP_K` | `1` | How many transcripts to extract per keyword |
| `YOUTUBE_SEARCH_WORKERS` | `10` | Parallel search workers |
| `YOUTUBE_TRANSCRIPT_WORKERS` | `15` | Parallel transcript workers |

### 🌍 Web Tuning

| Variable | Default | Description |
|----------|---------|-------------|
| `WEB_SEARCH_TOP_N` | `10` | Google results per keyword |
| `WEB_EXTRACT_TOP_K` | `1` | Pages to extract per keyword |
| `WEB_SEARCH_CONCURRENCY` | `5` | Serper API concurrency |
| `JINA_RPM` | `200` | Jina rate limit (requests/min) |
| `JINA_CONCURRENCY` | `20` | Jina parallel requests |
| `WEB_EXTRACT_RETRIES` | `3` | Retries for web extraction |

### 🤖 LLM — For Generate & Translate

Required for `seoscout generate` and `seoscout translate`. Any OpenAI-compatible API endpoint works (Gemini, OpenAI, DeepSeek, etc.).

```bash
LLM_API_KEY=your_api_key
LLM_API_BASE_URL=https://api.apifast.tech/v1
LLM_MODEL=gemini-2.5-flash
LLM_MAX_TOKENS=24576
```

| Variable | Default | Description |
|----------|---------|-------------|
| `LLM_API_KEY` | _(empty)_ | API key for the LLM |
| `LLM_API_BASE_URL` | `https://api.apifast.tech/v1` | OpenAI-compatible endpoint |
| `LLM_MODEL` | `gemini-2.5-flash` | Model name |
| `LLM_TEMPERATURE` | `0.7` | Sampling temperature |
| `LLM_MAX_TOKENS` | `24576` | Max output tokens per request |
| `LLM_TIMEOUT` | `300` | Request timeout (seconds) |
| `LLM_RETRY_ATTEMPTS` | `2` | Retries on failure |
| `LLM_RETRY_DELAY` | `5` | Seconds between retries |

### ⚡ Concurrency — Generate & Translate

| Variable | Default | Description |
|----------|---------|-------------|
| `GENERATE_BATCH_SIZE` | `100` | Articles per parallel batch |
| `GENERATE_CONCURRENT_LIMIT` | `10` | Max concurrent generate requests |
| `TRANSLATE_BATCH_SIZE` | `10` | Translations per parallel batch |
| `TRANSLATE_BATCH_DELAY` | `1` | Seconds between translation batches |

### ⚙️ General

| Variable | Default | Description |
|----------|---------|-------------|
| `SEARCH_MAX_RETRIES` | `3` | Search retry attempts |
| `SEARCH_RETRY_DELAY` | `2` | Seconds between retries |
| `BLOCKED_DOMAINS` | `youtube.com,youtu.be,...` | Domains excluded from web results |

## FAQ

### yt-dlp not found

Make sure yt-dlp is installed and on your PATH:

```bash
pip install yt-dlp
yt-dlp --version
```

### YouTube transcript extraction fails

YouTube sometimes blocks IPs that make too many requests. Solutions:
1. Wait a few minutes and retry
2. Enable proxy in `.env` with a rotating proxy service
3. Reduce `YOUTUBE_TRANSCRIPT_WORKERS` to lower concurrency

### Serper API returns errors

- Check your API key is correct
- Free tier has rate limits; reduce `WEB_SEARCH_CONCURRENCY`
- Check your account balance at [serper.dev](https://serper.dev/)

### Web content is too short or empty

Some pages block automated extraction. Try:
- Reducing `JINA_CONCURRENCY` to avoid rate limits
- Adding a `JINA_API_KEY` for higher rate limits

### LLM generation fails or returns empty

- Check `LLM_API_KEY` is set and valid
- Try reducing `GENERATE_BATCH_SIZE` or `GENERATE_CONCURRENT_LIMIT` if rate limited
- Check `LLM_MAX_TOKENS` — some models have lower limits
- Check your API provider's status page

### How to use a custom prompt template?

Pass `--prompt /path/to/your/prompt.md` to `generate` or `translate`. The generate template uses `{merged_data}`, `{current_date}`, and `{category}` variables. The translate template uses `$language_name`, `$lang_code`, and `$content` variables.

### Can I use OpenAI / DeepSeek / other models?

Yes — seoscout uses the OpenAI-compatible chat completions API. Set `LLM_API_BASE_URL` and `LLM_MODEL` to match your provider:

```bash
# OpenAI
LLM_API_BASE_URL=https://api.openai.com/v1
LLM_MODEL=gpt-4o

# DeepSeek
LLM_API_BASE_URL=https://api.deepseek.com/v1
LLM_MODEL=deepseek-chat
```

## License

[MIT](LICENSE)
