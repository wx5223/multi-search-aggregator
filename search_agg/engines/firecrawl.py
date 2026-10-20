"""Firecrawl Search and scrape API client."""
import os
import requests

from ..config import TIMEOUT


def call_firecrawl(
    query: str,
    count: int = 10,
    timeout: int = TIMEOUT,
    keyless: bool = False,
) -> list[dict]:
    """Search the web with the authenticated or IP-limited keyless endpoint."""
    api_key = "" if keyless else os.environ.get("FIRECRAWL_API_KEY", "")
    if not keyless and not api_key:
        return []

    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    response = requests.post(
        "https://api.firecrawl.dev/v2/search",
        headers=headers,
        json={"query": query, "limit": min(count, 100), "sources": ["web"], "highlights": True},
        timeout=timeout,
    )
    response.raise_for_status()
    data = response.json()
    payload = data.get("data") if isinstance(data, dict) else None
    results = payload.get("web") if isinstance(payload, dict) else None
    if not isinstance(results, list):
        raise ValueError("Firecrawl returned an invalid response")
    normalized = []
    for item in results:
        if not isinstance(item, dict):
            continue
        highlights = item.get("highlights") or []
        content = " ".join(str(text) for text in highlights) if isinstance(highlights, list) else str(highlights)
        metadata = item.get("metadata")
        normalized.append({
            "title": item.get("title", ""),
            "url": item.get("url", ""),
            "content": content or item.get("description", ""),
            "publish_time": item.get("date") or (
                metadata.get("publishedTime") if isinstance(metadata, dict) else None
            ),
        })
    return normalized


def call_firecrawl_scrape(url: str, timeout: int = TIMEOUT) -> dict:
    """Scrape a page through Firecrawl's keyless browser-backed API."""
    response = requests.post(
        "https://api.firecrawl.dev/v2/scrape",
        headers={"Content-Type": "application/json"},
        json={"url": url, "formats": ["markdown"]},
        timeout=timeout,
    )
    response.raise_for_status()
    payload = response.json()
    data = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(payload, dict) or payload.get("success") is not True or not isinstance(data, dict):
        message = payload.get("error") if isinstance(payload, dict) else None
        raise ValueError(message or "Firecrawl returned an invalid scrape response")
    markdown = data.get("markdown")
    if not isinstance(markdown, str) or not markdown.strip():
        raise ValueError("Firecrawl returned no page content")
    metadata = data.get("metadata")
    return {
        "title": metadata.get("title", "") if isinstance(metadata, dict) else "",
        "markdown": markdown,
    }
