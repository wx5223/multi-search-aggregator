"""web_fetch 网页抓取引擎 + HTML 解析"""
import re, requests as _requests
from ..models import SearchResult
from ..config import TIMEOUT

# Session for connection reuse
_http_session = None


def _get_session():
    global _http_session
    if _http_session is None:
        _http_session = _requests.Session()
        _http_session.headers.update({
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36"
            ),
            "Accept": "text/html,application/xhtml+xml",
            "Accept-Encoding": "gzip, deflate",
        })
    return _http_session


def call_web_fetch(url: str, timeout: int = TIMEOUT) -> str:
    """HTTP GET 获取页面 HTML，过滤反爬/验证页面"""
    resp = _get_session().get(url, timeout=timeout)
    resp.raise_for_status()
    if any(
        kw in resp.text[:2000].lower()
        for kw in ['antispider', 'verify you', 'captcha', 'rate limit']
    ):
        raise RuntimeError("Search page returned an anti-bot or rate-limit page")
    return resp.text


def parse_html_links(html: str, source: str, weight: int) -> list[SearchResult]:
    """从搜索引擎 HTML 中提取结果（按引擎区分解析策略）"""
    results = []
    html_clean = re.sub(
        r"<script[^>]*>.*?</script>", "", html, flags=re.DOTALL
    )
    html_clean = re.sub(
        r"<style[^>]*>.*?</style>", "", html_clean, flags=re.DOTALL
    )

    # 按引擎使用不同的 CSS 选择器提取结构化结果
    parsed = _parse_search_html(html_clean, source)
    if parsed:
        for title, url, snippet in parsed:
            results.append(
                SearchResult(
                    title=title[:200],
                    url=url,
                    summary=snippet[:500] if snippet else "",
                    source=source,
                    engine_weight=weight,
                    snippet_len=len(snippet) if snippet else 0,
                )
            )
        return results

    # fallback: 正则提取所有 <a> 链接（含 skip_domains 过滤）
    skip_domains_fallback = [
        'bing.com', 'google.com', 'yahoo.com', 'duckduckgo.com',
        'startpage.com', 'qwant.com', 'brave.com', 'sogou.com',
        'so.com', 'baidu.com',
    ]
    for m in re.finditer(
        r'<a[^>]+href="(https?://[^"]+)"[^>]*>(.*?)</a>',
        html_clean,
        re.DOTALL,
    ):
        url = m.group(1).strip()
        title = re.sub(r"<[^>]+>", "", m.group(2)).strip()
        if not title or len(title) <= 5 or len(title) >= 200:
            continue
        if any(d in url.lower() for d in skip_domains_fallback):
            continue
        results.append(
            SearchResult(
                title=title,
                url=url,
                source=source,
                engine_weight=weight,
                snippet_len=len(title),
            )
        )
    return results


