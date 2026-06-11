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
            return []

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
                if d.get("id") == 1 and "result" in d:
                    for c in d["result"].get("content", []):
                        t = c.get("text", "")
                        if t and not t.startswith("No results"):
                            parsed = json.loads(t)
                            if isinstance(parsed, list):
                                return parsed
                    break
            except (json.JSONDecodeError, ValueError):
                continue
        return []
    except Exception:
        return []
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
    return []
