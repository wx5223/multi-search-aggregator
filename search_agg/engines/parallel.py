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

    if getattr(result, "isError", getattr(result, "is_error", False)):
        raise RuntimeError("Parallel Search MCP returned a tool error")

    payload = getattr(result, "structuredContent", None)
    if payload is None:
        payload = getattr(result, "structured_content", None)
    if payload is None:
        for block in getattr(result, "content", []):
            text = getattr(block, "text", "")
            if not text:
                continue
            if text.strip().lower().startswith("no results"):
                return []
            try:
                payload = json.loads(text)
                if isinstance(payload, str):
                    payload = json.loads(payload)
                break
            except (json.JSONDecodeError, TypeError):
                continue

    if isinstance(payload, str) and payload.strip().lower().startswith("no results"):
        return []
    if isinstance(payload, str):
        try:
            payload = json.loads(payload)
        except json.JSONDecodeError as exc:
            raise ValueError("Parallel Search MCP returned invalid JSON") from exc
    if isinstance(payload, dict):
        payload = payload.get("results")
    if not isinstance(payload, list):
        raise ValueError("Parallel Search MCP returned no result list")

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
    return asyncio.run(_call_parallel_mcp(query, timeout))


def _tool_result_payload(result):
    if getattr(result, "isError", getattr(result, "is_error", False)):
        return None

    payload = getattr(result, "structuredContent", None)
    if payload is None:
        payload = getattr(result, "structured_content", None)
    if payload is not None:
        return payload

    for block in getattr(result, "content", []) or []:
        text = getattr(block, "text", "")
        if not text:
            continue
        try:
            payload = json.loads(text)
        except (json.JSONDecodeError, TypeError):
            continue
        if isinstance(payload, str):
            try:
                payload = json.loads(payload)
            except json.JSONDecodeError:
                continue
        return payload
    return None


def _normalize_parallel_fetch(payload, urls: list[str], full_content: bool) -> list[dict]:
    if isinstance(payload, str):
        try:
            payload = json.loads(payload)
        except json.JSONDecodeError:
            payload = [{"content": payload}] if len(urls) == 1 else []
    if isinstance(payload, dict):
        pages = payload.get("results", payload.get("pages"))
        if pages is None:
            pages = [payload] if any(
                key in payload for key in ("url", "original_url", "content", "full_content", "markdown")
            ) else []
        payload = pages
    if not isinstance(payload, list):
        return []

    normalized = []
    for index, item in enumerate(payload):
        if isinstance(item, str):
            item = {"content": item}
        if not isinstance(item, dict):
            continue

        page_url = (
            item.get("url")
            or item.get("original_url")
            or (urls[index] if index < len(urls) else "")
        )
        body = (
            item.get("full_content")
            or item.get("content")
            or item.get("markdown")
            or item.get("text")
            or ""
        )
        if not isinstance(body, str):
            body = ""

        raw_excerpts = item.get("excerpts", [])
        if isinstance(raw_excerpts, str):
            raw_excerpts = [raw_excerpts]
        excerpts = []
        if isinstance(raw_excerpts, list):
            for excerpt in raw_excerpts:
                if isinstance(excerpt, dict):
                    excerpt = excerpt.get("text") or excerpt.get("content") or ""
                if isinstance(excerpt, str) and excerpt.strip():
                    excerpts.append(excerpt.strip())
        if not excerpts and body:
            excerpts = [body[:1200]]

        page = {
            "url": page_url,
            "title": item.get("title", ""),
            "excerpts": excerpts,
        }
        if full_content and body:
            page["full_content"] = body
        if item.get("error"):
            page["error"] = str(item["error"])
        normalized.append(page)
    return normalized


async def _call_parallel_fetch(
    urls: list[str],
    search_queries: list[str] | None,
    full_content: bool,
    timeout: int,
) -> list[dict]:
    from mcp import ClientSession
    from mcp.client.streamable_http import streamablehttp_client

    async with streamablehttp_client(
        PARALLEL_MCP_URL,
        timeout=timeout,
        sse_read_timeout=timeout,
    ) as (read_stream, write_stream, _):
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()
            arguments = {
                "urls": urls,
                "full_content": full_content,
                "session_id": str(uuid.uuid4()),
            }
            if search_queries:
                arguments["search_queries"] = search_queries
            result = await session.call_tool("web_fetch", arguments)

    payload = _tool_result_payload(result)
    if payload is None and len(urls) == 1:
        # Some MCP clients return plain Markdown text instead of structured
        # content. Preserve it as the result for the single requested page.
        text_content = "\n\n".join(
            getattr(block, "text", "")
            for block in getattr(result, "content", []) or []
            if getattr(block, "text", "")
        )
        if text_content:
            payload = [{"url": urls[0], "content": text_content}]
    return _normalize_parallel_fetch(payload, urls, full_content)


def call_parallel_fetch(
    urls: list[str],
    search_queries: list[str] | None = None,
    full_content: bool = False,
    timeout: int = 35,
) -> list[dict]:
    """Fetch public pages through Parallel's anonymous Search MCP endpoint."""
    if not urls:
        return []
    try:
        return asyncio.run(
            _call_parallel_fetch(urls, search_queries, full_content, timeout)
        )
    except Exception:
        return []
