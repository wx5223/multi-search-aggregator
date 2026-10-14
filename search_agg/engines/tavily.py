"""Tavily Search API (keyless and API-key modes)."""
import os
import requests
from ..config import TIMEOUT


def _call_tavily(query: str, headers: dict, count: int, timeout: int) -> list[dict]:
    response = requests.post(
        "https://api.tavily.com/search",
        headers=headers,
        json={
            "query": query,
            "search_depth": "basic",
            "max_results": min(count, 20),
            "include_answer": False,
            "include_raw_content": False,
        },
        timeout=timeout,
    )
    response.raise_for_status()
    data = response.json()
    if not isinstance(data, dict) or not isinstance(data.get("results"), list):
        raise ValueError("Tavily returned an invalid response")
    return [
        {
            "title": item.get("title", ""),
            "url": item.get("url", ""),
            "content": item.get("content", ""),
            "publish_time": item.get("published_date"),
        }
        for item in data.get("results", [])
    ]


def call_tavily(query: str, count: int = 10, timeout: int = TIMEOUT) -> list[dict]:
    """Call Tavily Search using its free, rate-limited keyless access."""
    return _call_tavily(
        query,
        {"Content-Type": "application/json", "X-Tavily-Access-Mode": "keyless"},
        count,
        timeout,
    )


def call_tavily_key(query: str, count: int = 10, timeout: int = TIMEOUT) -> list[dict]:
    """Call the separately authenticated Tavily Search API channel."""
    api_key = os.environ.get("TAVILY_API_KEY", "")
    if not api_key:
        return []
    return _call_tavily(
        query,
        {"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"},
        count,
        timeout,
    )
