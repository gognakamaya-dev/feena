"""Managed preview launcher; token stays in a private local file."""
import os
import secrets
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
private = ROOT / ".mallory" / "mcp-token"
private.parent.mkdir(parents=True, exist_ok=True)
if not private.exists():
    with open(private, "x", opener=lambda path, flags: os.open(path, flags, 0o600)) as handle:
        handle.write(secrets.token_urlsafe(48))
env = {**os.environ, "MALLORY_MCP_TOKEN": private.read_text().strip()}
demo = subprocess.Popen([
    sys.executable, "-m", "flask", "--app", str(ROOT / "examples/resilient-checkout/app.py"),
    "run", "--host", "127.0.0.1", "--port", "5056",
])
try:
    subprocess.run([
        sys.executable, "-m", "mallory.mcp_server", "--transport", "http",
        "--host", "0.0.0.0", "--port", "3000", "--target", "http://127.0.0.1:5056",
        "--config", str(ROOT / "examples/resilient-checkout/mallory.yaml"),
        "--out", str(ROOT / ".mallory/mcp"),
    ], env=env, check=True)
finally:
    demo.terminate()
    demo.wait()
