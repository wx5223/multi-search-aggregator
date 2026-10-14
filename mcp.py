"""MCP server exposing aggregator-backed ``web_search`` and ``web_fetch`` tools."""
import importlib
import ipaddress
import os
import socket
import sys
from concurrent.futures import ThreadPoolExecutor
from contextlib import redirect_stdout
from pathlib import Path
from urllib.parse import urljoin, urlsplit


_PROJECT_DIR = Path(__file__).resolve().parent


def _load_mcp_sdk():
    """Load the installed MCP package without letting this file shadow it."""
    existing = sys.modules.get("mcp")
    if existing is not None and hasattr(existing, "__path__"):
        return existing

    importing_as_sdk = __name__ == "mcp"
    if importing_as_sdk:
        sys.modules.pop("mcp", None)

    original_path = sys.path[:]
    try:
        sys.path[:] = [
            item for item in original_path
            if Path(item or os.getcwd()).resolve() != _PROJECT_DIR
        ]
        sdk = importlib.import_module("mcp")
    finally:
        sys.path[:] = original_path

    # If another project module imports ``mcp``, expose the SDK package rather
    # than this script, whose filename would otherwise shadow the dependency.
    if importing_as_sdk:
        sys.modules["mcp"] = sdk
    return sdk


_mcp_sdk = _load_mcp_sdk()

