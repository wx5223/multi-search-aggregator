#!/usr/bin/env python3
"""Validate the Streamable HTTP MCP endpoint and its public tool schemas.

By default this only initializes an MCP session and lists tools. Use
``--search-query`` or ``--fetch-url`` to explicitly invoke a live tool.

Examples:
    python verify_mcp.py
    python verify_mcp.py --url http://127.0.0.1:8200/mcp
    python verify_mcp.py --search-query "Python 3.14 release date"
    python verify_mcp.py --fetch-url https://example.org/
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path
import traceback
from typing import Any


PROJECT_DIR = Path(__file__).resolve().parent

# This repository has a top-level mcp.py shim. Keep the project directory off
# the SDK import path so this script always loads the installed MCP package.
sys.path[:] = [
    entry
    for entry in sys.path
    if Path(entry or ".").resolve() != PROJECT_DIR
]

try:
    from mcp.client.session import ClientSession
    from mcp.client.streamable_http import streamablehttp_client
except ImportError as exc:
    raise SystemExit(
        "找不到 MCP Python SDK。请先安装项目依赖：pip install -r requirements.txt"
    ) from exc


EXPECTED_TOOLS = {
    "web_search": {"required": {"search_queries"}},
    "web_fetch": {"required": {"urls"}},
}
FORBIDDEN_ARGUMENTS = {
    "web_search": {"session_id", "model_name", "objective"},
    "web_fetch": {"session_id", "model_name", "objective"},
}


def get_tool_schema(tool: Any) -> dict[str, Any]:
    """Read the SDK's aliased or Python-style input schema field."""
    schema = getattr(tool, "inputSchema", None)
    if schema is None:
        schema = getattr(tool, "input_schema", None)
    if hasattr(schema, "model_dump"):
        schema = schema.model_dump(by_alias=True)
    return schema if isinstance(schema, dict) else {}


def get_tool_payload(result: Any) -> dict[str, Any]:
    """Unwrap structured MCP tool output, accepting JSON text as fallback."""
    if getattr(result, "isError", getattr(result, "is_error", False)):
        raise RuntimeError(f"MCP tool returned an error: {result}")

    structured = getattr(result, "structuredContent", None)
    if structured is None:
        structured = getattr(result, "structured_content", None)
    if isinstance(structured, dict):
        return structured

    for block in getattr(result, "content", []) or []:
        if getattr(block, "type", None) != "text":
            continue
        try:
            payload = json.loads(block.text)
        except (AttributeError, json.JSONDecodeError):
            continue
        if isinstance(payload, dict):
            return payload
    raise RuntimeError("MCP 工具没有返回可识别的 JSON 对象")


def validate_tools(tools: list[Any]) -> dict[str, Any]:
    tool_map = {tool.name: tool for tool in tools}
    missing = sorted(set(EXPECTED_TOOLS) - set(tool_map))
    if missing:
        raise RuntimeError(f"缺少 MCP 工具：{', '.join(missing)}")

    report: dict[str, Any] = {}
    for name, expected in EXPECTED_TOOLS.items():
        tool = tool_map[name]
        schema = get_tool_schema(tool)
        properties = schema.get("properties", {})
        required = set(schema.get("required", []))
        missing_required = expected["required"] - required
        if missing_required:
            raise RuntimeError(
                f"工具 {name} 的 required 参数不完整："
                f"{', '.join(sorted(missing_required))}"
            )

        forbidden = FORBIDDEN_ARGUMENTS[name] & set(properties)
        if forbidden:
            raise RuntimeError(
                f"工具 {name} 暴露了不应出现在接口中的参数："
                f"{', '.join(sorted(forbidden))}"
            )

        if name == "web_search":
            max_results_schema = properties.get("max_results")
            if not isinstance(max_results_schema, dict):
                raise RuntimeError("工具 web_search 缺少 max_results 参数")
            if max_results_schema.get("type") != "integer":
                raise RuntimeError("web_search.max_results 必须是 integer")
            if max_results_schema.get("default") != 20:
                raise RuntimeError("web_search.max_results 默认值必须为 20")
            if "max_results" in required:
                raise RuntimeError("web_search.max_results 应为可选参数")
        elif name == "web_fetch":
            max_chars_schema = properties.get("max_chars_total")
            if not isinstance(max_chars_schema, dict):
                raise RuntimeError("工具 web_fetch 缺少 max_chars_total 参数")
            if max_chars_schema.get("type") != "integer":
                raise RuntimeError("web_fetch.max_chars_total 必须是 integer")
            if max_chars_schema.get("default") != 25000:
                raise RuntimeError("web_fetch.max_chars_total 默认值必须为 25000")
            if "max_chars_total" in required:
                raise RuntimeError("web_fetch.max_chars_total 应为可选参数")

        description = getattr(tool, "description", None)
        if not description or not description.strip():
            raise RuntimeError(f"工具 {name} 缺少说明文本")

        report[name] = {
            "required": sorted(required),
            "parameters": sorted(properties),
            "description": description.strip(),
            "max_results_default": (
                properties["max_results"].get("default")
                if name == "web_search"
                else None
            ),
            "max_chars_total_default": (
                properties["max_chars_total"].get("default")
                if name == "web_fetch"
                else None
            ),
        }
    return report


