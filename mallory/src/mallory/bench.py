"""Benchmark harness: run the hostile agent across many apps and aggregate the results.

This is the month-one milestone — point Mallory at a set of open-source apps and see what it
finds in the wild. Three rules keep it legitimate and are enforced, not just documented:

- **Local only.** Every target is CLONED and BUILT into a Mallory sandbox (a throwaway,
  no-egress container). The harness never accepts a URL to a hosted instance. You test code you
  run yourself, never someone else's live service.
- **Detection only.** It runs the same non-destructive hostile checks as a normal run.
- **Own-or-authorised.** The default target set is intentionally-vulnerable apps published for
  security testing (OWASP Juice Shop, NodeGoat, DVWA). Add your own apps only if you own them or
  have permission to test them.

Target kinds:
- ``process``: import a local WSGI app and serve it in-thread. Used for the bundled examples so
  the harness runs end-to-end with no Docker. Not for third-party code.
- ``image``:   pull a prebuilt image (e.g. the OWASP benchmark images) and sandbox it.
- ``repo``:    git-clone a repo and build it from its Dockerfile/compose in the sandbox.
"""
from __future__ import annotations

import importlib
import threading
import time
import wsgiref.simple_server
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from .agents.hostile import HostileAgent
from .config import Config, TargetConfig, UserConfig
from .findings import Finding, Severity, confirm, dedup
from .sandbox import Sandbox
from .verification import verify_finding


@dataclass
class Target:
    name: str
    kind: str                      # "process" | "image" | "repo"
    port: int
    healthcheck: str = "/"
    users: list[dict] = field(default_factory=list)
    # process:
    module: str | None = None      # "examples.taskflow.app:app"
    # image:
    image: str | None = None
    # repo:
    repo: str | None = None
    ref: str | None = None
    notes: str = ""


@dataclass
class AppResult:
    name: str
    status: str                    # "ok" | "build_failed" | "unreachable" | "error"
    findings: list[Finding] = field(default_factory=list)
    dropped: int = 0
    duration_s: float = 0.0
    detail: str = ""

    @property
    def counts(self) -> dict[str, int]:
        c = {s.value: 0 for s in Severity}
        for f in self.findings:
            c[f.severity.value] += 1
        return c


def load_targets(path: str | Path) -> list[Target]:
    data = yaml.safe_load(Path(path).read_text()) or {}
    return [Target(**t) for t in data.get("targets", [])]


# ---------- bring-up per kind ----------

class _ProcessApp:
    """Serve an imported WSGI app in a background thread; yield a Sandbox pointing at it."""

    def __init__(self, module_spec: str):
        self.module_spec = module_spec
        self.srv = None

    def __enter__(self) -> Sandbox:
        spec_str, _, attr = self.module_spec.partition(":")
        attr = attr or "app"
        if spec_str.endswith(".py") or "/" in spec_str:
            # Load by file path with a unique module name (two examples are both 'app.py').
            import importlib.util

            path = Path(spec_str).resolve()
            uniq = "mallory_bench_" + path.parent.name.replace("-", "_")
            spec = importlib.util.spec_from_file_location(uniq, path)
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
        else:
            mod = importlib.import_module(spec_str)
        app = getattr(mod, attr)
        if hasattr(mod, "init_db"):
            mod.init_db()

        class _Quiet(wsgiref.simple_server.WSGIRequestHandler):
            def log_message(self, *a):
                pass

        self.srv = wsgiref.simple_server.make_server("127.0.0.1", 0, app, handler_class=_Quiet)
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()
        time.sleep(0.3)
        port = self.srv.server_address[1]
        return Sandbox(base_url=f"http://127.0.0.1:{port}")

    def __exit__(self, *exc):
        if self.srv:
            self.srv.shutdown()


def _bring_up(target: Target):
    """Return a context manager yielding a Sandbox, per target kind."""
    if target.kind == "process":
        if not target.module:
            raise ValueError(f"{target.name}: process target needs 'module'")
        return _ProcessApp(target.module)
    if target.kind in ("image", "repo"):
        # Real path: build a no-egress sandbox from a pulled image or a cloned repo.
        # Uses the Docker-backed SandboxManager and needs a Docker daemon; not exercised in
        # environments without one. Implemented in sandbox.py's manager; wired here.
        from .sandbox import SandboxManager

        cfg = _target_config(target)
        return SandboxManager(cfg)
    raise ValueError(f"{target.name}: unknown kind '{target.kind}'")


def _target_config(target: Target) -> Config:
    return Config(
        target=TargetConfig(compose=target.repo or "", service="web", port=target.port,
                            healthcheck=target.healthcheck),
        users=[UserConfig(**u) for u in target.users],
    )


# ---------- run ----------

def _replayer(sandbox: Sandbox, cfg: Config):
    return lambda finding: verify_finding(finding, cfg, sandbox)


def run_target(target: Target) -> AppResult:
    started = time.time()
    try:
        with _bring_up(target) as sandbox:
            if not sandbox.health_ok(target.healthcheck, timeout=5.0):
                return AppResult(target.name, "unreachable", duration_s=time.time() - started,
                                 detail=f"healthcheck {target.healthcheck} not OK")
            cfg = _target_config(target)
            findings = dedup(HostileAgent(cfg, sandbox).run())
            confirmed, dropped = confirm(findings, _replayer(sandbox, cfg))
            return AppResult(target.name, "ok", confirmed, len(dropped), time.time() - started)
    except Exception as e:  # noqa: BLE001 - one bad target must not sink the whole bench
        return AppResult(target.name, "error", duration_s=time.time() - started, detail=str(e))


def run_bench(targets: list[Target], only: str | None = None) -> list[AppResult]:
    return [run_target(t) for t in targets if not only or t.name == only]


# ---------- report ----------

def render_bench_md(results: list[AppResult]) -> str:
    ok = [r for r in results if r.status == "ok"]
    total_findings = sum(len(r.findings) for r in ok)
    apps_with_findings = sum(1 for r in ok if r.findings)
    lines = [
        "# Mallory benchmark",
        "",
        f"{len(results)} target(s): {len(ok)} tested, "
        f"{sum(1 for r in results if r.status != 'ok')} could not be brought up. "
        f"{total_findings} confirmed finding(s) across {apps_with_findings} app(s).",
        "",
        "| App | Status | Crit | High | Med | Low | Time |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for r in results:
        c = r.counts
        if r.status == "ok":
            lines.append(f"| {r.name} | ok | {c['critical']} | {c['high']} | {c['medium']} "
                         f"| {c['low']} | {r.duration_s:.0f}s |")
        else:
            lines.append(f"| {r.name} | {r.status} | - | - | - | - | {r.duration_s:.0f}s |")

    # Per-app detail for apps with findings.
    for r in ok:
        if not r.findings:
            continue
        lines += ["", f"## {r.name}", ""]
        for f in sorted(r.findings, key=lambda x: x.severity.value):
            lines.append(f"- **{f.severity.value.upper()}** · {f.kind.value} · {f.title}")

    failed = [r for r in results if r.status != "ok"]
    if failed:
        lines += ["", "## Could not be brought up", ""]
        for r in failed:
            lines.append(f"- {r.name}: {r.status}" + (f" — {r.detail}" if r.detail else ""))
    return "\n".join(lines)


def write_bench(results: list[AppResult], out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "benchmark.md"
    path.write_text(render_bench_md(results))
    return path
