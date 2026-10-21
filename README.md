<div align="center">

# 🔍 Multi-Search Aggregator

**Aggregate multiple search channels and provide search and page-fetch tools for the web, HTTP APIs, and MCP clients.**

[![English](https://img.shields.io/badge/English-DBEDFA)](./README.md)
[![简体中文](https://img.shields.io/badge/简体中文-DFE0E5)](./README_zh.md)

[![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

</div>

---

## Contents

- [Overview](#overview)
- [Features](#features)
- [Search channels](#search-channels)
- [Quick start](#quick-start)
- [Ranking and search modes](#ranking-and-search-modes)
- [Web UI and HTTP API](#web-ui-and-http-api)
- [MCP interface](#mcp-interface)
- [Configuration](#configuration)
- [Project structure](#project-structure)

## Overview

Multi-Search Aggregator combines results from multiple search channels, deduplicates and ranks them, and presents them through a single service. It provides a web search page, a REST API, an SSE progress endpoint, and an MCP server over Streamable HTTP.

## Features

- Search across multiple channels, with channel filtering and runtime enable/disable controls.
- Quota-first mode tries quota-limited channels one at a time and stops on the first hit. If they fail or return no results, unlimited channels run concurrently.
- Parallel mode runs all enabled and configured channels concurrently.
- BM25 is the default ranker. Chinese text is tokenized with jieba and filtered using `search_agg/stopwords.txt`; no local embedding model needs to be downloaded or loaded.
- Results are deduplicated and interleaved across channels while preserving each channel's upstream order.
- The home page and static assets are served from paths relative to the project; the home page is at `/` and static files are under `/static/`.
- MCP `web_fetch` tries a local fetch first, then uses Firecrawl's keyless browser-backed scrape for failed public URLs, with Parallel as a second fallback.

## Search channels

Channel availability depends on configuration, network access, and provider status. Channels that require credentials are skipped when their keys are not configured.

| Category | Examples |
|---|---|
| General web search | Bing, 360 Search, Sogou, Startpage, Brave, Qwant, Google |
| AI and search APIs | Zhipu, Z.AI, Alibaba Bailian, Tavily (keyless / API key), Exa, Firecrawl (keyless / API key), Keenable (keyless / API key), Brave Search API, Baidu Qianfan AI Search, Doubao Search, Parallel Search, SerpBase |
| Academic and developer | arXiv, OpenAlex, OpenReview, DBLP, Stack Overflow, Wikipedia, MDN, npm, crates.io |
| Communities and Chinese content | Hacker News, Reddit, Zhihu, Xiaohongshu, WeRead, Substack, AMiner |
| Extensions | OpenCLI browser automation, MCP stdio, and skill scripts |

Tavily, Firecrawl, and Keenable expose separate keyless and API-key channels. The keyless Firecrawl and Keenable channels work without setup; Keenable's public quota is shared by IP, while an API key gives it a separate account limit. Exa, the keyed Firecrawl and Keenable channels, Brave Search API, Baidu Qianfan, Doubao Search, SerpBase, AMiner, and Zhihu Skill require their corresponding API keys or credentials. Providers may change free allocations, rate limits, or fees; check their current documentation and terms. Parallel Search's anonymous MCP endpoint does not require an API key, but remains subject to provider limits.

## Quick start

### 1. Install dependencies

```bash
git clone https://github.com/yourname/multi-search-aggregator.git
cd multi-search-aggregator
pip install -r requirements.txt
```

### 2. Configure API keys

```bash
cp .env.example .env
# Edit .env and add keys for the channels you want to use:
# ZHIPU_API_KEY=your_key_here
# ZAI_API_KEY=your_key_here
# BAILIAN_API_KEY=your_key_here
# TAVILY_API_KEY=your_key_here
# EXA_API_KEY=your_key_here
# FIRECRAWL_API_KEY=your_key_here
# KEENABLE_API_KEY=your_key_here  # optional; Keenable also has a keyless channel
# BRAVE_SEARCH_API_KEY=your_key_here
# BAIDU_QIANFAN_API_KEY=your_key_here
# DOUBAO_SEARCH_API_KEY=your_key_here
# SERPBASE_API_KEY=your_key_here
# AMINER_API_KEY=your_key_here
# ZHIHU_ACCESS_SECRET=your_key_here
# CONFIG_ADMIN_PASSWORD=use_a_strong_unique_password
```

Channels with missing keys are skipped automatically. Keyless channels do not require credentials. API keys can also be supplied as environment variables. Set a strong `CONFIG_ADMIN_PASSWORD` to log in to the configuration page; keys entered there are stored in the ignored, owner-only `.api_keys.json` file. Use HTTPS when accessing the service over a network.

### 3. Start the server

```bash
python server.py
```

The default address is `http://localhost:8200`. Open it to use the search page; API documentation is available at `/docs`. You can also search from the CLI:

```bash
python run_search.py "RISC-V vector extension"
python run_search.py "LDPC decoder" --engines zhipu_pro,arxiv --top 10 --json
python run_search.py "RISC-V" --mode parallel
```

## Docker deployment

Copy the environment template and add API keys for the channels you want to use:

```bash
cp .env.example .env
# Edit .env and set keys such as ZHIPU_API_KEY, TAVILY_API_KEY, or EXA_API_KEY
```

Build and start the container from the project root:

```bash
docker build -t multi-search-aggregator .
docker run -d \
  --name multi-search-aggregator \
  --restart unless-stopped \
  -p 8200:8200 \
  --env-file .env \
  multi-search-aggregator
```

`--env-file .env` injects the API configuration when the container starts; keys are not baked into the image. Open `http://localhost:8200` for the web page or connect to MCP at `http://localhost:8200/mcp`. Follow container logs with:

```bash
docker logs -f multi-search-aggregator
```

The image includes the project's Python dependencies. Optional channels that need OpenCLI, Chrome, Node/npx, or skill scripts outside this repository require those runtimes and scripts to be installed or mounted separately.

## Ranking and search modes

### Ranking

BM25 is the primary relevance signal. The final score also considers snippet quality, publication time, channel weight, cross-channel matches, and domain frequency. Chinese queries and results are tokenized with jieba; terms in `search_agg/stopwords.txt` are removed. Restart the service after editing the stopword file.

Results are interleaved across channels for variety. Within each channel, an item cannot be placed ahead of an item returned before it by that channel.

### Search modes

| Mode | Behavior |
|---|---|
| `quota_first` (default) | Randomly orders all configured, available quota-limited channels and tries them one at a time, stopping at the first channel with results. Unlimited channels run concurrently only if every quota-limited channel fails or returns no results. |
| `parallel` | Runs all enabled, configured, and non-cooled-down channels concurrently; this can increase requests to quota-limited providers. |

Consecutive failures increase cooldown exponentially up to 24 hours. Ordinary failures start at 5 minutes; recognized rate-limit or quota-exhaustion failures without `Retry-After` start at 1 hour. Provider `Retry-After` values are included, up to the 24-hour cap. A successful response, including a valid empty result, resets the consecutive-failure count. Cooldown state is held in process memory.

In `quota_first` mode, Tavily, Firecrawl keyless, and Keenable keyless are treated as quota-limited channels like the keyed providers. The channel order is randomized for each search, and channels are called sequentially until one returns results. If all quota-limited channels fail or return no results, unlimited channels run concurrently. Failures still trigger cooldowns for the affected channels.

## Web UI and HTTP API

| Method | Path | Description |
|---|---|---|
| `GET` | `/` | Web search page |
| `GET` | `/static/...` | Page stylesheets, scripts, and other static assets |
| `GET` / `POST` | `/api/search` | Aggregated search |
| `GET` | `/api/search/stream` | SSE search progress and results |
| `GET` | `/api/engines` | View channel enablement and configuration status |
| `POST` | `/api/engines/toggle` | Enable or disable a channel (configuration login required) |
| `GET` | `/api/config/auth/status` | Check config login status |
| `POST` | `/api/config/auth/login` / `/api/config/auth/logout` | Start or end a config session |
| `GET` / `PUT` | `/api/config` | Read or update runtime configuration (configuration login required) |
| `POST` | `/api/config/api-keys/test` | Save and test one configured API channel (configuration login required) |
| `POST` | `/api/config/reload` | Reload `config.yaml` (configuration login required) |
| `GET` | `/api/health` | Service and channel health |
| `GET` | `/docs` | FastAPI interactive API documentation |

Search API examples:

```bash
curl "http://localhost:8200/api/search?q=RISC-V&top_k=20&mode=quota_first"

curl -X POST http://localhost:8200/api/search \
  -H "Content-Type: application/json" \
  -d '{"query":"transformer attention","top_k":20,"mode":"parallel","engines":["zhipu_pro","arxiv"]}'
```

`/api/search/stream` sends SSE events such as `engine_done`, `result`, and `complete`.

## MCP interface

After starting the server, connect an MCP client to the Streamable HTTP endpoint:

```text
http://localhost:8200/mcp
```

The server exposes two tools. Their public arguments focus on searching and reading web pages; clients do not need to pass `objective`, `session_id`, or `model_name`.

### `web_search`

| Parameter | Type | Required | Default | Description |
|---|---|---:|---:|---|
| `search_queries` | `string[]` | Yes | — | One or more focused search phrases |
| `max_results` | `integer` | No | `20` | Maximum results, from 1 up to the configured service limit (200 by default) |

Returns `results`, `total_results`, and related fields. Results include a title, URL, excerpt, and channel; a publication date is included when available.

### `web_fetch`

| Parameter | Type | Required | Default | Description |
|---|---|---:|---:|---|
| `urls` | `string[]` | Yes | — | 1–20 public web page URLs; duplicates are fetched once and results follow input order |
| `search_queries` | `string[]` | No | — | Optional phrases used to select relevant excerpts |
| `full_content` | `boolean` | No | `false` | Whether to return the complete readable page text |
| `max_chars_total` | `integer` | No | `25000` | Shared character limit across all excerpts and full text; excess text is truncated |

Each page returns its URL and excerpts, with a title and full text when available and requested. A failed page includes an `error`; the response includes a `truncated` flag.

If local fetching fails, the service first sends eligible public URLs to Firecrawl's keyless scrape API, which renders pages in Firecrawl's cloud browser. Pages Firecrawl cannot fetch are sent to Parallel as a second fallback. Private, local, or otherwise unverifiable destinations are not forwarded. Both providers may impose request limits; if neither can fetch a page, its error is returned.

## Configuration

`config.yaml` controls the listen address, port, timeouts, worker count, result limit, channel weights, and enablement. API keys can come from environment variables or `.env`, or be managed in the authenticated configuration page and stored in `.api_keys.json`. Keep both secret files out of version control. The configuration page requires `CONFIG_ADMIN_PASSWORD` to be set.

```yaml
server:
  host: "0.0.0.0"
  port: 8200

search:
  default_top_k: 10
  max_top_k: 200
  default_timeout: 35

engine_overrides:
  parallel_search:
    enabled: true
```

## Project structure

```text
multi-search-aggregator/
├── server.py                    # Web UI, REST API, and /mcp server
├── mcp.py                       # web_search and web_fetch MCP tools
├── verify_mcp.py                # MCP endpoint and public-schema checker
├── Dockerfile                   # Container image definition
├── .dockerignore                # Excludes secrets and local build artifacts
├── run_search.py                # CLI search entry point
├── config.yaml                  # Server and channel configuration
├── static/                      # Web page and static assets
└── search_agg/
    ├── runner.py                # Channel scheduling and search modes
    ├── ranker.py                # Deduplication, BM25, and result ranking
    ├── stopwords.txt            # Chinese search stopwords
    └── engines/                  # Search channel implementations
```

## Contributing and license

Issues, fixes, and new channel implementations are welcome. This project is licensed under the [MIT License](LICENSE).
