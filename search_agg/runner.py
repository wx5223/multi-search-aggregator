"""并发调度主逻辑 — ThreadPoolExecutor 全并发 + 引擎执行分发"""
from __future__ import annotations

import json, os, re, sys, time, urllib.parse, subprocess, platform as _platform, logging
import inspect
from dataclasses import dataclass
from collections.abc import Callable
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading
import signal as _signal
from requests.exceptions import ConnectionError as RequestsConnectionError
from requests.exceptions import Timeout as RequestsTimeout

_IS_UNIX = _platform.system() != 'Windows'

# Windows 兼容：setsid / killpg
if _IS_UNIX:
    _SETSID = os.setsid
else:
    _SETSID = None  # Windows 不支持 preexec_fn=os.setsid

def _kill_proc_tree(proc, sig=_signal.SIGTERM):
    """跨平台进程清理"""
    if _IS_UNIX:
        try:
            os.killpg(os.getpgid(proc.pid), sig)
        except (ProcessLookupError, OSError):
            proc.terminate()
    else:
        proc.terminate()

from .config import WORKSPACE, TIMEOUT, MAX_WORKERS, RETRY_DELAY, OUTPUT_DIR
from .config import BAILIAN_KEY, ZHIPU_KEY, ZAI_KEY, AMINER_KEY, ZHIHU_KEY
from .models import SearchResult
from .engines import ENGINES, get_enabled_engines
from .engines.zhipu import call_zhipu_api
from .engines.zai import call_zai_api
from .engines.bailian import call_bailian_mcp
from .engines.serpbase import call_serpbase_api
from .engines.opencli import call_opencli
from .engines.web_fetch import call_web_fetch, parse_html_links
from .engines.mcp_stdio import call_mcp_stdio
from .engines.parallel import call_parallel_search
from .engines.tavily import call_tavily, call_tavily_key
from .engines.exa import call_exa
from .engines.firecrawl import call_firecrawl
from .engines.brave import call_brave_search
from .engines.baidu_qianfan import call_baidu_qianfan_search
from .engines.doubao_search import call_doubao_search
from .engines.skill import call_skill
from . import ranker

log = logging.getLogger("search_agg.runner")

_LIMITED_BASE_COOLDOWN_SECONDS = 300
_LIMITED_RATE_LIMIT_BASE_SECONDS = 60 * 60
_LIMITED_MAX_COOLDOWN_SECONDS = 24 * 60 * 60
_LIMITED_STATE_LOCK = threading.Lock()
_LIMITED_CALL_LOCK = threading.Lock()
_LIMITED_UNAVAILABLE_UNTIL: dict[str, float] = {}
_LIMITED_FAILURE_COUNTS: dict[str, int] = {}
_LIMITED_LAST_COOLDOWN_SECONDS: dict[str, int] = {}
_LIMITED_ENGINE_CURSOR = 0


@dataclass
class EngineOutcome:
    results: list[SearchResult]
    status: str
    error_type: str | None = None
    http_status: int | None = None
    retry_after_seconds: int | None = None
    retryable: bool = False


def _failure_outcome(exc: Exception) -> EngineOutcome:
    response = getattr(exc, "response", None)
    http_status = getattr(response, "status_code", None)
    retry_after = None
    headers = getattr(response, "headers", {}) or {}
    retry_after_header = headers.get("Retry-After") if hasattr(headers, "get") else None
    if retry_after_header:
        try:
            retry_after = max(0, int(float(retry_after_header)))
        except (TypeError, ValueError):
            try:
                retry_at = parsedate_to_datetime(retry_after_header)
                if retry_at.tzinfo is None:
                    retry_at = retry_at.replace(tzinfo=timezone.utc)
                retry_after = max(
                    0,
                    int((retry_at - datetime.now(timezone.utc)).total_seconds()),
                )
            except (TypeError, ValueError, OverflowError):
                retry_after = None

    is_timeout = isinstance(
        exc, (TimeoutError, RequestsTimeout, subprocess.TimeoutExpired)
    ) or "timeout" in type(exc).__name__.lower()
    error_text = " ".join((str(exc), getattr(response, "text", "") or "")).lower()
    quota_error = any(
        marker in error_text
        for marker in ("rate limit", "rate_limit", "quota", "too many requests", "limit exceeded")
    )
    status = (
        "rate_limited" if http_status == 429 or quota_error
        else "timeout" if is_timeout
        else "error"
    )
    retryable = is_timeout or isinstance(exc, RequestsConnectionError) or http_status in (408, 425) or (
        isinstance(http_status, int) and http_status >= 500
    )
    return EngineOutcome(
        results=[],
        status=status,
        error_type=type(exc).__name__,
        http_status=http_status if isinstance(http_status, int) else None,
        retry_after_seconds=retry_after,
        retryable=retryable,
    )


