"""Skill 脚本引擎（子进程调用外部 Python 脚本）"""
import json, os, subprocess, platform as _platform
import signal as _signal
from ..config import WORKSPACE, TIMEOUT

_IS_UNIX = _platform.system() != 'Windows'


def call_skill(cmd_template: str, query: str, timeout: int = TIMEOUT) -> list[dict]:
    """执行外部 skill 脚本并解析返回的 JSON 结果"""
    # 替换环境变量引用
    cmd = cmd_template
    cmd = cmd.replace("$AMINER_API_KEY", os.environ.get("AMINER_API_KEY", ""))
    cmd = cmd.replace("{q}", query.replace('"', '\\"'))

    # 知乎 skill 特殊处理：注入 ZHIHU_ACCESS_SECRET 环境变量
    env = os.environ.copy()
    if "ZHIHU_ACCESS_SECRET=" in cmd:
        # 从 cmd 中提取知乎 key
        import re as _re
        m = _re.search(r'ZHIHU_ACCESS_SECRET=([^\s]+)', cmd)
        if m:
            env["ZHIHU_ACCESS_SECRET"] = m.group(1)
            # 移除 cmd 中的 key 注入 prefix
            cmd = _re.sub(r'ZHIHU_ACCESS_SECRET=\S+\s+', '', cmd)

    proc = None
    try:
        proc = subprocess.Popen(
            ["bash", "-c", cmd],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=WORKSPACE,
            env=env,
            preexec_fn=os.setsid if _IS_UNIX else None,  # new process group for tree kill
        )
        stdout, _ = proc.communicate(timeout=timeout)
        t = stdout.decode("utf-8", errors="replace").strip()
        if proc.returncode == 0 and t and t != "[]":
            # 去掉可能混入的非 JSON 行
            lines = t.split('\n')
            json_str = '\n'.join(
                l for l in lines
                if l.strip() and not l.strip().startswith('[Cost]')
            )
            if not json_str.strip():
                json_str = t
            raw_resp = json.loads(json_str)
            # AMiner 返回 {"data": [...]} 结构，知乎返回 {"items": [...]}
            if isinstance(raw_resp, dict):
                for key in ('data', 'items', 'results', 'hits'):
                    if key in raw_resp and isinstance(raw_resp[key], list):
                        return raw_resp[key]
                return []
            else:
                return raw_resp
    except subprocess.TimeoutExpired:
        if _IS_UNIX:
            try:
                os.killpg(os.getpgid(proc.pid), _signal.SIGTERM)
            except (ProcessLookupError, OSError):
                proc.terminate()
        else:
            proc.terminate()
        try:
            proc.wait(timeout=3)
        except subprocess.TimeoutExpired:
            if _IS_UNIX:
                try:
                    os.killpg(os.getpgid(proc.pid), _signal.SIGKILL)
                except (ProcessLookupError, OSError):
                    proc.kill()
            else:
                proc.kill()
            proc.wait(timeout=1)
    except Exception:
        if _IS_UNIX:
            try:
                os.killpg(os.getpgid(proc.pid), _signal.SIGTERM)
            except Exception:
                pass
        else:
            try:
                proc.terminate()
            except Exception:
                pass
    return []
