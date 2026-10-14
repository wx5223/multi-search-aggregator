"""Baidu Qianfan AI Search API client."""
import os
import requests

from ..config import TIMEOUT


def call_baidu_qianfan_search(
    query: str, count: int = 10, timeout: int = TIMEOUT
) -> list[dict]:
    api_key = os.environ.get("BAIDU_QIANFAN_API_KEY", "")
    if not api_key:
        return []

    response = requests.post(
        "https://qianfan.baidubce.com/v2/ai_search/web_search",
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json={
            "messages": [{"role": "user", "content": query}],
            "search_source": "baidu_search_v2",
            "edition": "standard",
            "resource_type_filter": [{"type": "web", "top_k": min(count, 50)}],
        },
        timeout=timeout,
    )
    response.raise_for_status()
    data = response.json()
    if not isinstance(data, dict):
        raise ValueError("Baidu Qianfan returned an invalid response")
    if data.get("code") and str(data["code"]) != "0":
        raise RuntimeError(f"Baidu Qianfan search failed: {data.get('message', data['code'])}")

    references = data.get("references")
    if not isinstance(references, list):
        raise ValueError("Baidu Qianfan returned an invalid references list")
    return [
        {
            "title": item.get("title", ""),
            "url": item.get("url", ""),
            "content": item.get("snippet") or item.get("content", ""),
            "publish_time": item.get("date"),
        }
        for item in references
        if isinstance(item, dict) and item.get("type", "web") == "web"
    ]
