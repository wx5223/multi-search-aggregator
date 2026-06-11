"""Z.AI REST API (MCP Streamable HTTP) 引擎"""
import json
import requests
from ..config import ZAI_KEY, TIMEOUT


def call_zai_api(query: str, count: int = 10, timeout: int = TIMEOUT) -> list[dict]:
    """Z.AI Web Search MCP Streamable HTTP 直连

    REST API 返回 429 余额不足，但 MCP 端点可用。
    关键：init 后必须带 mcp-session-id header
    """
    if not ZAI_KEY:
        return []

    url = "https://api.z.ai/api/mcp/web_search_prime/mcp"
    headers = {
        "Authorization": f"Bearer {ZAI_KEY}",
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
    }

    s = requests.Session()
    s.headers.update(headers)

    # 1. Initialize
    try:
        r = s.post(
            url,
            json={
                "jsonrpc": "2.0",
                "method": "initialize",
                "id": 0,
                "params": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {},
                    "clientInfo": {"name": "search-agg", "version": "8.0"},
                },
            },
            timeout=timeout,
        )
        if r.status_code != 200:
            return []
    except Exception:
        return []

    # 拿 mcp-session-id
    sid = r.headers.get("mcp-session-id")
    if sid:
        s.headers["mcp-session-id"] = sid

    # 2. Notification
    try:
        s.post(
            url,
            json={"jsonrpc": "2.0", "method": "notifications/initialized"},
            timeout=5,
        )
    except Exception:
        pass

    # 3. Tool call
    try:
        r2 = s.post(
            url,
            json={
                "jsonrpc": "2.0",
                "method": "tools/call",
                "id": 1,
                "params": {
                    "name": "web_search_prime",
                    "arguments": {"search_query": query, "count": count},
                },
            },
            timeout=timeout,
        )
    except Exception:
        return []

    if r2.status_code != 200:
        return []

    # 4. Parse response (SSE 格式)
    text = r2.text
    for line in text.split("\n"):
        line = line.strip()
        if line.startswith("data:"):
            try:
                payload = json.loads(line[5:])
                if "result" in payload:
                    for c in payload["result"].get("content", []):
                        t = c.get("text", "")
                        if t and "error" not in t[:30].lower():
                            parsed = json.loads(t)
                            if isinstance(parsed, str):
                                # 双重 JSON 编码
                                parsed = json.loads(parsed)
                            if isinstance(parsed, list):
                                return parsed
            except (json.JSONDecodeError, ValueError):
                continue
    return []
