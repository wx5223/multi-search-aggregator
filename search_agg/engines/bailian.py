"""百炼 MCP JSON-RPC 直连引擎"""
import json
import requests
from ..config import BAILIAN_KEY, TIMEOUT


def call_bailian_mcp(query: str, count: int = 10, timeout: int = TIMEOUT) -> list[dict]:
    """百炼 WebSearch MCP Streamable HTTP 直连"""
    if not BAILIAN_KEY:
        return []

    url = "https://dashscope.aliyuncs.com/api/v1/mcps/WebSearch/mcp"
    headers = {
        "Authorization": f"Bearer {BAILIAN_KEY}",
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

    # 2. Notification
    s.post(
        url,
        json={"jsonrpc": "2.0", "method": "notifications/initialized"},
        timeout=5,
    )

    # 3. Tool call
    r2 = s.post(
        url,
        json={
            "jsonrpc": "2.0",
            "method": "tools/call",
            "id": 1,
            "params": {
                "name": "bailian_web_search",
                "arguments": {"query": query, "count": count},
            },
        },
        timeout=timeout,
    )
    r2.raise_for_status()

    # 4. Parse response (支持 SSE 和纯 JSON 两种格式)
    text = r2.text.strip()

    # 尝试 SSE 格式 (data: {...})
    for line in text.split("\n"):
        line = line.strip()
        if line.startswith("data:"):
            try:
                payload = json.loads(line[5:])
                if payload.get("error"):
                    raise RuntimeError("Bailian MCP returned a tool error")
                if "result" in payload:
                    for c in payload["result"].get("content", []):
                        t = c.get("text", "")
                        if t:
                            if t.lower().startswith("no results"):
                                return []
                            parsed = json.loads(t)
                            if isinstance(parsed, dict):
                                pages = parsed.get("pages")
                                if isinstance(pages, list):
                                    return pages
                                raise ValueError("Bailian MCP returned an invalid pages list")
                            elif isinstance(parsed, list):
                                return parsed
                            raise ValueError("Bailian MCP returned an invalid result")
            except json.JSONDecodeError:
                continue

    # 尝试纯 JSON 格式
    try:
        payload = json.loads(text)
        if payload.get("error"):
            raise RuntimeError("Bailian MCP returned a tool error")
        if "result" in payload:
            for c in payload["result"].get("content", []):
                t = c.get("text", "")
                if t:
                    if t.lower().startswith("no results"):
                        return []
                    parsed = json.loads(t)
                    if isinstance(parsed, dict):
                        pages = parsed.get("pages")
                        if isinstance(pages, list):
                            return pages
                        raise ValueError("Bailian MCP returned an invalid pages list")
                    elif isinstance(parsed, list):
                        return parsed
                    raise ValueError("Bailian MCP returned an invalid result")
    except json.JSONDecodeError as exc:
        raise ValueError("Bailian MCP returned an invalid response") from exc

    raise ValueError("Bailian MCP returned no parseable search result")