def _limited_group(engine: dict) -> str:
    return engine.get("quota_group") or engine["id"]


def _provider_is_configured(engine: dict) -> bool:
    required_env = engine.get("required_env")
    return not required_env or bool(os.environ.get(required_env))


def _limited_is_unavailable(engine: dict, now: float | None = None) -> bool:
    now = time.monotonic() if now is None else now
    with _LIMITED_STATE_LOCK:
        group = _limited_group(engine)
        unavailable_until = _LIMITED_UNAVAILABLE_UNTIL.get(group, 0)
        if unavailable_until <= now:
            _LIMITED_UNAVAILABLE_UNTIL.pop(group, None)
            return False
        return True


def _limited_cooldown_remaining(engine: dict) -> int:
    with _LIMITED_STATE_LOCK:
        remaining = _LIMITED_UNAVAILABLE_UNTIL.get(_limited_group(engine), 0) - time.monotonic()
        return max(0, int(remaining + 0.999))


def _mark_limited_unavailable(
    engine: dict,
    failure_status: str,
    retry_after_seconds: int | None = None,
) -> dict:
    with _LIMITED_STATE_LOCK:
        group = _limited_group(engine)
        failures = _LIMITED_FAILURE_COUNTS.get(group, 0) + 1
        _LIMITED_FAILURE_COUNTS[group] = failures
        exponent = min(failures - 1, 20)
        base_cooldown = (
            _LIMITED_RATE_LIMIT_BASE_SECONDS
            if failure_status == "rate_limited" and retry_after_seconds is None
            else _LIMITED_BASE_COOLDOWN_SECONDS
        )
        cooldown = min(
            _LIMITED_MAX_COOLDOWN_SECONDS,
            base_cooldown * (2 ** exponent),
        )
        previous_cooldown = _LIMITED_LAST_COOLDOWN_SECONDS.get(group, 0)
        if previous_cooldown:
            cooldown = max(
                cooldown,
                min(_LIMITED_MAX_COOLDOWN_SECONDS, previous_cooldown * 2),
            )
        if retry_after_seconds is not None:
            cooldown = max(
                cooldown,
                min(_LIMITED_MAX_COOLDOWN_SECONDS, max(0, retry_after_seconds)),
            )
        _LIMITED_LAST_COOLDOWN_SECONDS[group] = cooldown
        _LIMITED_UNAVAILABLE_UNTIL[group] = time.monotonic() + cooldown
        return {"consecutive_failures": failures, "cooldown_seconds": cooldown}


def _mark_limited_available(engine: dict) -> None:
    with _LIMITED_STATE_LOCK:
        group = _limited_group(engine)
        _LIMITED_FAILURE_COUNTS.pop(group, None)
        _LIMITED_LAST_COOLDOWN_SECONDS.pop(group, None)
        _LIMITED_UNAVAILABLE_UNTIL.pop(group, None)


