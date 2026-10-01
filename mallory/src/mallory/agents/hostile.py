"""The hostile agent: an attacker with a normal account, confined to the sandbox.

Runs a curated set of non-destructive, observation-based checks against the sandboxed app. HTTP
checks (headers, SQLi, access control) run over httpx. The XSS checks are render-aware: when a
browser is available the agent starts one shared Renderer and hands it to them so they inspect
the rendered DOM (catching client-rendered SPAs); otherwise they fall back to httpx.

Refuses to run against any target not produced by a Mallory-built no-egress sandbox.
"""
from __future__ import annotations

from ..config import Config
from ..findings import Finding
from ..render import Renderer, browser_available
from ..sandbox import Sandbox, assert_sandboxed
from .checks import access_control, headers, input_reflection, sqli, stored_xss
from ..plugins import load_plugin_checks

# HTTP-level checks: signature run(cfg, sandbox).
HTTP_CHECKS = [
    headers.run,             # observational: missing security headers
    sqli.run,                # detection-only: is an input interpreted as SQL?
    access_control.run,      # observational: IDOR / missing auth via two seeded accounts
]
# Render-aware checks: signature run(cfg, sandbox, renderer). renderer may be None.
RENDER_CHECKS = [
    input_reflection.run,    # reflected XSS surface, in the rendered DOM when possible
    stored_xss.run,          # stored XSS, in the rendered DOM when possible
]


class HostileAgent:
    name = "hostile"

    def __init__(self, cfg: Config, sandbox: Sandbox):
        self.cfg = cfg
        self.sandbox = sandbox

    def run(self) -> list[Finding]:
        assert_sandboxed(self.sandbox, self.sandbox.base_url)

        findings: list[Finding] = []

        # HTTP checks + any installed plugin checks (plugin contract stays run(cfg, sandbox)).
        for check in HTTP_CHECKS + [fn for _, fn in load_plugin_checks()]:
            try:
                findings.extend(check(self.cfg, self.sandbox))
            except Exception:
                continue

        # One shared browser for the render-aware checks, if we can start it.
        renderer = None
        if browser_available():
            try:
                renderer = Renderer(self.sandbox.base_url).start()
            except Exception:
                renderer = None
        try:
            for check in RENDER_CHECKS:
                try:
                    findings.extend(check(self.cfg, self.sandbox, renderer))
                except Exception:
                    continue
        finally:
            if renderer is not None:
                renderer.close()

        return findings
