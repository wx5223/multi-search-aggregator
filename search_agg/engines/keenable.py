"""Keenable web search API client."""
import os

import requests

from ..config import TIMEOUT


def call_keenable(
    query: str,
    count: int = 10,
    timeout: int = TIMEOUT,
    keyless: bool = False,
) -> list[dict]:
    """Search with Keenable's public or API-key endpoint."""
    api_key = "" if keyless else os.environ.get("KEENABLE_API_KEY", "").strip()
    if not keyless and not api_key:
        return []

    base_url = os.environ.get("KEENABLE_API_URL", "https://api.keenable.ai").rstrip("/")
    endpoint = "/v1/search/public" if keyless else "/v1/search"
    headers = {"Content-Type": "application/json"}
    if keyless:
        # Keenable requires an app identifier on its unauthenticated endpoint.
        headers["X-Keenable-Title"] = "Multi-Search Aggregator"
    else:
        headers["X-API-Key"] = api_key

    response = requests.post(
        f"{base_url}{endpoint}",
        headers=headers,
        json={"query": query, "mode": "pro", "max_results": min(max(count, 1), 50)},
        timeout=timeout,
    )
    response.raise_for_status()
    payload = response.json()
    results = payload.get("results") if isinstance(payload, dict) else None
    if not isinstance(results, list):
        raise ValueError("Keenable returned an invalid response")

    normalized = []
    for item in results:
        if not isinstance(item, dict):
            continue
        normalized.append({
            "title": item.get("title", ""),
            "url": item.get("url", ""),
            "content": item.get("snippet") or item.get("description", ""),
            "publish_time": item.get("published_at"),
        })
    return normalized