def _choose_limited_engines(engines: list[dict]) -> list[dict]:
    global _LIMITED_ENGINE_CURSOR
    now = time.monotonic()
    with _LIMITED_STATE_LOCK:
        available = []
        seen_groups = set()
        for engine in engines:
            group = _limited_group(engine)
            if group in seen_groups:
                continue
            seen_groups.add(group)
            unavailable_until = _LIMITED_UNAVAILABLE_UNTIL.get(group, 0)
            if unavailable_until <= now:
                _LIMITED_UNAVAILABLE_UNTIL.pop(group, None)
                available.append(engine)
        if not available:
            return []
        start = _LIMITED_ENGINE_CURSOR % len(available)
        _LIMITED_ENGINE_CURSOR += 1
        return available[start:] + available[:start]


def _notify_progress(
    callback: Callable | None,
    engine_name: str,
    count: int,
    status: str,
) -> None:
    if callback is None:
        return
    try:
        signature = inspect.signature(callback)
        signature.bind(engine_name, count, status)
    except (TypeError, ValueError):
        try:
            callback(engine_name, count)
        except Exception:
            pass
    else:
        try:
            callback(engine_name, count, status)
        except Exception:
            pass


def run_one(
    engine: dict,
    query: str,
    retry_transient: bool = False,
    timeout: int | None = None,
) -> EngineOutcome:
    """执行单个渠道，并保留空结果与调用故障的区别。"""
    name = engine["name"]
    etype = engine["type"]
    request_timeout = timeout or TIMEOUT
    w = __import__("search_agg.config", fromlist=["WEIGHTS"]).WEIGHTS.get(name, 5)
    retry = engine.get("retry", False)

    def _exec(attempt_timeout: int):
        try:
            if etype == "zhipu_api":
                raw = call_zhipu_api(engine["engine"], query, timeout=attempt_timeout)
                return ranker.normalize_results(raw, name, w)
            elif etype == "serpbase_api":
                raw = call_serpbase_api(query, timeout=attempt_timeout)
                return ranker.normalize_results(raw, name, w)
            elif etype == "zai_api":
                raw = call_zai_api(query, timeout=attempt_timeout)
                return ranker.normalize_results(raw, name, w)
            elif etype == "bailian_mcp":
                raw = call_bailian_mcp(query, timeout=attempt_timeout)
                return ranker.normalize_results(raw, name, w)
            elif etype == "tavily_api":
                raw = call_tavily(query, timeout=attempt_timeout)
                return ranker.normalize_results(raw, name, w)
            elif etype == "tavily_key_api":
                raw = call_tavily_key(query, timeout=attempt_timeout)
                return ranker.normalize_results(raw, name, w)
            elif etype == "exa_api":
                raw = call_exa(query, timeout=attempt_timeout)
                return ranker.normalize_results(raw, name, w)
            elif etype == "firecrawl_api":
                raw = call_firecrawl(query, timeout=attempt_timeout)
                return ranker.normalize_results(raw, name, w)
            elif etype == "brave_api":
                raw = call_brave_search(query, timeout=attempt_timeout)
                return ranker.normalize_results(raw, name, w)
            elif etype == "baidu_qianfan_api":
                raw = call_baidu_qianfan_search(query, timeout=attempt_timeout)
                return ranker.normalize_results(raw, name, w)
            elif etype == "doubao_search_api":
                raw = call_doubao_search(query, timeout=attempt_timeout)
                return ranker.normalize_results(raw, name, w)
            elif etype == "parallel_mcp":
                raw = call_parallel_search(query, timeout=attempt_timeout)
                return ranker.normalize_results(raw, name, w)
            elif etype == "opencli" or etype == "opencli_heavy":
                raw = call_opencli(engine["site"], query, timeout=attempt_timeout)
                return ranker.normalize_results(raw, name, w)
            elif etype == "web_fetch":
                encoded_q = urllib.parse.quote(query)
                url = engine["url_tpl"].replace("{q}", encoded_q)
                html = call_web_fetch(url, timeout=attempt_timeout)
                if html:
                    return parse_html_links(html, name, w)
                return []
            elif etype == "skill":
                cmd = engine["cmd"].replace("{q}", query.replace('"', '\\"'))
                try:
                    # Process env var substitution
                    cmd = cmd.replace("$AMINER_API_KEY", AMINER_KEY or os.environ.get("AMINER_API_KEY", ""))
                    env = os.environ.copy()
                    import re as _re2
                    m = _re2.search(r'ZHIHU_ACCESS_SECRET=([^\s]+)', cmd)
                    if m:
                        env["ZHIHU_ACCESS_SECRET"] = m.group(1)
                        cmd = _re2.sub(r'ZHIHU_ACCESS_SECRET=\S+\s+', '', cmd)

                    proc = subprocess.Popen(
                        ["bash" if _IS_UNIX else "cmd", "-c" if _IS_UNIX else "/c", cmd],
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        cwd=WORKSPACE,
                        env=env,
                        preexec_fn=_SETSID,
                    )
                    stdout, _ = proc.communicate(timeout=attempt_timeout)
                    t = stdout.decode("utf-8", errors="replace").strip()
                    if proc.returncode != 0:
                        raise RuntimeError("Skill command exited unsuccessfully")
                    if t and t != "[]":
                        lines = t.split('\n')
                        json_str = '\n'.join(
                            l for l in lines
                            if l.strip() and not l.strip().startswith('[Cost]')
                        )
                        if not json_str.strip():
                            json_str = t
                        raw_resp = json.loads(json_str)
                        if isinstance(raw_resp, dict):
                            for key in ('data', 'items', 'results', 'hits'):
                                if key in raw_resp and isinstance(raw_resp[key], list):
                                    raw = raw_resp[key]
                                    break
                            else:
                                raw = []
                        else:
                            raw = raw_resp
                        return ranker.normalize_results(raw, name, w)
                except subprocess.TimeoutExpired:
                    _kill_proc_tree(proc, _signal.SIGTERM)
                    try:
                        proc.wait(timeout=3)
                    except subprocess.TimeoutExpired:
                        _kill_proc_tree(proc, _signal.SIGKILL if _IS_UNIX else _signal.SIGTERM)
                        proc.wait(timeout=1)
                    raise
                except Exception:
                    try:
                        _kill_proc_tree(proc)
                    except Exception:
                        pass
                    raise
            elif etype == "mcp_stdio":
                raw = call_mcp_stdio(
                    command=engine["command"],
                    args=engine.get("args", []),
                    tool=engine["tool"],
                    tool_args=engine["tool_args"],
                    query=query,
                    timeout=attempt_timeout,
                )
                return ranker.normalize_results(raw, name, w)
        except Exception as exc:
            return _failure_outcome(exc)

    def _run_once(attempt_timeout: int) -> EngineOutcome:
        outcome = _exec(attempt_timeout)
        if isinstance(outcome, EngineOutcome):
            return outcome
        results = outcome if isinstance(outcome, list) else []
        return EngineOutcome(results, "success" if results else "no_results")

    retry_enabled = bool(retry and retry_transient)
    attempt_timeout = max(1, request_timeout // 2) if retry_enabled else request_timeout
    outcome = _run_once(attempt_timeout)
    if retry_enabled and outcome.retryable:
        time.sleep(RETRY_DELAY)
        outcome = _run_once(attempt_timeout)
    return outcome


def aggregate(
    query: str,
    top_n: int = 50,
    engine_filter: list[str] | None = None,
    custom_timeout: int | None = None,
    progress_callback: Callable | None = None,
    mode: str = "quota_first",
) -> dict:
    """主入口：并发调度所有引擎，去重排序，返回结果

    Args:
        query: 搜索查询词
        top_n: 返回前 N 条结果
        engine_filter: 限定引擎 id 列表（None=全部启用引擎）
        custom_timeout: 自定义超时（None=使用配置默认值）
        progress_callback: 可选回调，签名为 (engine_name, count[, status])
                           每个引擎完成后调用
        mode: quota_first 依次尝试限额渠道再回退；parallel 并发调用未冷却渠道
    """
    effective_timeout = custom_timeout if custom_timeout is not None else TIMEOUT
    if mode not in ("quota_first", "parallel"):
        raise ValueError("mode must be 'quota_first' or 'parallel'")

    engines = get_enabled_engines(engine_filter)
    limited_engines = [e for e in engines if e.get("quota_limited")]
    fallback_engines = [e for e in engines if not e.get("quota_limited")]

    print(f"\n{'='*60}")
    print(f"🔍 {query}")
    mode_label = "限额优先" if mode == "quota_first" else "全并发"
    print(f"   {len(engines)} 引擎 | {mode_label} | {effective_timeout}s超时")
    print(f"{'='*60}")

    t0 = time.time()
    all_results = []
    stats = {engine["name"]: 0 for engine in engines}
    engine_status = {engine["name"]: "not_called" for engine in engines}
    engine_errors = {}

    def run_parallel_batch(batch: list[dict], timeout: int) -> None:
        if not batch:
            return
        executor = ThreadPoolExecutor(max_workers=MAX_WORKERS)
        try:
            future_to_engine = {
                executor.submit(
                    run_one,
                    engine,
                    query,
                    retry_transient=not engine.get("quota_limited", False),
                    timeout=timeout,
                ): engine
                for engine in batch
            }
            done_set = set()
            batch_outcomes = {}
            try:
                for future in as_completed(future_to_engine, timeout=max(1, timeout)):
                    engine = future_to_engine[future]
                    done_set.add(future)
                    try:
                        outcome = future.result()
                    except Exception as exc:
                        outcome = _failure_outcome(exc)
                    batch_outcomes[engine["name"]] = outcome
            except (TimeoutError, KeyboardInterrupt):
                pass

            for future, engine in future_to_engine.items():
                name = engine["name"]
                if future in done_set:
                    continue
                future.cancel()
                outcome = EngineOutcome([], "timeout", "TimeoutError", retryable=True)
                batch_outcomes[name] = outcome

            limited_groups = {}
            progress_events = []
            for engine in batch:
                name = engine["name"]
                outcome = batch_outcomes[name]
                results = outcome.results
                stats[name] = len(results)
                all_results.extend(results)
                if engine.get("quota_limited"):
                    limited_groups.setdefault(_limited_group(engine), []).append((engine, outcome))
                    status = "available" if results else outcome.status
                else:
                    status = "available" if results else outcome.status
                engine_status[name] = status
                if outcome.status in {"error", "timeout", "rate_limited"}:
                    details = {
                        "status": outcome.status,
                        "error_type": outcome.error_type,
                    }
                    if outcome.http_status is not None:
                        details["http_status"] = outcome.http_status
                    engine_errors[name] = details
                    log.warning(
                        "Channel %s failed: status=%s error_type=%s http_status=%s",
                        name, outcome.status, outcome.error_type, outcome.http_status,
                    )
                progress_events.append((name, len(results)))

            # Several variants can share one quota account. Count one failure
            # per group per search, and reset the group if any variant worked.
            for group, group_outcomes in limited_groups.items():
                if any(outcome.results for _, outcome in group_outcomes):
                    _mark_limited_available(group_outcomes[0][0])
                    continue
                failed = next(
                    (outcome for _, outcome in group_outcomes
                     if outcome.status in {"error", "timeout", "rate_limited"}),
                    None,
                )
                if failed is None:
                    continue
                cooldown = _mark_limited_unavailable(
                    group_outcomes[0][0], failed.status, failed.retry_after_seconds
                )
                for engine, outcome in group_outcomes:
                    engine_status[engine["name"]] = "temporarily_unavailable"
                    details = engine_errors.setdefault(engine["name"], {})
                    details.update(cooldown)
                    if outcome.status == "no_results":
                        details["status"] = "shared_quota_group_unavailable"

            for name, count in progress_events:
                _notify_progress(progress_callback, name, count, engine_status[name])

        finally:
            # Do not let a slow provider hold the whole search open after the
            # batch deadline. Running HTTP calls still rely on their own timeout.
            executor.shutdown(wait=False, cancel_futures=True)

    if mode == "quota_first":
        configured_limited = [e for e in limited_engines if _provider_is_configured(e)]
        for engine in limited_engines:
            name = engine["name"]
            if not _provider_is_configured(engine):
                engine_status[name] = "not_configured"
            elif _limited_is_unavailable(engine):
                engine_status[name] = "temporarily_unavailable"
                engine_errors[name] = {
                    "status": "cooldown",
                    "cooldown_seconds_remaining": _limited_cooldown_remaining(engine),
                }

        deadline = time.monotonic() + effective_timeout
        fallback_reserve = min(10, max(1, effective_timeout // 3))
        if configured_limited:
            if not _LIMITED_CALL_LOCK.acquire(blocking=False):
                for engine in configured_limited:
                    if engine_status[engine["name"]] == "not_called":
                        engine_status[engine["name"]] = "skipped_busy"
            else:
                try:
                    candidates = _choose_limited_engines(configured_limited)
                    limited_timeout_cap = max(
                        1, min(effective_timeout, 10, max(3, effective_timeout // 3))
                    )
                    for candidate_index, selected in enumerate(candidates):
                        remaining_budget = deadline - time.monotonic() - fallback_reserve
                        if remaining_budget < 1:
                            for skipped in candidates[candidate_index:]:
                                engine_status[skipped["name"]] = "skipped_budget"
                            break

                        selected_name = selected["name"]
                        limited_timeout = max(
                            1, min(limited_timeout_cap, int(remaining_budget))
                        )
                        outcome = run_one(
                            selected,
                            query,
                            retry_transient=False,
                            timeout=limited_timeout,
                        )
                        stats[selected_name] = len(outcome.results)
                        all_results.extend(outcome.results)

                        if outcome.results:
                            _mark_limited_available(selected)
                            engine_status[selected_name] = "available"
                            for skipped in candidates[candidate_index + 1:]:
                                engine_status[skipped["name"]] = "skipped_result_found"
                        elif outcome.status == "no_results":
                            _mark_limited_available(selected)
                            engine_status[selected_name] = "no_results"
                        else:
                            cooldown = _mark_limited_unavailable(
                                selected, outcome.status, outcome.retry_after_seconds
                            )
                            engine_status[selected_name] = "temporarily_unavailable"
                            details = {
                                "status": outcome.status,
                                "error_type": outcome.error_type,
                                **cooldown,
                            }
                            if outcome.http_status is not None:
                                details["http_status"] = outcome.http_status
                            engine_errors[selected_name] = details
                            log.warning(
                                "Limited channel %s failed: status=%s error_type=%s http_status=%s cooldown=%ss",
                                selected_name, outcome.status, outcome.error_type,
                                outcome.http_status, cooldown["cooldown_seconds"],
                            )
                            for sibling in limited_engines:
                                if _limited_group(sibling) == _limited_group(selected):
                                    engine_status[sibling["name"]] = "temporarily_unavailable"
                                    if sibling["name"] != selected_name:
                                        engine_errors[sibling["name"]] = {
                                            "status": "shared_quota_group_cooldown",
                                            **cooldown,
                                        }

                        _notify_progress(
                            progress_callback,
                            selected_name,
                            len(outcome.results),
                            engine_status[selected_name],
                        )
                        if outcome.results:
                            break
                finally:
                    _LIMITED_CALL_LOCK.release()

        # Try other healthy limited channels before the unlimited fallback.
        if not all_results:
            remaining = max(1, int(deadline - time.monotonic()))
            run_parallel_batch(fallback_engines, remaining)
    else:
        parallel_batch = list(fallback_engines)
        for engine in limited_engines:
            if not _provider_is_configured(engine):
                engine_status[engine["name"]] = "not_configured"
            elif _limited_is_unavailable(engine):
                engine_status[engine["name"]] = "temporarily_unavailable"
                engine_errors[engine["name"]] = {
                    "status": "cooldown",
                    "cooldown_seconds_remaining": _limited_cooldown_remaining(engine),
                }
            else:
                parallel_batch.append(engine)
        run_parallel_batch(parallel_batch, effective_timeout)

    elapsed = time.time() - t0
    ok_count = sum(1 for c in stats.values() if c > 0)
    total_results = sum(stats.values())
    timed_out = any(status == "timeout" for status in engine_status.values()) or any(
        details.get("status") == "timeout" for details in engine_errors.values()
    )

    # 统计报告
    print(
        f"\n⏱️  {elapsed:.1f}s | ✅{ok_count} "
        f"❌{len(stats)-ok_count} 📦{total_results}\n"
    )
    print("引擎报告:")
    for name, count in sorted(stats.items(), key=lambda x: (-x[1], x[0])):
        icon = "✅" if count > 0 else (
            "⚠️" if engine_status.get(name) == "temporarily_unavailable" else "❌"
        )
        print(f"  {icon} {name:20s} {count:>3d} 条 [{engine_status.get(name)}]")

    # 去重
    deduped = ranker.dedup(all_results)

    # 动态域名权威度
    domain_boost = ranker._domain_freq_boost(deduped)

    # 默认使用 BM25 排序，不加载本地 embedding 模型。
    try:
        bm25_scores = ranker.compute_bm25_scores(query, deduped)
    except Exception as e:
        print(f"BM25 排序失败 ({e})")
        bm25_scores = {}

    # 排序
    now = datetime.now()
    for r in deduped:
        r._score = ranker.score_result(
            r, query, now,
            bm25_scores=bm25_scores,
            domain_boost=domain_boost,
        )
    deduped.sort(key=lambda r: r._score, reverse=True)
    ranked = ranker.diversify(deduped, top_n)

    # 附加元数据
    for r in ranked:
        r._vec_sim = 0.0
        try:
            d = r.url.split("/")[2].lower().replace("www.", "")
            r._domain_auth = domain_boost.get(d, 1.0)
        except Exception:
            r._domain_auth = 1.0

    # 输出 Top-N
    show_n = min(top_n, len(ranked))
    print(f"\n📊 {total_results}→{len(deduped)}去重→Top{show_n}\n")
    if ranked:
        for i, r in enumerate(ranked[:show_n], 1):
            line = f"{i}. [{r.source}] {r.title}"
            if r.publish_time:
                line += f" ({r.publish_time})"
            print(line)
            print(f"   {r.url}")
            if r.summary:
                s = r.summary[:200]
                if len(r.summary) > 200:
                    s += "..."
                print(f"   {s}")
            print()

    # 保存结果
    output = {
        "query": query,
        "timestamp": now.isoformat(),
        "elapsed_seconds": round(elapsed, 2),
        "engine_stats": stats,
        "engine_status": engine_status,
        "engine_errors": engine_errors,
        "search_mode": mode,
        "total_engines": len(engines),
        "ok_engines": ok_count,
        "timed_out": timed_out,
        "raw_results": total_results,
        "deduped": len(deduped),
        "top": len(ranked),
        "results": [
            {
                "rank": i + 1,
                "title": r.title,
                "url": r.url,
                "summary": r.summary,
                "source": r.source,
                "publish_time": r.publish_time,
                "author": r.author,
                "score": round(r._score, 4),
                "relevance": r._relevance,
                "vec_sim": getattr(r, '_vec_sim', 0),
                "domain_auth": getattr(r, '_domain_auth', 1.0),
                "engine_weight": r.engine_weight,
                "snippet_len": r.snippet_len,
            }
            for i, r in enumerate(ranked)
        ],
    }
    # os.makedirs(OUTPUT_DIR, exist_ok=True)
    # out_path = os.path.join(OUTPUT_DIR, "results.json")
    # with open(out_path, "w", encoding="utf-8") as f:
    #     json.dump(output, f, indent=2, ensure_ascii=False)
    # print(f"\n💾 → {out_path}")

    return output
