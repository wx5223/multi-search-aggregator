"""Brave Search API client."""
import os
import requests

from ..config import TIMEOUT


def call_brave_search(query: str, count: int = 10, timeout: int = TIMEOUT) -> list[dict]:
    api_key = os.environ.get("BRAVE_SEARCH_API_KEY", "")
    if not api_key:
        return []

    response = requests.get(
        "https://api.search.brave.com/res/v1/web/search",
        headers={"Accept": "application/json", "X-Subscription-Token": api_key},
        params={"q": query, "count": min(count, 20)},
        timeout=timeout,
    )
    response.raise_for_status()
    data = response.json()
    web = data.get("web", {}) if isinstance(data, dict) else {}
    results = web.get("results", []) if isinstance(web, dict) else []
    return [
        {
            "title": item.get("title", ""),
            "url": item.get("url", ""),
            "content": item.get("description", ""),
            "publish_time": item.get("page_age"),
        }
        for item in results
        if isinstance(item, dict)
    ]
