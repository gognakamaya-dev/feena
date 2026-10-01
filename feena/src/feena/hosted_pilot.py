"""Supervise the MCP service and its loopback-only disposable demo."""
from __future__ import annotations

import os
from pathlib import Path
import re
import signal
import subprocess
import sys
import threading
import time
from urllib.request import urlopen


def hosted_environment(source: dict[str, str]) -> dict[str, str]:
    env = dict(source)
    if len(env.get("FEENA_MCP_TOKEN", "")) < 32:
        raise ValueError("FEENA_MCP_TOKEN must contain at least 32 characters")
    host = env.get("RENDER_EXTERNAL_HOSTNAME", "")
    if not re.fullmatch(r"[a-z0-9](?:[a-z0-9-]*[a-z0-9])?\.onrender\.com", host):
        raise ValueError("Expected Render's assigned onrender.com hostname")
    env["FEENA_MCP_PUBLIC_URL"] = f"https://{host}/mcp"
    env["FEENA_MCP_HOSTS"] = host
    return env


def main() -> int:
    env = hosted_environment(dict(os.environ))
    os.umask(0o077)
    out = Path(env.get("FEENA_EVIDENCE_DIR", "/app/data/runs"))
    out.mkdir(parents=True, exist_ok=True)
    # Fail at startup rather than accepting runs on an unwritable disk.
    probe = out / ".write-check"
    probe.write_text("")
    probe.unlink()
    root = Path.cwd()
    demo = root / "examples/resilient-checkout"
    stopped = threading.Event()
    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, lambda *_: stopped.set())
    children = []
    try:
        demo_env = {k: v for k, v in env.items() if k in ("PATH", "HOME", "LANG")}
        children.append(subprocess.Popen([
            sys.executable, "-m", "gunicorn", "--workers", "1", "--threads", "2",
            "--bind", "127.0.0.1:5057", "--chdir", str(demo), "app:app",
        ], env=demo_env))
        deadline = time.monotonic() + 20
        while not stopped.is_set():
            if children[0].poll() is not None or time.monotonic() > deadline:
                raise RuntimeError("Disposable demo failed to start")
            try:
                with urlopen("http://127.0.0.1:5057/api/health", timeout=1) as response:
                    if response.status == 200:
                        break
            except OSError:
                stopped.wait(0.1)
        if stopped.is_set():
            return 0
        children.append(subprocess.Popen([
            sys.executable, "-m", "feena.mcp_server", "--transport", "http",
            "--host", "0.0.0.0", "--port", env.get("PORT", "10000"),
            "--target", "http://127.0.0.1:5057", "--config", str(demo / "feena.yaml"),
            "--out", str(out),
        ], env=env))
        while not stopped.wait(0.25):
            if any(child.poll() is not None for child in children):
                return 1
        return 0
    finally:
        for child in reversed(children):
            if child.poll() is None:
                child.terminate()
        for child in reversed(children):
            try:
                child.wait(timeout=10)
            except subprocess.TimeoutExpired:
                child.kill()
                child.wait()


if __name__ == "__main__":
    raise SystemExit(main())
