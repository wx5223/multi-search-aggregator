"""opencli 浏览器搜索引擎"""
import json, os, subprocess
from ..config import WORKSPACE, TIMEOUT, OPENCLI_PATH


def call_opencli(site: str, query: str, timeout: int = TIMEOUT) -> list[dict]:
    """调用 opencli 搜索引擎"""
    proc = subprocess.Popen(
        ["bash", "-c", f'{OPENCLI_PATH} {site} search "{query}" -f json'],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        cwd=WORKSPACE,
        env=os.environ.copy(),
    )
    try:
        stdout, _ = proc.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        proc.terminate()
        try:
            proc.wait(timeout=3)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=1)
        raise

    text = stdout.decode("utf-8", errors="replace").strip()
    if proc.returncode != 0:
        raise RuntimeError("OpenCLI exited unsuccessfully")
    if not text or text == "[]":
        return []
    payload = json.loads(text)
    if not isinstance(payload, list):
        raise ValueError("OpenCLI returned an invalid results list")
    return payload
