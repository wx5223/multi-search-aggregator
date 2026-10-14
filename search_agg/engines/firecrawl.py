"""Firecrawl Search API client."""
import os
import requests

from ..config import TIMEOUT


def call_firecrawl(query: str, count: int = 10, timeout: int = TIMEOUT) -> list[dict]:
    api_key = os.environ.get("FIRECRAWL_API_KEY", "")
    if not api_key:
        return []

    response = requests.post(
        "https://api.firecrawl.dev/v2/search",
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json={"query": query, "limit": min(count, 100), "sources": ["web"], "highlights": True},
        timeout=timeout,
    )
    response.raise_for_status()
    data = response.json()
    payload = data.get("data", {}) if isinstance(data, dict) else {}
    results = payload.get("web", []) if isinstance(payload, dict) else []
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
