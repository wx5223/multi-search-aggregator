"""Parallel Search MCP client (free anonymous endpoint)."""
import asyncio
import json
import uuid

PARALLEL_MCP_URL = "https://search.parallel.ai/mcp"


async def _call_parallel_mcp(query: str, timeout: int) -> list[dict]:
    from mcp import ClientSession
    from mcp.client.streamable_http import streamablehttp_client

    async with streamablehttp_client(
        PARALLEL_MCP_URL,
        timeout=timeout,
        sse_read_timeout=timeout,
    ) as (read_stream, write_stream, _):
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()
            result = await session.call_tool(
                "web_search",
                {
                    "objective": query,
                    "search_queries": [query],
                    "session_id": str(uuid.uuid4()),
                },
            )

    if getattr(result, "isError", False):
        return []

    payload = getattr(result, "structuredContent", None)
    if payload is None:
        payload = getattr(result, "structured_content", None)
    if payload is None:
        for block in getattr(result, "content", []):
            text = getattr(block, "text", "")
            if not text:
                continue
            try:
                payload = json.loads(text)
                if isinstance(payload, str):
                    payload = json.loads(payload)
                break
            except (json.JSONDecodeError, TypeError):
                continue

    if isinstance(payload, str):
        try:
            payload = json.loads(payload)
        except json.JSONDecodeError:
            return []
    if isinstance(payload, dict):
        payload = payload.get("results", [])
    if not isinstance(payload, list):
        return []

    normalized = []
    for item in payload:
        if not isinstance(item, dict):
            continue
        excerpts = item.get("excerpts", [])
        summary = item.get("content", "")
        if not summary and isinstance(excerpts, list):
            summary = " ".join(str(excerpt) for excerpt in excerpts)
        normalized.append({
            "title": item.get("title", ""),
            "url": item.get("url", ""),
            "content": summary,
            "publish_time": item.get("publish_date"),
        })
    return normalized


def call_parallel_search(query: str, timeout: int = 35) -> list[dict]:
    """Call Parallel's anonymous, free Search MCP endpoint."""
    try:
        return asyncio.run(_call_parallel_mcp(query, timeout))
    except Exception:
        return []
