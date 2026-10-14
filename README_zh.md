<div align="center">

# 🔍 Multi-Search Aggregator

**并行调用 35+ 个搜索引擎——一次查询，汇聚全网结果。**

[![English](https://img.shields.io/badge/English-DBEDFA)](./README.md)
[![简体中文](https://img.shields.io/badge/简体中文-DFE0E5)](./README_zh.md)

[![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Engines](https://img.shields.io/badge/Engines-33%2B-orange.svg)]()

</div>

---

<details open>
<summary><b>📕 目录</b></summary>

- [💡 这是什么？](#-这是什么)
- [✨ 核心特性](#-核心特性)
- [📡 支持的搜索引擎](#-支持的搜索引擎)
- [🚀 快速开始](#-快速开始)
- [⚙️ 配置说明](#-配置说明)
- [🌐 Web 界面与 API](#-web-界面与-api)
- [🧩 扩展引擎](#-扩展引擎)
- [📁 项目结构](#-项目结构)
- [🤝 参与贡献](#-参与贡献)
- [📄 许可证](#-许可证)

</details>

---

## 💡 这是什么？

一个**并行搜索聚合器**，能同时向 35+ 个搜索引擎发送查询请求，去重结果，按相关性排序，并返回最佳匹配——专为 AI 代理和科研工作流而设计。

相比只调用一个搜索引擎然后听天由命，本工具通过智能评分整合多方来源的结果：

- **限额优先**——默认单次尝试一个限额渠道；命中即返回，未命中则并发回退
- **智能排序**——关键词相关性 + 引擎权威性 + 时效性 + 语义向量相似度
- **实时进度**——SSE 流式推送，每个引擎完成时实时展示
- **可插拔引擎**——新增搜索后端无需改动核心代码

## ✨ 核心特性

- ⚡ **两种调用模式**——限额优先模式减少付费请求；全并发模式同时调用所有已配置引擎
- 🧠 **智能排序**——多信号评分：关键词匹配 + 引擎权重 + 时效性 + 向量相似度
- 🔄 **自动去重**——URL 标准化，跨引擎去除重复结果
- 📡 **SSE 流式推送**——浏览器内实时进度，每完成一个引擎即报告
- 🖥️ **Web 界面**——Google 风格搜索页面，带引擎筛选侧边栏
- 🚀 **REST API**——简单 JSON 端点，方便程序接入
- 🔌 **33 个以上引擎**——从 Google、arXiv 到 Hacker News、知乎
- ⚙️ **动态配置**——无需重启即可启用/禁用引擎、调整权重
- 🛡️ **优雅降级**——需要密钥的引擎未配置时自动跳过；Tavily 免 Key 版和 Parallel Search 可直接使用。

## 📡 支持的搜索引擎

| 类别 | 引擎 |
|----------|---------|
| **通用搜索** | Google、Bing（国内 + 国际版）、360 搜索、搜狗、Startpage、Brave、Qwant |
| **学术搜索** | arXiv、OpenAlex、OpenReview、DBLP、AMiner（论文 + 专利） |
| **开发者** | Stack Overflow、npm、crates.io、MDN |
| **社交** | Reddit、Hacker News、知乎、小红书 |
| **AI 与聚合搜索** | 智谱 AI（Pro/搜狗/夸克）、Z.AI、阿里百炼、Tavily（免 Key/API Key）、Exa、Firecrawl、Brave Search API、百度千帆 AI 搜索、豆包搜索、Parallel Search |
| **中文搜索** | 微信搜一搜、知乎、百度、微信读书 |
| **浏览器** | 通过 OpenCLI 浏览器自动化访问任意网站 |
| **自定义** | 通过 MCP、技能脚本或 web_fetch 添加自己的引擎 |

## 🚀 快速开始

### 1. 安装

```bash
git clone https://github.com/yourname/multi-search-aggregator.git
cd multi-search-aggregator
pip install -r requirements.txt
```

### 2. 配置 API 密钥

```bash
cp .env.example .env
# 编辑 .env —— 为你想要使用的引擎添加密钥：
# ZHIPU_API_KEY=your_key_here
# ZAI_API_KEY=your_key_here
# BAILIAN_API_KEY=your_key_here
# TAVILY_API_KEY=your_key_here  # Tavily 带 Key 渠道（免 Key 渠道仍独立可用）
# EXA_API_KEY=your_key_here
# FIRECRAWL_API_KEY=your_key_here
# BRAVE_SEARCH_API_KEY=your_key_here
# BAIDU_QIANFAN_API_KEY=your_key_here
# DOUBAO_SEARCH_API_KEY=your_key_here
# （未提供密钥 = 跳过该引擎，不会报错）
```

Tavily 提供独立的免 Key（`tavily`）和带 Key（`tavily_key`）渠道。Exa、Firecrawl、Brave Search API、百度千帆 AI 搜索和豆包搜索配置密钥后启用。这些渠道均纳入“限额优先”模式：每次只调用一个已配置的限额渠道，有结果即返回。百度每日免费额度的具体数量以千帆控制台为准；豆包搜索每月免费 500 次，Global 与 Custom 共用，并于每月 1 日重置。

### 3. 运行

```bash
# CLI 搜索
python run_search.py "RISC-V vector extension"
python run_search.py "LDPC decoder" --engines zhipu_pro,arxiv --top 10 --json
python run_search.py "RISC-V" --mode parallel  # 切换到全并发模式

# Web 服务器（http://localhost:8200）
python server.py
```

打开 `http://localhost:8200` → 像 Google 一样搜索，结果来自 35+ 个引擎。

默认“限额优先”模式每次只尝试一个已配置的限额渠道；有结果就结束，否则将该渠道标记为暂不可用 5 分钟，并发调用其他渠道。也可通过界面、API 的 `mode=parallel` 或 CLI 的 `--mode parallel` 切换为全并发。

## ⚙️ 配置说明

```yaml
# config.yaml

# 服务器
server:
  host: "0.0.0.0"
  port: 8200

# 搜索默认值
search:
  default_top_k: 50
  max_top_k: 200
  default_timeout: 35

# 引擎权重（值越高越权威）
weights:
  Google: 10
  Z.AI: 9
  ZhipuPro: 9
  Stack Overflow: 8
  arXiv: 8

# 禁用特定引擎
engine_overrides:
  some_engine_id:
    enabled: false
```

## 🌐 Web 界面与 API

### 搜索

```bash
# GET 请求
curl "http://localhost:8200/api/search?q=RISC-V&top_k=50"

# POST 请求（更多选项）
curl -X POST http://localhost:8200/api/search \
  -H "Content-Type: application/json" \
  -d '{"query": "transformer attention", "top_k": 20, "engines": ["zhipu_pro", "arxiv"]}'

# 响应格式：
# {
#   "results": [
#     {"title": "...", "url": "...", "summary": "...", "source": "arXiv", "score": 0.95},
#     ...
#   ],
#   "meta": {"engines_used": 15, "total_results": 234, "elapsed_ms": 3200}
# }
```

### SSE 流式推送（实时进度）

```javascript
const es = new EventSource('/api/search/stream?q=RISC-V');
es.addEventListener('engine_done', e => {
    console.log(`✅ ${JSON.parse(e.data).engine}: ${JSON.parse(e.data).results} 条结果`);
});
es.addEventListener('complete', e => {
    const data = JSON.parse(e.data);
    console.log(`完成：共 ${data.total_results} 条结果，耗时 ${data.elapsed_ms} ms`);
});
```

### 配置与引擎管理

```bash
# 列出引擎及其状态
curl http://localhost:8200/api/engines

# 开关引擎
curl -X POST http://localhost:8200/api/engines/toggle \
  -d '{"engine_id": "google", "enabled": false}'

# 获取/更新配置
curl http://localhost:8200/api/config
curl -X PUT http://localhost:8200/api/config -d '{"timeout": 20}'
```

## 🧩 扩展引擎

添加新引擎非常简单：

1. 创建 `search_agg/engines/my_engine.py`
2. 实现 `call_my_engine(query: str) -> list[dict]`
3. 在 `search_agg/engines/__init__.py` 中注册

```python
# search_agg/engines/my_engine.py
def call_my_engine(query: str) -> list[dict]:
    """必须返回包含 title、url、summary 的字典列表"""
    import requests
    resp = requests.get(f"https://api.example.com/search?q={query}")
    return resp.json().get("results", [])
```

```python
# 在 search_agg/engines/__init__.py 中，添加到 ENGINES 列表：
{
    "id": "my_engine",
    "name": "My Engine",
    "type": "web_fetch",
    "url_tpl": "https://api.example.com/search?q={q}",
    "weight": 7,
}
```

## 📁 项目结构

```
multi-search-aggregator/
├── server.py                    # FastAPI Web 服务器
├── run_search.py                # CLI 入口
├── config.yaml                  # 配置文件
│
├── search_agg/
│   ├── __init__.py              # 公开 API：search()、aggregate()
│   ├── config.py                # 配置加载 + 环境变量
│   ├── models.py                # SearchResult 数据模型
│   ├── runner.py                # 并行引擎调度器
│   ├── ranker.py                # 去重 + 评分 + 向量排序
│   ├── utils.py                 # URL 清理、进程管理
│   └── engines/
│       ├── __init__.py          # 引擎注册表（31 个引擎）
│       ├── zhipu.py             # 智谱 AI（Pro/搜狗/夸克）
│       ├── zai.py               # Z.AI REST API
│       ├── bailian.py           # 阿里百炼 MCP
│       ├── opencli.py           # 浏览器自动化引擎
│       ├── web_fetch.py         # HTTP 抓取 + HTML 解析
│       ├── mcp_stdio.py         # MCP stdio 协议
│       └── skill.py             # 外部脚本引擎
│
├── static/                      # Web 界面
│   ├── index.html               # 搜索页面（SSE 实时进度）
│   ├── config.html              # 引擎配置面板
│   └── style.css
│
├── requirements.txt
├── .env.example
├── .gitignore
├── LICENSE
└── README.md
```

## 🤝 参与贡献

欢迎提交新引擎、Bug 修复和改进！

1. Fork 本仓库
2. 创建功能分支
3. 添加你的引擎或修复
4. 提交 Pull Request

## 📄 许可证

[MIT 许可证](LICENSE) —— 随意使用。
