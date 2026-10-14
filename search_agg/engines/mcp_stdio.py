"""MCP stdio 直连引擎（绕过 mcporter daemon，自行管理子进程生命周期）"""
import json, os, time, subprocess, platform as _platform
import select as _sel
from ..config import WORKSPACE, TIMEOUT

_IS_UNIX = _platform.system() != 'Windows'


def _mcp_send(proc, msg):
    proc.stdin.write((json.dumps(msg) + "\n").encode())
    proc.stdin.flush()


def _mcp_read(proc, timeout_s=15):
    ready, _, _ = _sel.select([proc.stdout], [], [], timeout_s)
    if ready:
        return proc.stdout.readline().decode().strip()
    return None


def call_mcp_stdio(
    command: str,
    args: list[str],
    tool: str,
    tool_args: dict,
    query: str,
    timeout: int = TIMEOUT,
) -> list[dict]:
    """MCP stdio 直连：自行管理子进程生命周期，不依赖 mcporter daemon"""
    proc = None
    try:
        cmd = [command] + args
        _env = os.environ.copy()
        _env.pop("OPENAI_LOG", None)  # 防止 OpenAI SDK 调试输出阻塞进程

        proc = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            cwd=WORKSPACE,
            env=_env,
        )

        # 1. Initialize
        _mcp_send(
            proc,
            {
                "jsonrpc": "2.0",
                "method": "initialize",
                "id": 0,
                "params": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {},
                    "clientInfo": {"name": "search-agg", "version": "8.1"},
                },
            },
        )
        init_resp = _mcp_read(proc, 15)
        if not init_resp:
            raise TimeoutError("MCP server did not initialize in time")

        # 2. Notification
        _mcp_send(
            proc,
            {"jsonrpc": "2.0", "method": "notifications/initialized"},
        )

        # 3. Tool call — substitute {q} with query
        resolved_args = {}
        for k, v in tool_args.items():
            resolved_args[k] = query if v == "{q}" else v

        _mcp_send(
            proc,
            {
                "jsonrpc": "2.0",
                "method": "tools/call",
                "id": 1,
                "params": {"name": tool, "arguments": resolved_args},
            },
        )

        # 4. Read responses (may have notification lines + final result)
        deadline = time.time() + timeout
        while time.time() < deadline:
            line = _mcp_read(proc, min(10, deadline - time.time()))
            if not line:
                continue  # 超时但未到 deadline，继续等
            try:
                d = json.loads(line)
            except json.JSONDecodeError:
                continue
            if d.get("id") == 1 and "error" in d:
                raise RuntimeError("MCP tool call failed")
            if d.get("id") == 1 and "result" in d:
                result = d["result"]
                if result.get("isError") or result.get("is_error"):
                    raise RuntimeError("MCP tool call failed")
                content_blocks = result.get("content", [])
                for content in content_blocks:
                    text = content.get("text", "")
                    if not text:
                        continue
                    if text.lower().startswith("no results"):
                        return []
                    try:
                        parsed = json.loads(text)
                    except json.JSONDecodeError as exc:
                        raise ValueError("MCP tool returned invalid JSON") from exc
                    if isinstance(parsed, list):
                        return parsed
                    raise ValueError("MCP tool returned an invalid result list")
                if not content_blocks:
                    raise ValueError("MCP tool returned an empty response")
                raise ValueError("MCP tool returned no parseable search result")
        raise TimeoutError("MCP tool did not return a result in time")
    finally:
        if proc:
            try:
                proc.terminate()
                proc.wait(timeout=2)
            except subprocess.TimeoutExpired:
                proc.kill()
                try:
                    proc.wait(timeout=1)
                except Exception:
                    pass
            except Exception:
                pass
            # pkill 残留的 MCP server 子进程 (Unix only)
            if _IS_UNIX:
                for pn in ["bing-cn-mcp-enhanced"]:
                    try:
                        subprocess.run(
                            ["pkill", "-9", "-f", pn],
                            stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL,
                            timeout=3,
                        )
                    except Exception:
                        pass
