<div align="center">

# 🔍 Multi-Search Aggregator

**聚合多个搜索渠道，为 Web、HTTP API 和 MCP 客户端提供搜索与网页抓取能力。**

[![English](https://img.shields.io/badge/English-DBEDFA)](./README.md)
[![简体中文](https://img.shields.io/badge/简体中文-DFE0E5)](./README_zh.md)

[![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

</div>

---

## 目录

- [项目简介](#项目简介)
- [主要功能](#主要功能)
- [搜索渠道](#搜索渠道)
- [快速开始](#快速开始)
- [搜索排序与调用模式](#搜索排序与调用模式)
- [Web 与 HTTP API](#web-与-http-api)
- [MCP 接口](#mcp-接口)
- [配置](#配置)
- [项目结构](#项目结构)

## 项目简介

Multi-Search Aggregator 将多个搜索渠道的结果统一到一个服务中，完成去重、相关性排序和结果整理。项目提供 Web 搜索页面、REST API、SSE 实时进度接口，以及基于 Streamable HTTP 的 MCP 服务。

## 主要功能

- 多渠道搜索，支持按渠道筛选、启用或禁用。
- 限额优先模式依次尝试限额渠道，有结果即停；都失败或无结果时再并发调用不限额渠道。
- 全并发模式同时调用已启用且已配置的渠道。
- 默认使用 jieba 中文分词和 BM25 排序，并过滤 `search_agg/stopwords.txt` 中的停用词；无需下载或加载本地 embedding 模型。
- 搜索结果会去重并交错展示；同一渠道内保留上游返回顺序。
- Web 页面及静态资源通过项目目录定位，首页位于 `/`，静态文件位于 `/static/`。
- MCP `web_fetch` 先尝试本地抓取；失败时先使用 Firecrawl 免 Key 云端浏览器抓取公网页面，仍失败再回退到 Parallel。

## 搜索渠道

渠道是否可用取决于配置、网络及提供方服务状态。需要密钥的渠道未配置密钥时会自动跳过。

| 类型 | 渠道示例 |
|---|---|
| 通用网页搜索 | Bing、360 搜索、搜狗、Startpage、Brave、Qwant、Google |
| AI 与搜索 API | 智谱、Z.AI、阿里百炼、Tavily（免 Key / API Key）、Exa、Firecrawl（免 Key / API Key）、Keenable（免 Key / API Key）、Brave Search API、百度千帆 AI 搜索、豆包搜索、Parallel Search、SerpBase |
| 学术与开发者 | arXiv、OpenAlex、OpenReview、DBLP、Stack Overflow、Wikipedia、MDN、npm、crates.io |
| 社区与中文内容 | Hacker News、Reddit、知乎、小红书、微信读书、Substack、AMiner |
| 扩展接入 | OpenCLI 浏览器自动化、MCP stdio 和技能脚本 |

Tavily、Firecrawl 和 Keenable 的免 Key 与 API Key 版本是独立渠道，免 Key 渠道安装后即可使用。Keenable 免 Key 额度按 IP 共享，配置 API Key 后使用独立账户额度。Exa、Firecrawl 和 Keenable 的带 Key 渠道、Brave Search API、百度千帆、豆包搜索、SerpBase、AMiner 和知乎 Skill 等需要相应 API Key 或凭据。各提供方可能调整免费额度、频次限制或费用；请以其当前文档和服务条款为准。Parallel Search 的匿名 MCP 接口无需 API Key，但仍受服务方限制。

## 快速开始

### 1. 安装依赖

```bash
git clone https://github.com/yourname/multi-search-aggregator.git
cd multi-search-aggregator
pip install -r requirements.txt
```

### 2. 配置密钥

```bash
cp .env.example .env
# 编辑 .env，按需填写：
# ZHIPU_API_KEY=your_key_here
# ZAI_API_KEY=your_key_here
# BAILIAN_API_KEY=your_key_here
# TAVILY_API_KEY=your_key_here
# EXA_API_KEY=your_key_here
# FIRECRAWL_API_KEY=your_key_here
# KEENABLE_API_KEY=your_key_here  # 可选；Keenable 也可免 Key 使用
# BRAVE_SEARCH_API_KEY=your_key_here
# BAIDU_QIANFAN_API_KEY=your_key_here
# DOUBAO_SEARCH_API_KEY=your_key_here
# SERPBASE_API_KEY=your_key_here
# AMINER_API_KEY=your_key_here
# ZHIHU_ACCESS_SECRET=your_key_here
```

将 `.env.example` 复制为 `.env` 后，未配置的密钥渠道会自动跳过；免 Key 渠道不需要填写密钥。也可以通过环境变量配置 API Key。

### 3. 启动服务

```bash
python server.py
```

默认监听 `http://localhost:8200`。访问首页开始搜索；API 文档见 `/docs`。使用 CLI：

```bash
python run_search.py "RISC-V vector extension"
python run_search.py "LDPC decoder" --engines zhipu_pro,arxiv --top 10 --json
python run_search.py "RISC-V" --mode parallel
```

## Docker 部署

先复制并编辑环境变量文件，为需要使用的渠道填写 API Key：

```bash
cp .env.example .env
# 编辑 .env，填写需要的密钥，例如 ZHIPU_API_KEY、TAVILY_API_KEY、EXA_API_KEY
```

在项目根目录构建并启动容器：

```bash
docker build -t multi-search-aggregator .
docker run -d \
  --name multi-search-aggregator \
  --restart unless-stopped \
  -p 8200:8200 \
  --env-file .env \
  multi-search-aggregator
```

`--env-file .env` 会在容器启动时注入 API 配置；密钥不会写入镜像。访问 `http://localhost:8200` 使用页面，MCP 地址为 `http://localhost:8200/mcp`。查看日志：

```bash
docker logs -f multi-search-aggregator
```

镜像包含项目的 Python 依赖。依赖 OpenCLI、Chrome、Node/npx 或仓库外技能脚本的可选渠道，需要另外在镜像中安装或挂载相应运行时和脚本。

## 搜索排序与调用模式

### 排序

默认以 BM25 相关性为主要信号，并综合摘要质量、发布时间、渠道权重、跨渠道重复情况和域名出现情况。中文查询和结果使用 jieba 分词，分词后会过滤 `search_agg/stopwords.txt` 中的词。修改停用词文件后，重启服务即可加载新列表。

排序会在不同渠道之间穿插结果以提高多样性，同时保证某渠道的结果不会越过该渠道上游排序更靠前的结果。

### 调用模式

| 模式 | 行为 |
|---|---|
| `quota_first`（默认） | 将所有已配置且可用的限额渠道随机排序，逐个请求；某个渠道返回结果后立即停止。只有所有限额渠道都失败或无结果时，才并发调用不限额渠道。 |
| `parallel` | 并发调用所有已启用、已配置且未处于冷却期的渠道；可能增加限额渠道的请求次数。 |

连续失败会指数增加冷却时间，最长 24 小时。普通故障从 5 分钟开始；识别为限流或配额耗尽、且服务方未提供 `Retry-After` 时从 1 小时开始。提供方的 `Retry-After` 会纳入冷却时间，最长不超过 24 小时。成功响应（包括正常无结果）会重置连续失败计数。冷却只保存在当前进程内存中。

`quota_first` 模式会把 Tavily、Firecrawl 免 Key、Keenable 免 Key 和带 Key 提供方一样视为限额渠道。每次搜索都会随机排列可用渠道，并逐个请求；有渠道返回结果就停止后续限额渠道。所有限额渠道都失败或无结果时，才并发调用不限额渠道。渠道失败仍会触发对应的冷却时间。

## Web 与 HTTP API

| 方法 | 地址 | 说明 |
|---|---|---|
| `GET` | `/` | Web 搜索页面 |
| `GET` | `/static/...` | 页面 CSS、脚本等静态资源 |
| `GET` / `POST` | `/api/search` | 聚合搜索 |
| `GET` | `/api/search/stream` | SSE 实时搜索进度和结果 |
| `GET` | `/api/engines` | 查看渠道启用和配置状态 |
| `POST` | `/api/engines/toggle` | 在当前运行期间启用或禁用渠道 |
| `GET` / `PUT` | `/api/config` | 读取或更新运行时配置 |
| `POST` | `/api/config/reload` | 重新加载 `config.yaml` |
| `GET` | `/api/health` | 服务与渠道健康状态 |
| `GET` | `/docs` | FastAPI 交互式 API 文档 |

搜索 API 示例：

```bash
curl "http://localhost:8200/api/search?q=RISC-V&top_k=20&mode=quota_first"

curl -X POST http://localhost:8200/api/search \
  -H "Content-Type: application/json" \
  -d '{"query":"transformer attention","top_k":20,"mode":"parallel","engines":["zhipu_pro","arxiv"]}'
```

`/api/search/stream` 使用 SSE 推送 `engine_done`、`result`、`complete` 等事件。

## MCP 接口

服务启动后，MCP Streamable HTTP 地址为：

```text
http://localhost:8200/mcp
```

客户端连接该地址后可调用两个工具。工具参数面向搜索和网页阅读任务，不需要传入 `objective`、`session_id` 或 `model_name`。

### `web_search`

| 参数 | 类型 | 必需 | 默认值 | 说明 |
|---|---|---:|---:|---|
| `search_queries` | `string[]` | 是 | — | 一个或多个搜索短语 |
| `max_results` | `integer` | 否 | `20` | 返回结果上限，范围为 1 至服务配置上限（默认最多 200） |

返回 `results`、`total_results` 等字段；结果包含标题、URL、摘要和渠道，发布时间可用时也会提供。

### `web_fetch`

| 参数 | 类型 | 必需 | 默认值 | 说明 |
|---|---|---:|---:|---|
| `urls` | `string[]` | 是 | — | 1 至 20 个公网网页 URL；重复 URL 只抓取一次，结果按输入顺序返回 |
| `search_queries` | `string[]` | 否 | — | 可选的内容关注短语，用于挑选摘要 |
| `full_content` | `boolean` | 否 | `false` | 是否返回完整的可读页面文本 |
| `max_chars_total` | `integer` | 否 | `25000` | 所有摘要和全文共用的字符数上限，超出部分截断 |

每个页面返回 URL、摘要；标题和全文（若请求且可用）也会包含在内。抓取失败时页面条目包含 `error`，整体响应包含 `truncated` 标记。

本地抓取失败后，服务先将可确认的公网 URL 交给 Firecrawl 免 Key 抓取接口，由 Firecrawl 云端浏览器渲染页面；Firecrawl 仍无法抓取的页面再交给 Parallel。私有地址、本机地址或无法确认公网归属的地址不会转发。两个后备服务都可能受频次限制；若都不可用，页面错误仍会返回。

## 配置

`config.yaml` 控制服务器监听地址、端口、超时、并发数、搜索结果上限、渠道权重和启用状态。API Key 从环境变量或 `.env` 读取，不要写入版本控制中的配置文件。

```yaml
server:
  host: "0.0.0.0"
  port: 8200

search:
  default_top_k: 10
  max_top_k: 200
  default_timeout: 35

engine_overrides:
  parallel_search:
    enabled: true
```

## 项目结构

```text
multi-search-aggregator/
├── server.py                    # Web、REST API 和 /mcp 服务
├── mcp.py                       # MCP 工具定义：web_search、web_fetch
├── verify_mcp.py                # MCP 接口与参数 schema 验证脚本
├── Dockerfile                   # 容器镜像构建文件
├── .dockerignore                # 排除密钥和本地构建文件
├── run_search.py                # CLI 搜索入口
├── config.yaml                  # 服务和渠道配置
├── static/                      # Web 页面及其静态资源
└── search_agg/
    ├── runner.py                # 渠道调度、限额优先与并发模式
    ├── ranker.py                # 去重、BM25 与结果排序
    ├── stopwords.txt            # 中文搜索停用词
    └── engines/                  # 搜索渠道实现
```

## 参与贡献与许可证

欢迎提交问题、修复和新渠道实现。项目使用 [MIT License](LICENSE)。
