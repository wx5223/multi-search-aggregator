"""Z.AI REST API (MCP Streamable HTTP) 引擎"""
import json
import os
import requests
from ..config import TIMEOUT


def call_zai_api(query: str, count: int = 10, timeout: int = TIMEOUT) -> list[dict]:
    """Z.AI Web Search MCP Streamable HTTP 直连

    REST API 返回 429 余额不足，但 MCP 端点可用。
    关键：init 后必须带 mcp-session-id header
    """
    api_key = os.environ.get("ZAI_API_KEY", "")
    if not api_key:
        return []

    url = "https://api.z.ai/api/mcp/web_search_prime/mcp"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
    }

    s = requests.Session()
    s.headers.update(headers)

    # 1. Initialize
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
    r.raise_for_status()

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

    r2.raise_for_status()

    # 4. Parse response (SSE 格式)
    text = r2.text
    for line in text.split("\n"):
        line = line.strip()
        if line.startswith("data:"):
            try:
                payload = json.loads(line[5:])
                if payload.get("error"):
                    raise RuntimeError("Z.AI MCP returned a tool error")
                if "result" in payload:
                    for c in payload["result"].get("content", []):
                        t = c.get("text", "")
                        if t:
                            if t.lower().startswith("no results"):
                                return []
                            if "error" in t[:30].lower():
                                raise RuntimeError("Z.AI MCP returned a tool error")
                            parsed = json.loads(t)
                            if isinstance(parsed, str):
                                parsed = json.loads(parsed)
                            if isinstance(parsed, list):
                                return parsed
            except json.JSONDecodeError:
                continue
    raise ValueError("Z.AI MCP returned no parseable search result")
