<div align="center">

# 🔍 Multi-Search Aggregator

**35+ search engines in parallel — one query, comprehensive results from across the web.**

[![English](https://img.shields.io/badge/English-DBEDFA)](./README.md)
[![简体中文](https://img.shields.io/badge/简体中文-DFE0E5)](./README_zh.md)

[![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Engines](https://img.shields.io/badge/Engines-33%2B-orange.svg)]()

</div>

---

<details open>
<summary><b>📕 Table of Contents</b></summary>

- [💡 What is this?](#-what-is-this)
- [✨ Key Features](#-key-features)
- [📡 Supported Engines](#-supported-engines)
- [🚀 Quick Start](#-quick-start)
- [⚙️ Configuration](#-configuration)
- [🌐 Web UI & API](#-web-ui--api)
- [🧩 Extending](#-extending)
- [📁 Project Structure](#-project-structure)
- [🤝 Contributing](#-contributing)
- [📄 License](#-license)

</details>

---

## 💡 What is this?

A **parallel search aggregator** that fires queries to 35+ search engines simultaneously, deduplicates results, ranks by relevance, and returns the best matches — designed specifically for AI agents and research workflows.

Instead of calling one search API and hoping for the best, this tool combines results from multiple sources with intelligent scoring:

- **Quota-first mode** — Try one metered provider; return on a hit, otherwise fall back concurrently
- **Smart ranking** — Keyword relevance + engine authority + recency + semantic vector similarity
- **Real-time progress** — SSE streaming shows each engine completing as it happens
- **Pluggable engines** — Add new search backends without touching core code

## ✨ Key Features

- ⚡ **Two search modes** — Quota-first reduces paid requests; full parallel runs all configured engines
- 🧠 **Intelligent ranking** — Multi-signal scoring: keyword match + engine weight + freshness + vector similarity
- 🔄 **Auto-dedup** — URL normalization removes duplicates across engines
- 📡 **SSE streaming** — Real-time progress in browser, each engine reports as it finishes
- 🖥️ **Web UI** — Google-style search page with engine filter sidebar
- 🚀 **REST API** — Simple JSON endpoint for programmatic access
- 🔌 **35+ engines** — From Google to arXiv to Hacker News to Zhihu
- ⚙️ **Hot config** — Enable/disable engines, adjust weights, all without restart
- 🛡️ **Graceful degradation** — Key-required engines are skipped when unconfigured; Tavily keyless and Parallel Search channels work without keys.

## 📡 Supported Engines

| Category | Engines |
|----------|---------|
| **General Search** | Google, Bing (CN + Global), 360 Search, Sogou, Startpage, Brave, Qwant |
| **Academic** | arXiv, OpenAlex, OpenReview, DBLP, AMiner (Papers + Patents) |
| **Developer** | Stack Overflow, npm, crates.io, MDN |
| **Social** | Reddit, Hacker News, Zhihu, Xiaohongshu |
| **AI & Search Aggregators** | Zhipu AI (Pro/Sogou/Quark), Z.AI, Bailian, Tavily (keyless + API key), Exa, Firecrawl, Brave Search API, Baidu Qianfan AI Search, Doubao Search, Parallel Search |
| **Chinese** | WeChat Search, Zhihu, Baidu, WeRead |
| **Browser** | Any site via OpenCLI browser automation |
| **Custom** | Add your own via MCP, skill scripts, or web_fetch |

## 🚀 Quick Start

### 1. Install

```bash
git clone https://github.com/yourname/multi-search-aggregator.git
cd multi-search-aggregator
pip install -r requirements.txt
```

### 2. Configure API Keys

```bash
cp .env.example .env
# Edit .env — add keys for engines you want to use:
# ZHIPU_API_KEY=your_key_here
# ZAI_API_KEY=your_key_here
# BAILIAN_API_KEY=your_key_here
# TAVILY_API_KEY=your_key_here  # optional authenticated Tavily channel
# EXA_API_KEY=your_key_here
# FIRECRAWL_API_KEY=your_key_here
# BRAVE_SEARCH_API_KEY=your_key_here
# BAIDU_QIANFAN_API_KEY=your_key_here
# DOUBAO_SEARCH_API_KEY=your_key_here
# (No key = engine skipped, no errors)
```

Tavily is available as separate keyless (`tavily`) and authenticated (`tavily_key`) channels. Exa, Firecrawl, Brave Search API, Baidu Qianfan AI Search, and Doubao Search are enabled when their keys are configured. All are quota-limited providers, so quota-first mode calls one configured limited provider and returns immediately when it finds results. Baidu's daily free allocation should be checked in its console; Doubao Search provides 500 free calls per month shared by Global and Custom, resetting on the first of each month.

### 3. Run

```bash
# CLI search
python run_search.py "RISC-V vector extension"
python run_search.py "LDPC decoder" --engines zhipu_pro,arxiv --top 10 --json
python run_search.py "RISC-V" --mode parallel  # use full parallel mode

# Web server (http://localhost:8200)
python server.py
```

Open `http://localhost:8200` → search like Google, results from 35+ engines.

Quota-first is the default: it tries one configured metered provider and returns on a hit. If that provider fails or returns no results, it is marked unavailable for five minutes and the search falls back to the other engines concurrently. Choose `mode=parallel` in the UI/API or `--mode parallel` in the CLI to run all configured engines concurrently.

## ⚙️ Configuration

```yaml
# config.yaml

# Server
server:
  host: "0.0.0.0"
  port: 8200

# Search defaults
search:
  default_top_k: 50
  max_top_k: 200
  default_timeout: 35

# Engine weights (higher = more authoritative)
weights:
  Google: 10
  Z.AI: 9
  ZhipuPro: 9
  Stack Overflow: 8
  arXiv: 8

# Disable specific engines
engine_overrides:
  some_engine_id:
    enabled: false
```

## 🌐 Web UI & API

### Search

```bash
# GET request
curl "http://localhost:8200/api/search?q=RISC-V&top_k=50"

# POST request (more options)
curl -X POST http://localhost:8200/api/search \
  -H "Content-Type: application/json" \
  -d '{"query": "transformer attention", "top_k": 20, "engines": ["zhipu_pro", "arxiv"]}'

# Response:
# {
#   "results": [
#     {"title": "...", "url": "...", "summary": "...", "source": "arXiv", "score": 0.95},
#     ...
#   ],
#   "meta": {"engines_used": 15, "total_results": 234, "elapsed_ms": 3200}
# }
```

### SSE Streaming (real-time progress)

```javascript
const es = new EventSource('/api/search/stream?q=RISC-V');
es.addEventListener('engine_done', e => {
    console.log(`✅ ${JSON.parse(e.data).engine}: ${JSON.parse(e.data).results} results`);
});
es.addEventListener('complete', e => {
    const data = JSON.parse(e.data);
    console.log(`Done: ${data.total_results} results in ${data.elapsed_ms}ms`);
});
```

### Config & Engine Management

```bash
# List engines and their status
curl http://localhost:8200/api/engines

# Toggle engine on/off
curl -X POST http://localhost:8200/api/engines/toggle \
  -d '{"engine_id": "google", "enabled": false}'

# Get/update config
curl http://localhost:8200/api/config
curl -X PUT http://localhost:8200/api/config -d '{"timeout": 20}'
```

## 🧩 Extending

Adding a new engine is straightforward:

1. Create `search_agg/engines/my_engine.py`
2. Implement `call_my_engine(query: str) -> list[dict]`
3. Register in `search_agg/engines/__init__.py`

```python
# search_agg/engines/my_engine.py
def call_my_engine(query: str) -> list[dict]:
    """Must return list of dicts with: title, url, summary"""
    import requests
    resp = requests.get(f"https://api.example.com/search?q={query}")
    return resp.json().get("results", [])
```

```python
# In search_agg/engines/__init__.py, add to ENGINES list:
{
    "id": "my_engine",
    "name": "My Engine",
    "type": "web_fetch",
    "url_tpl": "https://api.example.com/search?q={q}",
    "weight": 7,
}
```

## 📁 Project Structure

```
multi-search-aggregator/
├── server.py                    # FastAPI web server
├── run_search.py                # CLI entry point
├── config.yaml                  # Configuration
│
├── search_agg/
│   ├── __init__.py              # Public API: search(), aggregate()
│   ├── config.py                # Config loader + env vars
│   ├── models.py                # SearchResult data model
│   ├── runner.py                # Parallel engine dispatcher
│   ├── ranker.py                # Dedup + scoring + vector ranking
│   ├── utils.py                 # URL cleanup, process management
│   └── engines/
│       ├── __init__.py          # Engine registry (31 engines)
│       ├── zhipu.py             # Zhipu AI (Pro/Sogou/Quark)
│       ├── zai.py               # Z.AI REST API
│       ├── bailian.py           # Alibaba Bailian MCP
│       ├── opencli.py           # Browser automation engines
│       ├── web_fetch.py         # HTTP fetch + HTML parsers
│       ├── mcp_stdio.py         # MCP stdio protocol
│       └── skill.py             # External script engines
│
├── static/                      # Web UI
│   ├── index.html               # Search page (SSE progress)
│   ├── config.html              # Engine config dashboard
│   └── style.css
│
├── requirements.txt
├── .env.example
├── .gitignore
├── LICENSE
└── README.md
```

## 🤝 Contributing

New engines, bug fixes, and improvements are welcome!

1. Fork the repo
2. Create a feature branch
3. Add your engine or fix
4. Open a PR

## 📄 License

[MIT License](LICENSE) — use it however you want.
