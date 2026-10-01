"""Single-workspace MCP service for operator-approved browser scenarios."""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import secrets
import signal
import sys
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import urlsplit

from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings
from starlette.responses import HTMLResponse, JSONResponse

from .config import load_config
from .sandbox import attach


class Runs:
    def __init__(self, config: Path, target: str, out: Path, timeout: int = 120):
        self.config = config.resolve()
        self.scenarios = load_config(config).scenarios
        if not self.scenarios:
            raise ValueError("Configure at least one scenario before starting MCP")
        self.target = attach(target).base_url
        self.out = out.resolve()
        self.timeout = timeout
        self.jobs: dict[str, dict] = {}
        self.tasks: dict[str, asyncio.Task] = {}

    def list_scenarios(self) -> list[dict]:
        return [{"name": s.name, "goal": s.goal,
                 "profiles": [p.name for p in s.profiles]} for s in self.scenarios]

    async def start(self, scenario: str) -> dict:
        selected = next((s for s in self.scenarios if s.name == scenario), None)
        if selected is None:
            raise ValueError("Unknown configured scenario")
        if any(not t.done() for t in self.tasks.values()):
            raise ValueError("A run is already active; wait or cancel it first")
        if len(self.jobs) >= 100:
            raise ValueError("Run limit reached; operator must archive results and restart")
        run_id = uuid.uuid4().hex
        folder = self.out / run_id
        folder.mkdir(parents=True, mode=0o700)
        (folder / "scenario.json").write_text(selected.model_dump_json())
        self.jobs[run_id] = {"run_id": run_id, "scenario": scenario, "status": "running"}
        self.tasks[run_id] = asyncio.create_task(self._execute(run_id, folder))
        return dict(self.jobs[run_id])

    async def _execute(self, run_id: str, folder: Path):
        job = self.jobs[run_id]
        process = None
        try:
            # Browser workers do not inherit provider tokens or the MCP access token.
            env = {k: v for k, v in os.environ.items() if k in (
                "PATH", "HOME", "LANG", "LD_LIBRARY_PATH", "PLAYWRIGHT_BROWSERS_PATH")}
            process = await asyncio.create_subprocess_exec(
                sys.executable, "-m", "mallory.mcp_worker", str(folder), self.target,
                env=env, stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL,
                start_new_session=True,
            )
            await asyncio.wait_for(process.wait(), self.timeout)
            if process.returncode != 0:
                job.update(status="error", reason="Worker failed; inspect local run artifacts")
            else:
                job.update(status="completed", results=json.loads((folder / "results.json").read_text()))
        except TimeoutError:
            job.update(status="timed_out", reason="Server execution budget exceeded")
        except asyncio.CancelledError:
            job.update(status="cancelled")
        except Exception:  # noqa: BLE001 - never leak worker exceptions to remote clients
            job.update(status="error", reason="Run could not be completed")
        finally:
            if process is not None:
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                await process.wait()

    def get(self, run_id: str) -> dict:
        if run_id not in self.jobs:
            raise ValueError("Unknown run ID")
        return dict(self.jobs[run_id])

    async def cancel(self, run_id: str) -> dict:
        self.get(run_id)
        task = self.tasks[run_id]
        if not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
            self.jobs[run_id]["status"] = "cancelled"
        return self.get(run_id)

    async def close(self):
        for run_id in list(self.tasks):
            await self.cancel(run_id)


class AccessToken:
    def __init__(self, app, token: str, public_url: str | None = None):
        self.app, self.token = app, token
        self.public_url = public_url
        if public_url:
            parsed = urlsplit(public_url)
            if (parsed.scheme != "https" or not parsed.hostname or parsed.username
                    or parsed.password or parsed.query or parsed.fragment or parsed.path != "/mcp"):
                raise ValueError("MALLORY_MCP_PUBLIC_URL must be an HTTPS URL ending in /mcp")

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http":
            private_headers = {"Cache-Control": "no-store", "Referrer-Policy": "no-referrer",
                               "X-Content-Type-Options": "nosniff", "X-Frame-Options": "DENY"}
            if scope["path"] == "/" and scope["method"] == "GET":
                await HTMLResponse(Path(__file__).with_name("onboarding.html").read_text(),
                                   headers=private_headers)(scope, receive, send)
                return
            if scope["path"] == "/connection-info" and scope["method"] == "GET":
                await JSONResponse({"endpoint": self.public_url}, headers=private_headers)(scope, receive, send)
                return
            if scope["path"] == "/health" and scope["method"] == "GET":
                await JSONResponse({"service": "Mallory MCP", "status": "ready",
                                    "endpoint": "/mcp", "authentication": "Bearer token"})(scope, receive, send)
                return
            headers = dict(scope["headers"])
            supplied = headers.get(b"authorization", b"")
            if not secrets.compare_digest(supplied, ("Bearer " + self.token).encode()):
                await JSONResponse({"error": "Unauthorized"}, status_code=401,
                                   headers={"WWW-Authenticate": "Bearer"})(scope, receive, send)
                return
            if scope["path"] == "/connection-check" and scope["method"] == "GET":
                await JSONResponse({"connected": True}, headers=private_headers)(scope, receive, send)
                return
        await self.app(scope, receive, send)


def create_server(runs: Runs, hosts: list[str]) -> FastMCP:
    server = FastMCP(
        "Mallory UX QA", instructions="List configured journeys, start one, then poll get_run. "
        "Runs mutate disposable test data. A failed journey needs investigation, not an automatic fix.",
        stateless_http=True, json_response=True,
        max_request_body_size=65536,
        transport_security=TransportSecuritySettings(
            allowed_hosts=hosts, allowed_origins=[f"https://{h}" for h in hosts if "*" not in h]),
    )

    @server.tool()
    def list_scenarios() -> list[dict]:
        """List operator-approved user journeys and network profiles."""
        return runs.list_scenarios()

    @server.tool()
    async def start_run(scenario: str) -> dict:
        """Start one configured journey asynchronously. Mutates the configured test app."""
        return await runs.start(scenario)

    @server.tool()
    def get_run(run_id: str) -> dict:
        """Get execution state and sanitized pass/fail results. Raw evidence stays server-local."""
        return runs.get(run_id)

    @server.tool()
    async def cancel_run(run_id: str) -> dict:
        """Stop a run and its browser processes. Does not undo application writes."""
        return await runs.cancel(run_id)

    return server


def http_app(server: FastMCP, runs: Runs, token: str):
    app = server.streamable_http_app()
    original = app.router.lifespan_context

    @asynccontextmanager
    async def lifespan(application):
        async with original(application):
            try:
                yield
            finally:
                await runs.close()

    app.router.lifespan_context = lifespan
    return AccessToken(app, token, os.environ.get("MALLORY_MCP_PUBLIC_URL"))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--target", required=True)
    parser.add_argument("--out", type=Path, default=Path(".mallory/mcp"))
    parser.add_argument("--transport", choices=["stdio", "http"], default="stdio")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=3000)
    args = parser.parse_args()
    hosts = ["localhost:*", "127.0.0.1:*", *filter(None, os.environ.get("MALLORY_MCP_HOSTS", "").split(","))]
    runs = Runs(args.config, args.target, args.out)
    server = create_server(runs, hosts)
    if args.transport == "stdio":
        server.run(transport="stdio")
    else:
        import uvicorn
        token = os.environ.get("MALLORY_MCP_TOKEN", "")
        if len(token) < 32:
            parser.error("HTTP requires MALLORY_MCP_TOKEN with at least 32 characters")
        uvicorn.run(http_app(server, runs, token), host=args.host, port=args.port)


if __name__ == "__main__":
    main()