# ``mcp.py`` shares its name with the MCP SDK package. When imported by SDK
# clients, act as a transparent package shim; the server is started as a script.
if __name__ != "mcp":
    from mcp.server.fastmcp import FastMCP
    import requests
    from bs4 import BeautifulSoup

    if str(_PROJECT_DIR) not in sys.path:
        sys.path.insert(0, str(_PROJECT_DIR))

    try:
        from dotenv import load_dotenv
        load_dotenv(_PROJECT_DIR / ".env")
    except ImportError:
        pass

    from search_agg import search as aggregate_search
    from search_agg.config import MAX_TOP_K, TIMEOUT
    from search_agg.engines.parallel import call_parallel_fetch

    mcp = FastMCP("multi-search-aggregator")

    @mcp.tool()
    def web_search(
        search_queries: list[str],
        max_results: int = 20,
    ) -> dict:
        """Find useful web pages for one or more search queries.

        Provide focused phrases that describe the information you need. Use
        multiple queries when you want to explore the topic from different
        angles. Choose ``max_results`` to control how many pages are returned.

        Args:
            search_queries: One or more focused searches describing what to
                find.
            max_results: Maximum number of results to return, from 1 up to
                the service limit (default: 20).

        Returns web pages with a title, URL, excerpt, and source. A
        publication date is included when available. The response also
        includes ``total_results``.
        """
        queries = [query.strip() for query in search_queries if query.strip()]
        if not queries:
            raise ValueError("search_queries must contain at least one query")
        if not 1 <= max_results <= MAX_TOP_K:
            raise ValueError(f"max_results must be between 1 and {MAX_TOP_K}")
        query = " OR ".join(queries)

        # The aggregator prints progress for its CLI. Keep stdout clean because
        # it carries MCP's stdio JSON-RPC messages.
        with redirect_stdout(sys.stderr):
            response = aggregate_search(
                query=query,
                top_k=max_results,
                timeout=TIMEOUT,
                mode="quota_first",
            )

        results = []
        for item in response.get("results", []):
            summary = str(item.get("summary") or "").strip()
            result = {
                "title": item.get("title", ""),
                "url": item.get("url", ""),
                "excerpts": [summary] if summary else [],
                "source": item.get("source", ""),
            }
            if item.get("publish_time"):
                result["publish_date"] = item["publish_time"]
            results.append(result)

        return {
            "search_queries": queries,
            "max_results": max_results,
            "results": results,
            "total_results": response.get("meta", {}).get("total_results", len(results)),
        }

    class _UnsafePublicURL(ValueError):
        """The URL cannot safely be sent to an external fetch service."""

    def _validate_public_url(url: str) -> str:
        parsed = urlsplit(url)
        if parsed.scheme.lower() not in {"http", "https"} or not parsed.hostname:
            raise _UnsafePublicURL("Only absolute HTTP or HTTPS URLs are supported")
        if parsed.username or parsed.password:
            raise _UnsafePublicURL("URLs containing credentials are not supported")

        host = parsed.hostname.rstrip(".").lower()
        if host == "localhost" or host.endswith((".localhost", ".local", ".internal")):
            raise _UnsafePublicURL("Private and local URLs are not supported")
        try:
            port = parsed.port or (443 if parsed.scheme.lower() == "https" else 80)
        except ValueError as exc:
            raise _UnsafePublicURL("URL contains an invalid port") from exc
        try:
            addresses = {ipaddress.ip_address(host)}
        except ValueError:
            try:
                addresses = {
                    ipaddress.ip_address(info[4][0])
                    for info in socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
                }
            except (OSError, ValueError) as exc:
                raise _UnsafePublicURL("Could not verify the URL host") from exc
        if not addresses or any(not address.is_global for address in addresses):
            raise _UnsafePublicURL("Private and local URLs are not supported")
        return url

    def _fetch_page(url: str, search_queries: list[str]) -> dict:
        original_url = url
        current_url = url
        response = None
        try:
            for _ in range(6):
                current_url = _validate_public_url(current_url)
                response = requests.get(
                    current_url,
                    headers={
                        "User-Agent": "Mozilla/5.0 (compatible; MultiSearchAggregator/1.0)",
                        "Accept": "text/html,application/xhtml+xml,text/plain",
                    },
                    timeout=TIMEOUT,
                    allow_redirects=False,
                    stream=True,
                )
                if response.is_redirect or response.is_permanent_redirect:
                    location = response.headers.get("Location")
                    response.close()
                    if not location:
                        raise ValueError("Redirect response did not include a destination")
                    current_url = urljoin(current_url, location)
                    continue
                response.raise_for_status()
                content_type = response.headers.get("Content-Type", "").lower()
                if content_type and not any(
                    kind in content_type for kind in ("text/html", "application/xhtml", "text/plain")
                ):
                    raise ValueError(f"Unsupported content type: {content_type.split(';', 1)[0]}")

                body = bytearray()
                for chunk in response.iter_content(64 * 1024):
                    body.extend(chunk)
                    if len(body) > 5 * 1024 * 1024:
                        raise ValueError("Page is larger than the 5 MiB fetch limit")
                response.encoding = response.encoding or "utf-8"
                html = bytes(body).decode(response.encoding, errors="replace")
                soup = BeautifulSoup(html, "lxml")
                title = soup.title.get_text(" ", strip=True) if soup.title else ""
                for node in soup.select("script, style, nav, footer, header, aside, form, noscript"):
                    node.decompose()
                root = soup.find("main") or soup.find("article") or soup.body or soup

                markdown_blocks = []
                for node in root.find_all(
                    ["h1", "h2", "h3", "h4", "h5", "h6", "p", "li", "pre", "blockquote"]
                ):
                    if node.name in {"p", "li"} and node.find_parent(["li", "pre", "blockquote"]):
                        continue
                    text = node.get_text(" ", strip=True)
                    if not text:
                        continue
                    if node.name.startswith("h"):
                        text = f"{'#' * int(node.name[1:])} {text}"
                    elif node.name == "li":
                        text = f"- {text}"
                    elif node.name == "blockquote":
                        text = f"> {text}"
                    elif node.name == "pre":
                        text = f"```\n{text}\n```"
                    markdown_blocks.append(text)
                if not markdown_blocks:
                    markdown_blocks = [root.get_text("\n", strip=True)]
                markdown = "\n\n".join(markdown_blocks).strip()
                if not markdown:
                    raise ValueError("No readable page content found")

                terms = [
                    value.strip().lower()
                    for value in search_queries
                    if value and value.strip()
                ]
                scored = [
                    (sum(text.lower().count(term) for term in terms), index, text)
                    for index, text in enumerate(markdown_blocks)
                ]
                relevant = sorted(scored, key=lambda entry: (-entry[0], entry[1]))
                excerpts = [entry[2][:1200] for entry in relevant[:4] if entry[0] > 0]
                if not excerpts:
                    excerpts = [text[:1200] for text in markdown_blocks[:4]]
                return {
                    "url": original_url,
                    "title": title,
                    "excerpts": excerpts,
                    "full_content": markdown,
                }
            raise ValueError("Too many redirects")
        except _UnsafePublicURL as exc:
            return {
                "url": original_url,
                "error": str(exc),
                "excerpts": [],
                "_fallback_allowed": False,
            }
        except Exception as exc:
            return {
                "url": original_url,
                "error": str(exc),
                "excerpts": [],
                "_fallback_allowed": True,
            }
        finally:
            if response is not None:
                response.close()

    @mcp.tool()
    def web_fetch(
        urls: list[str],
        search_queries: list[str] | None = None,
        full_content: bool = False,
        max_chars_total: int = 25000,
    ) -> dict:
        """Read public web pages and return useful excerpts.

        Use this tool to read pages found through search or supplied by the
        user. Set ``full_content`` to true when you need the complete readable
        page text. The character limit is shared across all excerpts and full
        page text, in the order of the supplied URLs. If text is shortened,
        the response's ``truncated`` field is true.

        Args:
            urls: One to 20 public web page addresses to read. Results follow
                the order of the supplied addresses.
            search_queries: Optional phrases to help focus the excerpts on
                relevant information.
            full_content: Set to true to include the readable page text along
                with the excerpts.
            max_chars_total: Maximum combined number of characters in all
                excerpts and full page text. Excess text is shortened
                (default: 25000).

        Each result includes the page address and excerpts, with the title and
        full text when available. If a page cannot be read, its result includes
        an ``error`` message.
        """
        if not urls:
            raise ValueError("urls must contain at least one URL")
        if len(urls) > 20:
            raise ValueError("urls must contain at most 20 URLs")
        if max_chars_total < 1:
            raise ValueError("max_chars_total must be at least 1")
        queries = search_queries or []
        requested_urls = list(dict.fromkeys(urls))[:20]
        with ThreadPoolExecutor(max_workers=min(8, len(requested_urls))) as pool:
            pages = list(pool.map(
                lambda page_url: _fetch_page(page_url, queries),
                requested_urls,
            ))

        fallback_indices = [
            index for index, page in enumerate(pages)
            if page.get("_fallback_allowed")
        ]
        if fallback_indices:
            fallback_urls = [pages[index]["url"] for index in fallback_indices]
            fallback_pages = call_parallel_fetch(
                fallback_urls,
                search_queries=queries,
                full_content=full_content,
                timeout=TIMEOUT,
            )

            def url_identity(value: str) -> tuple:
                try:
                    parsed = urlsplit(value)
                    return (
                        parsed.scheme.lower(),
                        (parsed.hostname or "").rstrip(".").lower(),
                        parsed.port,
                        parsed.path.rstrip("/") or "/",
                        parsed.query,
                    )
                except ValueError:
                    return (value.rstrip("/"),)

            fallback_by_url = {
                url_identity(page["url"]): page
                for page in fallback_pages
                if page.get("url")
            }
            for offset, index in enumerate(fallback_indices):
                local_page = pages[index]
                fallback_page = fallback_by_url.get(url_identity(local_page["url"]))
                if fallback_page is None and len(fallback_pages) == len(fallback_indices):
                    fallback_page = fallback_pages[offset]
                if not fallback_page or fallback_page.get("error"):
                    continue
                if not fallback_page.get("excerpts") and not fallback_page.get("full_content"):
                    continue

                pages[index] = {
                    "url": local_page["url"],
                    "title": fallback_page.get("title", ""),
                    "excerpts": fallback_page.get("excerpts", []),
                }
                if full_content and fallback_page.get("full_content"):
                    pages[index]["full_content"] = fallback_page["full_content"]

        output_pages = []
        for page in pages:
            page_result = {
                "url": page["url"],
                "excerpts": page.get("excerpts", []),
            }
            if page.get("title"):
                page_result["title"] = page["title"]
            if full_content and page.get("full_content"):
                page_result["full_content"] = page["full_content"]
            if page.get("error"):
                page_result["error"] = page["error"]
            output_pages.append(page_result)

        remaining_chars = max_chars_total
        truncated = False

        def limit_content(text: str) -> str:
            nonlocal remaining_chars, truncated
            if len(text) > remaining_chars:
                clipped = text[:remaining_chars]
                remaining_chars = 0
                truncated = True
                return clipped
            remaining_chars -= len(text)
            return text

        for page in output_pages:
            page["excerpts"] = [
                clipped
                for excerpt in page.get("excerpts", [])
                if (clipped := limit_content(excerpt))
            ]
            full_text = page.get("full_content")
            if full_text:
                clipped = limit_content(full_text)
                if clipped:
                    page["full_content"] = clipped
                else:
                    page.pop("full_content", None)

        return {"results": output_pages, "truncated": truncated}

    if __name__ == "__main__":
        mcp.run(transport="stdio")
