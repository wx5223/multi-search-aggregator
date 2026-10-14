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
    from search_agg.config import TIMEOUT

    mcp = FastMCP("multi-search-aggregator")

    @mcp.tool()
    def web_search(
        objective: str,
        search_queries: list[str],
    ) -> dict:
        """Search the web and return up to 20 ranked results.

        Args:
            objective: Non-empty description of the information to find. It is
                included in the single query sent to the aggregator.
            search_queries: One or more non-empty keyword queries. They are
                joined with OR and sent with the objective in one aggregator
                request. This keeps one tool call from multiplying provider
                calls.

        Returns results with title, URL, excerpts, source, and publish date
        when available. ``total_results`` is the raw count reported by the
        aggregator before its result limit and deduplication.
        """
        if not objective.strip():
            raise ValueError("objective must not be empty")
        queries = [query.strip() for query in search_queries if query.strip()]
        if not queries:
            raise ValueError("search_queries must contain at least one query")
        query = f"{objective.strip()} ({' OR '.join(queries)})"

        # The aggregator prints progress for its CLI. Keep stdout clean because
        # it carries MCP's stdio JSON-RPC messages.
        with redirect_stdout(sys.stderr):
            response = aggregate_search(
                query=query,
                top_k=20,
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
            "objective": objective,
            "search_queries": queries,
            "results": results,
            "total_results": response.get("meta", {}).get("total_results", len(results)),
        }

    def _validate_public_url(url: str) -> str:
        parsed = urlsplit(url)
        if parsed.scheme.lower() not in {"http", "https"} or not parsed.hostname:
            raise ValueError("Only absolute HTTP or HTTPS URLs are supported")
        if parsed.username or parsed.password:
            raise ValueError("URLs containing credentials are not supported")

        host = parsed.hostname.rstrip(".").lower()
        if host == "localhost" or host.endswith((".localhost", ".local", ".internal")):
            raise ValueError("Private and local URLs are not supported")
        port = parsed.port or (443 if parsed.scheme.lower() == "https" else 80)
        try:
            addresses = {ipaddress.ip_address(host)}
        except ValueError:
            try:
                addresses = {
                    ipaddress.ip_address(info[4][0])
                    for info in socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
                }
            except (OSError, ValueError) as exc:
                raise ValueError("Could not resolve the URL host") from exc
        if not addresses or any(not address.is_global for address in addresses):
            raise ValueError("Private and local URLs are not supported")
        return url

    def _fetch_page(url: str, objective: str, search_queries: list[str]) -> dict:
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
                    for value in [objective, *search_queries]
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
        except Exception as exc:
            return {"url": original_url, "error": str(exc), "excerpts": []}
        finally:
            if response is not None:
                response.close()

    @mcp.tool()
    def web_fetch(
        urls: list[str],
        objective: str | None = None,
        search_queries: list[str] | None = None,
        full_content: bool = False,
    ) -> dict:
        """Fetch excerpts or full extracted text from public web pages.

        Args:
            urls: One to 20 absolute public HTTP or HTTPS URLs. Duplicate URLs
                are fetched once; results follow the input order.
            objective: Optional excerpt focus, at most 200 characters.
            search_queries: Optional phrases used with the objective to rank
                extracted text blocks for excerpts. Ranking uses
                case-insensitive substring matches; ties keep page order.
            full_content: When true, include the extracted page text in
                Markdown-like form in addition to excerpts.

        Only static HTML, XHTML, and plain-text responses up to 5 MiB per page
        are supported. Private/local destinations and redirects to them are
        rejected. Each page returns up to four excerpts of at most 1,200
        characters. A fetch failure is reported in that page's ``error`` field.
        """
        if not urls:
            raise ValueError("urls must contain at least one URL")
        if len(urls) > 20:
            raise ValueError("urls must contain at most 20 URLs")
        if objective is not None and len(objective) > 200:
            raise ValueError("objective must be at most 200 characters")
        queries = search_queries or []
        requested_urls = list(dict.fromkeys(urls))[:20]
        with ThreadPoolExecutor(max_workers=min(8, len(requested_urls))) as pool:
            pages = list(pool.map(
                lambda page_url: _fetch_page(page_url, objective or "", queries),
                requested_urls,
            ))

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

        return {"results": output_pages}

    if __name__ == "__main__":
        mcp.run(transport="stdio")
