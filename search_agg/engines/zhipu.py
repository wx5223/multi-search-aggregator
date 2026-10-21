"""智谱 REST API 引擎（Pro / Sogou / Quark）"""
import os
import requests
from ..config import TIMEOUT


def call_zhipu_api(engine_code: str, query: str, count: int = 10, timeout: int = TIMEOUT) -> list[dict]:
    """智谱 Web Search REST API 直连"""
    api_key = os.environ.get("ZHIPU_API_KEY", "")
    if not api_key:
        return []
    url = "https://open.bigmodel.cn/api/paas/v4/web_search"
    r = requests.post(
        url,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json={
            "search_query": query,
            "search_engine": engine_code,
            "search_intent": False,  # 跳过意图识别，直接搜索
            "count": count,
        },
        timeout=timeout,
    )
    r.raise_for_status()
    data = r.json()
    if not isinstance(data, dict) or not isinstance(data.get("search_result"), list):
        raise ValueError("Zhipu Search returned an invalid response")
    return data["search_result"]
