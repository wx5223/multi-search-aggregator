"""SerpBase REST API engine — Google Search Results via serpbase.dev"""
import requests
from ..config import SERPBASE_KEY, TIMEOUT

API_URL = "https://api.serpbase.dev/google/search"


def call_serpbase_api(query: str, count: int = 10, timeout: int = TIMEOUT) -> list[dict]:
    """Query SerpBase Google Search API.

    Returns structured Google results as list of dicts with
    title, link, snippet, position fields.
    Gracefully returns [] when SERPBASE_API_KEY is not set.
    """
    if not SERPBASE_KEY:
        return []

    try:
        r = requests.get(
            API_URL,
            params={
                "q": query,
                "num": count,
                "api_key": SERPBASE_KEY,
            },
            timeout=timeout,
        )
        if r.status_code != 200:
            return []
        data = r.json()
        return data.get("organic_results", [])
    except Exception:
        return []