async def verify(args: argparse.Namespace) -> None:
    async with streamablehttp_client(args.url) as (read_stream, write_stream, _):
        async with ClientSession(read_stream, write_stream) as session:
            init_result = await session.initialize()
            tools_result = await session.list_tools()
            tools = list(tools_result.tools)
            report = validate_tools(tools)

            print(f"MCP 握手成功：{args.url}")
            server_info = getattr(init_result, "serverInfo", None)
            if server_info is None:
                server_info = getattr(init_result, "server_info", None)
            if server_info is not None:
                server_name = getattr(server_info, "name", None)
                server_version = getattr(server_info, "version", None)
                print(f"服务：{server_name or 'unknown'} {server_version or ''}".strip())
            print("工具列表与参数 schema 验证通过：")
            for name, details in report.items():
                print(
                    f"  - {name}: required={details['required']}; "
                    f"parameters={details['parameters']}"
                )

            if args.search_query:
                result = await session.call_tool(
                    "web_search",
                    {
                        "search_queries": [args.search_query],
                        "max_results": args.max_results,
                    },
                )
                payload = get_tool_payload(result)
                if not isinstance(payload.get("results"), list):
                    raise RuntimeError("web_search 返回结果缺少 results 列表")
                if len(payload["results"]) > args.max_results:
                    raise RuntimeError(
                        f"web_search 返回 {len(payload['results'])} 条，"
                        f"超过 max_results={args.max_results}"
                    )
                total = payload.get("total_results", len(payload["results"]))
                print(
                    f"web_search 调用成功：返回 {len(payload['results'])} 条，"
                    f"total_results={total}"
                )

            if args.fetch_url:
                result = await session.call_tool(
                    "web_fetch",
                    {
                        "urls": [args.fetch_url],
                        "full_content": False,
                        "max_chars_total": args.max_chars_total,
                    },
                )
                payload = get_tool_payload(result)
                pages = payload.get("results")
                if not isinstance(pages, list) or not pages:
                    raise RuntimeError("web_fetch 返回结果缺少 results 页面列表")
                if not isinstance(payload.get("truncated"), bool):
                    raise RuntimeError("web_fetch 返回结果缺少 truncated 标记")
                text_char_count = sum(
                    sum(len(excerpt) for excerpt in page.get("excerpts", []))
                    + len(page.get("full_content", ""))
                    for page in pages
                )
                if text_char_count > args.max_chars_total:
                    raise RuntimeError(
                        f"web_fetch 返回文本共 {text_char_count} 个字符，"
                        f"超过 max_chars_total={args.max_chars_total}"
                    )
                page = pages[0]
                if page.get("error"):
                    raise RuntimeError(f"web_fetch 页面抓取失败：{page['error']}")
                if not isinstance(page.get("excerpts"), list):
                    raise RuntimeError("web_fetch 页面结果缺少 excerpts 列表")
                print(
                    f"web_fetch 调用成功：{page.get('title') or page.get('url')}；"
                    f"excerpts={len(page['excerpts'])}，"
                    f"text_chars={text_char_count}，"
                    f"truncated={payload['truncated']}"
                )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="检查 Multi-Search Aggregator 的 MCP Streamable HTTP 接口。"
    )
    parser.add_argument(
        "--url",
        default="http://127.0.0.1:8200/mcp",
        help="MCP endpoint URL（默认：http://127.0.0.1:8200/mcp）",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=60,
        help="整个验证过程的超时秒数（默认：60）",
    )
    parser.add_argument(
        "--search-query",
        help="可选：实际调用 web_search 验证端到端搜索，会产生搜索请求",
        default='测试内容'
    )
    parser.add_argument(
        "--max-results",
        type=int,
        default=20,
        help="传给 web_search 的最大结果数（默认：20）",
    )
    parser.add_argument(
        "--fetch-url",
        help="可选：实际调用 web_fetch 验证指定页面抓取",
        default='https://www.baidu.com'
    )
    parser.add_argument(
        "--max-chars-total",
        type=int,
        default=25000,
        help="传给 web_fetch 的总文本字符上限（默认：25000）",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        asyncio.run(asyncio.wait_for(verify(args), timeout=args.timeout))
    except asyncio.TimeoutError:
        print(f"验证失败：超过 {args.timeout:g} 秒超时", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("验证已取消", file=sys.stderr)
        return 130
    except Exception as exc:
        print('error:', traceback.format_exc())
        print(f"验证失败：{exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
