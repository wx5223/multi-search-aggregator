"""Utilities: URL denoising and process cleanup."""
import os, time, subprocess
import signal as _signal


def kill_proc_tree(proc):
    """彻底杀死进程树：PGID kill + pkill 子进程名 + 确认回收。"""
    if proc is None:
        return
    try:
        # 1. 先尝试 SIGTERM 整个进程组
        try:
            os.killpg(os.getpgid(proc.pid), _signal.SIGTERM)
        except (ProcessLookupError, OSError, ValueError):
            try:
                proc.terminate()
            except (ProcessLookupError, OSError):
                pass

        try:
            proc.wait(timeout=2)
        except subprocess.TimeoutExpired:
            # 2. SIGKILL 进程组
            try:
                os.killpg(os.getpgid(proc.pid), _signal.SIGKILL)
            except (ProcessLookupError, OSError, ValueError):
                try:
                    proc.kill()
                except (ProcessLookupError, OSError):
                    pass
            try:
                proc.wait(timeout=1)
            except subprocess.TimeoutExpired:
                pass
    except Exception:
        pass


def cleanup_mcp_orphans():
    """搜索结束后统一清理所有残留的 MCP server 孤儿进程 (Unix only)。"""
    import platform as _platform
    if _platform.system() == 'Windows':
        return
    killed = 0
    orphan_names = ["bing-cn-mcp-enhanced"]
    for name in orphan_names:
        try:
            subprocess.run(
                ["pkill", "-f", name],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                timeout=3)
            time.sleep(0.1)
            subprocess.run(
                ["pkill", "-9", "-f", name],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                timeout=3)
            killed += 1
            print(f"  🧹 已清理孤儿进程: {name}")
        except Exception:
            pass
    if killed:
        print(f"  🧹 共清理 {killed} 类孤儿进程")