def _parse_search_html(html: str, source: str) -> list[tuple]:
    """按搜索引擎区分的结构化 HTML 解析，返回 [(title, url, snippet)]"""
    results = []

    # 百度：结果在 <h3 class="c-title"> 或 <h3 class="t"> 里
    if source == "百度":
        for m in re.finditer(
            r'<h3[^>]*class="[^"]*c-title[^"]*"[^>]*>.*?<a[^>]+href="([^"]+)"[^>]*>(.*?)</a>',
            html,
            re.DOTALL,
        ):
            url, title_raw = m.group(1), m.group(2)
            title = re.sub(r'<[^>]+>', '', title_raw).strip()
            snippet = ""
            after = html[m.end():m.end() + 2000]
            sm = re.search(
                r'<span[^>]*class="[^"]*content-right[^"]*"[^>]*>(.*?)</span>',
                after,
                re.DOTALL,
            )
            if not sm:
                sm = re.search(
                    r'class="c-abstract[^"]*"[^>]*>(.*?)</(?:span|div)>',
                    after,
                    re.DOTALL,
                )
            if sm:
                snippet = re.sub(r'<[^>]+>', '', sm.group(1)).strip()
            if title and url:
                results.append((title, url, snippet))

    # Bing：结果在 <li class="b_algo">
    elif source in ("Bing国内", "Bing国际"):
        for m in re.finditer(
            r'<li[^>]*class="b_algo"[^>]*>(.*?)</li>', html, re.DOTALL
        ):
            block = m.group(1)
            tm = re.search(
                r'<a[^>]+href="([^"]+)"[^>]*><h2[^>]*>(.*?)</h2>',
                block,
                re.DOTALL,
            )
            if not tm:
                tm = re.search(
                    r'<h2[^>]*><a[^>]+href="([^"]+)"[^>]*>(.*?)</a></h2>',
                    block,
                    re.DOTALL,
                )
            if tm:
                url, title_raw = tm.group(1), tm.group(2)
                title = re.sub(r'<[^>]+>', '', title_raw).strip()
                snippet = ""
                sm = re.search(r'<p[^>]*>(.*?)</p>', block, re.DOTALL)
                if sm:
                    snippet = re.sub(r'<[^>]+>', '', sm.group(1)).strip()
                results.append((title, url, snippet))

    # 搜狗 — 直接提取 h3>a 模式
    elif source == "搜狗Web":
        for m in re.finditer(
            r'<h3[^>]*>\s*<a[^>]+href="([^"]+)"[^>]*>(.*?)</a>\s*</h3>',
            html,
            re.DOTALL,
        ):
            url, title_raw = m.group(1), m.group(2)
            title = re.sub(r'<[^>]+>', '', title_raw).strip()
            snippet = ""
            after = html[m.end():m.end() + 3000]
            sm = re.search(
                r'<(?:div|p)[^>]*class="[^"]*(?:text-layout|str-text|str_time|content)[^"]*"[^>]*>(.*?)</(?:div|p)>',
                after,
                re.DOTALL,
            )
            if not sm:
                sm = re.search(r'<p[^>]*>(.*?)</p>', after, re.DOTALL)
            if sm:
                snippet = re.sub(r'<[^>]+>', '', sm.group(1)).strip()
            if title and url:
                results.append((title, url, snippet))

    # 微信搜一搜
    elif source == "微信搜一搜":
        for m in re.finditer(
            r'<h3[^>]*>\s*<a[^>]+href="([^"]+)"[^>]*>(.*?)</a>\s*</h3>',
            html,
            re.DOTALL,
        ):
            url, title_raw = m.group(1), m.group(2)
            title = re.sub(r'<[^>]+>', '', title_raw).strip()
            if url.startswith('/'):
                url = 'https://wx.sogou.com' + url
            snippet = ""
            after = html[m.end():m.end() + 2000]
            sm = re.search(r'<p[^>]*>(.*?)</p>', after, re.DOTALL)
            if sm:
                snippet = re.sub(r'<[^>]+>', '', sm.group(1)).strip()
                if len(snippet) < 15:
                    snippet = ""
            if title and url:
                results.append((title, url, snippet))

    # Google / Google HK
    elif source in ("Google_WF", "Google_HK"):
        g_blocks = re.split(r'<div[^>]*class="g"[^>]*>', html)
        for block in g_blocks[1:]:
            tm = re.search(r'<h3[^>]*>(.*?)</h3>', block, re.DOTALL)
            if not tm:
                continue
            title = re.sub(r'<[^>]+>', '', tm.group(1)).strip()
            am = re.search(
                r'<a[^>]+href="(/url\?q=([^&"]+)|([^"]+))"', block
            )
            url = ""
            if am:
                url = am.group(2) or am.group(3) or ""
            snippet = ""
            sm = re.search(
                r'<div[^>]*class="[^"]*VwiC3b[^"]*"[^>]*>(.*?)</div>',
                block,
                re.DOTALL,
            )
            if not sm:
                sm = re.search(
                    r'<span[^>]*class="[^"]*st[^"]*"[^>]*>(.*?)</span>',
                    block,
                    re.DOTALL,
                )
            if sm:
                snippet = re.sub(r'<[^>]+>', '', sm.group(1)).strip()
            if title and url and 'google.com' not in url:
                results.append((title, url, snippet))

    # DuckDuckGo HTML
    elif source == "DDG_WF":
        for m in re.finditer(
            r'<div[^>]*class="result__body"[^>]*>(.*?)</div>\s*</div>',
            html,
            re.DOTALL,
        ):
            block = m.group(1)
            tm = re.search(
                r'<a[^>]+class="result__a"[^>]+href="([^"]+)"[^>]*>(.*?)</a>',
                block,
                re.DOTALL,
            )
            if tm:
                url = tm.group(1)
                title = re.sub(r'<[^>]+>', '', tm.group(2)).strip()
                snippet = ""
                sm = re.search(
                    r'<a[^>]*class="result__snippet"[^>]*>(.*?)</a>',
                    block,
                    re.DOTALL,
                )
                if not sm:
                    sm = re.search(
                        r'<td[^>]*class="result__snippet"[^>]*>(.*?)</td>',
                        block,
                        re.DOTALL,
                    )
                if sm:
                    snippet = re.sub(r'<[^>]+>', '', sm.group(1)).strip()
                results.append((title, url, snippet))

    # Yahoo
    elif source == "Yahoo_WF":
        y_blocks = re.split(r'<li[^>]*class="[^"]*layout[^"]*"[^>]*>', html)
        if len(y_blocks) < 2:
            y_blocks = re.split(
                r'<div[^>]*class="(?:algo-sr|Sr\b)[^"]*"[^>]*>', html
            )
        for block in y_blocks[1:]:
            tm = re.search(
                r'<h3[^>]*>\s*<a[^>]+href="([^"]+)"[^>]*>(.*?)</a>',
                block,
                re.DOTALL,
            )
            if not tm:
                tm = re.search(
                    r'<a[^>]+href="([^"]+)"[^>]*title="([^"]+)"',
                    block,
                )
            if tm:
                url, title_raw = tm.group(1), tm.group(2)
                title = re.sub(r'<[^>]+>', '', title_raw).strip()
                title = re.sub(r'^.{3,30}?https?://', '', title).strip()
                title = re.sub(r'^.{3,30}?›', '', title).strip()
                snippet = ""
                sm = re.search(r'<p[^>]*>(.*?)</p>', block, re.DOTALL)
                if not sm:
                    sm = re.search(
                        r'<span[^>]*class="[^"]*fc-falcon[^"]*"[^>]*>(.*?)</span>',
                        block,
                        re.DOTALL,
                    )
                if sm:
                    snippet = re.sub(r'<[^>]+>', '', sm.group(1)).strip()
                if title and url:
                    results.append((title, url, snippet))

        # Yahoo alt pattern
        for m in re.finditer(
            r'<a[^>]+href="(https?://[^"]+)"[^>]*>.*?<h3[^>]*>.*?<span[^>]*>(.*?)</span>.*?</h3>',
            html,
            re.DOTALL,
        ):
            url, title_raw = m.group(1), m.group(2)
            title = re.sub(r'<[^>]+>', '', title_raw).strip()
            if title and url:
                results.append((title, url, ""))

    # Brave Search
    elif source == "Brave_WF":
        for m in re.finditer(
            r'<div[^>]*class="snippet[^"]*"[^>]*>(.*?)</div>',
            html,
            re.DOTALL,
        ):
            block = m.group(1)
            tm = re.search(
                r'<a[^>]+href="(https?://[^"]+)"[^>]*>(.*?)</a>',
                block,
                re.DOTALL,
            )
            if tm:
                url, title_raw = tm.group(1), tm.group(2)
                title = re.sub(r'<[^>]+>', '', title_raw).strip()
                snippet = ""
                sm = re.search(
                    r'<p[^>]*class="snippet-description[^"]*"[^>]*>(.*?)</p>',
                    block,
                    re.DOTALL,
                )
                if not sm:
                    sm = re.search(
                        r'<div[^>]*class="snippet-description[^"]*"[^>]*>(.*?)</div>',
                        block,
                        re.DOTALL,
                    )
                if sm:
                    snippet = re.sub(r'<[^>]+>', '', sm.group(1)).strip()
                if title and url:
                    results.append((title, url, snippet))
        if not results:
            for m in re.finditer(
                r'<a[^>]+href="(https?://[^"]+)"[^>]*class="result-header[^"]*"[^>]*>(.*?)</a>',
                html,
                re.DOTALL,
            ):
                url, title_raw = m.group(1), m.group(2)
                title = re.sub(r'<[^>]+>', '', title_raw).strip()
                if title and url:
                    results.append((title, url, ""))

    # Qwant
    elif source == "Qwant":
        for m in re.finditer(
            r'<article[^>]*>(.*?)</article>', html, re.DOTALL
        ):
            block = m.group(1)
            tm = re.search(
                r'<a[^>]+href="(https?://[^"]+)"[^>]*>(.*?)</a>',
                block,
                re.DOTALL,
            )
            if tm:
                url, title_raw = tm.group(1), tm.group(2)
                title = re.sub(r'<[^>]+>', '', title_raw).strip()
                snippet = ""
                sm = re.search(r'<p[^>]*>(.*?)</p>', block, re.DOTALL)
                if sm:
                    snippet = re.sub(r'<[^>]+>', '', sm.group(1)).strip()
                if title and url:
                    results.append((title, url, snippet))

    # Startpage — 新React结构
    elif source == "Startpage":
        seen_sp = set()
        for m in re.finditer(
            r'<a[^>]+href="(https?://[^"]*)"[^>]*target="_blank"[^>]*rel="noopener[^"]*"[^>]*>(.+?)</a>',
            html,
            re.DOTALL,
        ):
            url = m.group(1)
            if 'startpage.com' in url.lower() or url in seen_sp:
                continue
            seen_sp.add(url)
            inner = m.group(2)
            title = re.sub(r'<[^>]+>', '', inner).strip()
            if (
                not title
                or len(title) < 10
                or title.startswith('.')
                or title.startswith('http')
            ):
                continue
            snippet = ""
            after = html[m.end():m.end() + 3000]
            for tag in ['span', 'p', 'div']:
                sm = re.search(
                    f'<{tag}[^>]*>(.*?)</{tag}>', after, re.DOTALL
                )
                if sm:
                    snippet = re.sub(r'<[^>]+>', '', sm.group(1)).strip()
                    if len(snippet) > 30:
                        break
                    snippet = ""
            if title and url:
                results.append((title, url, snippet))

    # 360搜索
    elif source == "360搜索":
        for m in re.finditer(
            r'<a[^>]+href="(https?://[^"]*so\.com/link[^"]*)"[^>]*>(.+?)</a>',
            html,
            re.DOTALL,
        ):
            url = m.group(1)
            title_raw = m.group(2)
            title = re.sub(r'<[^>]+>', '', title_raw).strip()
            if not title or len(title) < 5:
                continue
            snippet = ""
            after = html[m.end():m.end() + 3000]
            for tag in ['p', 'div', 'span']:
                sm = re.search(
                    f'<{tag}[^>]*>(.*?)</{tag}>', after, re.DOTALL
                )
                if sm:
                    snippet = re.sub(r'<[^>]+>', '', sm.group(1)).strip()
                    if len(snippet) > 20:
                        break
                    snippet = ""
            if title and url:
                results.append((title, url, snippet))

    # 通用 fallback
    if not results:
        h_blocks = list(
            re.finditer(
                r'<(?:h[23])[^>]*>\s*(?:<a[^>]+href="([^"]+)"[^>]*>)?([^<]*(?:<[^>]+>[^<]*)*?)(?:</a>)?\s*</(?:h[23])>',
                html,
                re.DOTALL,
            )
        )
        for m in h_blocks:
            url = m.group(1) or ""
            title = re.sub(r'<[^>]+>', '', m.group(2)).strip()
            if not title or len(title) < 8 or len(title) > 200 or not url:
                continue
            snippet = ""
            after_text = html[m.end():m.end() + 1500]
            sm = re.search(
                r'<(?:p|span|div)[^>]*class="[^"]*(?:snippet|abstract|desc|summary|content)[^"]*"[^>]*>(.*?)</(?:p|span|div)>',
                after_text,
                re.DOTALL,
            )
            if not sm:
                sm = re.search(r'<p[^>]*>(.*?)</p>', after_text, re.DOTALL)
            if sm:
                snippet = re.sub(r'<[^>]+>', '', sm.group(1)).strip()
                if len(snippet) < 15:
                    snippet = ""
            results.append((title, url, snippet))

    # 过滤导航/广告链接
    filtered = []
    skip_domains = [
        'bing.com', 'google.com', 'yahoo.com', 'duckduckgo.com',
        'startpage.com', 'qwant.com', 'brave.com', 'sogou.com',
        'so.com',
    ]
    for title, url, snippet in results:
        is_so_jump = 'so.com/link?' in url.lower()
        if is_so_jump:
            filtered.append((title, url, snippet))
            continue
        is_bing_jump = 'bing.com/ck/' in url.lower()
        if is_bing_jump:
            filtered.append((title, url, snippet))
            continue
        if any(d in url.lower() for d in skip_domains) and len(results) > 3:
            continue
        filtered.append((title, url, snippet))

    return filtered
