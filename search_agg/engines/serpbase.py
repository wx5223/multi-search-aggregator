"""SerpBase REST API engine — Google Search Results via serpbase.dev"""
import os
import requests
from ..config import TIMEOUT

API_URL = "https://api.serpbase.dev/google/search"


def call_serpbase_api(query: str, count: int = 10, timeout: int = TIMEOUT) -> list[dict]:
    """Query SerpBase Google Search API.

    Returns structured Google results as list of dicts with
    title, link, snippet, position fields.
    Gracefully returns [] when SERPBASE_API_KEY is not set.
    """
    api_key = os.environ.get("SERPBASE_API_KEY", "")
    if not api_key:
        return []

    response = requests.get(
        API_URL,
        params={
            "q": query,
            "num": count,
            "api_key": api_key,
        },
        timeout=timeout,
    )
    response.raise_for_status()
    data = response.json()
    if not isinstance(data, dict) or not isinstance(data.get("organic_results"), list):
        raise ValueError("SerpBase returned an invalid response")
    return data["organic_results"]
