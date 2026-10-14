"""引擎注册表 — 定义所有可用搜索引擎"""
from ..config import AMINER_KEY, ZHIHU_KEY, OPENCLI_PATH

# ============================================================
# 引擎注册表（完整的 35+ 引擎定义）
# ============================================================
ENGINES = [
    # ============================================================
    # 1. API/MCP 直连
    # ============================================================
    {
        "id": "serpbase_google",
        "name": "SerpBase Google",
        "type": "serpbase_api",
        "retry": True,
        "quota_limited": True,
        "required_env": "SERPBASE_API_KEY",
    },
    {
        "id": "zhipu_pro",
        "name": "智谱Pro",
        "type": "zhipu_api",
        "engine": "search_pro",
        "retry": True,
        "quota_limited": True,
        "required_env": "ZHIPU_API_KEY",
        "quota_group": "zhipu",
    },
    {
        "id": "zhipu_sogou",
        "name": "智谱Sogou",
        "type": "zhipu_api",
        "engine": "search_pro_sogou",
        "retry": True,
        "quota_limited": True,
        "required_env": "ZHIPU_API_KEY",
        "quota_group": "zhipu",
    },
    {
        "id": "zhipu_quark",
        "name": "智谱Quark",
        "type": "zhipu_api",
        "engine": "search_pro_quark",
        "retry": True,
        "quota_limited": True,
        "required_env": "ZHIPU_API_KEY",
        "quota_group": "zhipu",
    },
    {
        "id": "zai", "name": "Z.AI", "type": "zai_api", "retry": True,
        "quota_limited": True, "required_env": "ZAI_API_KEY",
    },
    {
        "id": "bailian", "name": "百炼", "type": "bailian_mcp", "retry": True,
        "quota_limited": True, "required_env": "BAILIAN_API_KEY",
    },
    {
        "id": "tavily", "name": "Tavily（免Key）", "type": "tavily_api",
        "retry": True, "quota_limited": True,
    },
    {
        "id": "tavily_key", "name": "Tavily（API Key）", "type": "tavily_key_api",
        "retry": True, "quota_limited": True, "required_env": "TAVILY_API_KEY",
    },
    {
        "id": "exa", "name": "Exa", "type": "exa_api", "retry": True,
        "quota_limited": True, "required_env": "EXA_API_KEY",
    },
    {
        "id": "firecrawl", "name": "Firecrawl", "type": "firecrawl_api", "retry": True,
        "quota_limited": True, "required_env": "FIRECRAWL_API_KEY",
    },
    {
        "id": "brave_search", "name": "Brave Search API", "type": "brave_api", "retry": True,
        "quota_limited": True, "required_env": "BRAVE_SEARCH_API_KEY",
    },
    {
        "id": "baidu_qianfan_search", "name": "百度千帆 AI 搜索", "type": "baidu_qianfan_api",
        "retry": True, "quota_limited": True, "required_env": "BAIDU_QIANFAN_API_KEY",
    },
    {
        "id": "doubao_search", "name": "豆包搜索（Custom）", "type": "doubao_search_api",
        "retry": True, "quota_limited": True, "required_env": "DOUBAO_SEARCH_API_KEY",
    },
    {"id": "parallel_search", "name": "Parallel Search", "type": "parallel_mcp", "retry": True, "quota_limited": True},

    # ============================================================
    # 2. opencli（12 轻量 API + 3 重型）
    # ============================================================
    # --- 轻量 API 式（串行 <5s，全并发不冲突）---
    {"id": "oc_hackernews", "name": "Hacker News", "type": "opencli", "site": "hackernews"},
    {"id": "oc_so", "name": "Stack Overflow", "type": "opencli", "site": "stackoverflow"},
    {"id": "oc_wikipedia", "name": "Wikipedia", "type": "opencli", "site": "wikipedia"},
    {"id": "oc_arxiv", "name": "arXiv", "type": "opencli", "site": "arxiv"},
    {"id": "oc_openalex", "name": "OpenAlex", "type": "opencli", "site": "openalex"},
    {"id": "oc_openreview", "name": "OpenReview", "type": "opencli", "site": "openreview"},
    {"id": "oc_npm", "name": "npm", "type": "opencli", "site": "npm"},
    {"id": "oc_crates", "name": "crates.io", "type": "opencli", "site": "crates"},
    {"id": "oc_mdn", "name": "MDN", "type": "opencli", "site": "mdn"},
    # --- 重型学术/阅读（串行 5-7s 可用）---
    {"id": "oc_dblp", "name": "DBLP", "type": "opencli", "site": "dblp"},
    {"id": "oc_substack", "name": "Substack", "type": "opencli", "site": "substack"},
    {"id": "oc_weread", "name": "微信读书", "type": "opencli", "site": "weread"},
    # --- 重型页面渲染（需 Chrome，串行可用）---
    {
        "id": "oc_google",
        "name": "Google",
        "type": "opencli_heavy",
        "site": "google",
        "retry": True,
    },
    {
        "id": "oc_reddit",
        "name": "Reddit",
        "type": "opencli_heavy",
        "site": "reddit",
        "retry": True,
    },
    {
        "id": "oc_xiaohongshu",
        "name": "小红书",
        "type": "opencli_heavy",
        "site": "xiaohongshu",
        "retry": True,
    },

    # ============================================================
    # 3. web_fetch（6个活跃）
    # ============================================================
    {
        "id": "wf_bing_cn",
        "name": "Bing国内",
        "type": "web_fetch",
        "retry": True,
        "url_tpl": "https://cn.bing.com/search?q={q}&ensearch=0&count=10",
    },
    {
        "id": "wf_bing_int",
        "name": "Bing国际",
        "type": "web_fetch",
        "retry": True,
        "url_tpl": "https://cn.bing.com/search?q={q}&ensearch=1&count=10",
    },
    {
        "id": "wf_360",
        "name": "360搜索",
        "type": "web_fetch",
        "retry": True,
        "url_tpl": "https://www.so.com/s?q={q}",
    },
    {
        "id": "wf_sogou",
        "name": "搜狗Web",
        "type": "web_fetch",
        "retry": True,
        "url_tpl": "https://www.sogou.com/web?query={q}&num=10",
    },
    {
        "id": "wf_startpage",
        "name": "Startpage",
        "type": "web_fetch",
        "retry": True,
        "url_tpl": "https://www.startpage.com/sp/search?query={q}",
    },
    {
        "id": "wf_brave",
        "name": "Brave_WF",
        "type": "web_fetch",
        "retry": True,
        "url_tpl": "https://search.brave.com/search?q={q}",
    },
    {
        "id": "wf_qwant",
        "name": "Qwant",
        "type": "web_fetch",
        "retry": True,
        "url_tpl": "https://www.qwant.com/?q={q}",
    },

    # ============================================================
    # 4. Skill 脚本
    # ============================================================
    {
        "id": "sk_aminer",
        "name": "AMiner论文",
        "type": "skill",
        "quota_limited": True,
        "required_env": "AMINER_API_KEY",
        "quota_group": "aminer",
        "cmd": (
            'python3 skills/aminer-academic-search/scripts/aminer_client.py '
            '--action raw --api paper_search_pro '
            '--params \'{"keyword":"{q}","size":10,"order":"n_citation"}\' '
            '--token $AMINER_API_KEY'
        ),
    },
    {
        "id": "sk_aminer_pat",
        "name": "AMiner专利",
        "type": "skill",
        "quota_limited": True,
        "required_env": "AMINER_API_KEY",
        "quota_group": "aminer",
        "cmd": (
            'python3 skills/aminer-academic-search/scripts/aminer_client.py '
            '--action raw --api patent_search '
            '--params \'{"query":"{q}","size":10}\' '
            '--token $AMINER_API_KEY'
        ),
    },
    {
        "id": "sk_zhihu",
        "name": "知乎Skill",
        "type": "skill",
        "cmd": (
            'python3 skills/zhihu-search/scripts/global-search.py '
            '\'{ "query": "{q}", "count": 10 }\''
        ),
    },

    # ============================================================
    # 5. MCP stdio 直连
    # ============================================================
    {
        "id": "mcp_bing",
        "name": "EnhancedBing",
        "type": "mcp_stdio",
        "command": "npx",
        "args": ["-y", "bing-cn-mcp-enhanced"],
        "tool": "bing_search",
        "tool_args": {"query": "{q}", "num_results": 10},
        "retry": True,
    },
]


def get_engine_by_id(engine_id: str) -> dict | None:
    """根据 engine id 或显示名称查找引擎定义"""
    for e in ENGINES:
        if e["id"] == engine_id or e["name"] == engine_id:
            return e
    return None


def get_engines_by_ids(ids: list[str]) -> list[dict]:
    """根据 engine id 或名称列表批量查找"""
    result = []
    for eid in ids:
        e = get_engine_by_id(eid)
        if e:
            result.append(e)
    return result


def get_enabled_engines(engine_filter: list[str] | None = None) -> list[dict]:
    """返回启用的引擎列表。可选 filter 接受 engine id 或名称。"""
    from ..config import is_engine_enabled
    if engine_filter:
        return [e for e in get_engines_by_ids(engine_filter) if is_engine_enabled(e["id"])]
    return [e for e in ENGINES if is_engine_enabled(e["id"])]
