"""Exa Search API client."""
import os
import requests

from ..config import TIMEOUT


def call_exa(query: str, count: int = 10, timeout: int = TIMEOUT) -> list[dict]:
    api_key = os.environ.get("EXA_API_KEY", "")
    if not api_key:
        return []

    response = requests.post(
        "https://api.exa.ai/search",
        headers={"x-api-key": api_key, "Content-Type": "application/json"},
        json={
            "query": query,
            "type": "auto",
            "numResults": min(count, 100),
            "contents": {"highlights": True},
        },
        timeout=timeout,
    )
    response.raise_for_status()
    data = response.json()
    results = data.get("results", []) if isinstance(data, dict) else []
    normalized = []
    for item in results:
        if not isinstance(item, dict):
            continue
        highlights = item.get("highlights") or []
        content = " ".join(str(text) for text in highlights) if isinstance(highlights, list) else str(highlights)
        normalized.append({
            "title": item.get("title", ""),
            "url": item.get("url", ""),
            "content": content or item.get("text", ""),
            "publish_time": item.get("publishedDate"),
        })
    return normalized
