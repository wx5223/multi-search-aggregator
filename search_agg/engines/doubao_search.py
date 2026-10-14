"""Volcengine Doubao Search Custom API client."""
import os
import requests

from ..config import TIMEOUT


def call_doubao_search(
    query: str, count: int = 10, timeout: int = TIMEOUT
) -> list[dict]:
    api_key = os.environ.get("DOUBAO_SEARCH_API_KEY", "")
    if not api_key:
        return []

    response = requests.post(
        "https://open.feedcoopapi.com/search_api/web_search",
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json={
            "Query": query[:100],
            "SearchType": "web",
            "Count": min(count, 50),
            "Filter": {"NeedContent": False, "NeedUrl": True},
        },
        timeout=timeout,
    )
    response.raise_for_status()
    data = response.json()
    if not isinstance(data, dict):
        raise ValueError("Doubao Search returned an invalid response")

    result = data.get("Result")
    if not isinstance(result, dict):
        raise ValueError("Doubao Search returned an invalid result object")
    if result.get("ErrorCode") and str(result["ErrorCode"]) != "0":
        raise RuntimeError(f"Doubao Search failed: {result.get('ErrorMsg', result['ErrorCode'])}")
    results = result.get("WebResults")
    if not isinstance(results, list):
        raise ValueError("Doubao Search returned an invalid web results list")
    return [
        {
            "title": item.get("Title", ""),
            "url": item.get("Url", ""),
            "content": item.get("Summary") or item.get("Snippet") or item.get("Content", ""),
            "publish_time": item.get("PublishTime"),
        }
        for item in results
        if isinstance(item, dict)
    ]
