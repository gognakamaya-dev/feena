"""Check for missing security response headers.

Purely observational: fetch a page and read the response headers. No payloads, no state change.
"""
from __future__ import annotations

import httpx

from ...config import Config
from ...findings import Finding, Kind, Severity, Step
from ...sandbox import Sandbox

# header -> (why it matters, severity if missing)
EXPECTED = {
    "content-security-policy": ("limits where scripts/styles can load from; core XSS defence", Severity.MEDIUM),
    "x-content-type-options": ("stops MIME sniffing (should be 'nosniff')", Severity.LOW),
    "strict-transport-security": ("forces HTTPS on subsequent visits", Severity.LOW),
    "x-frame-options": ("or a CSP frame-ancestors; blocks clickjacking", Severity.LOW),
}


def run(cfg: Config, sandbox: Sandbox) -> list[Finding]:
    findings: list[Finding] = []
    url = sandbox.base_url.rstrip("/") + "/"
    try:
        resp = httpx.get(url, timeout=5.0)
    except httpx.HTTPError:
        return findings

    present = {k.lower() for k in resp.headers.keys()}
    for header, (why, sev) in EXPECTED.items():
        if header not in present:
            findings.append(
                Finding(
                    kind=Kind.WEAK_HEADERS,
                    severity=sev,
                    title=f"Missing response header: {header}",
                    detail=f"The app does not send `{header}`. This header {why}.",
                    agent="hostile",
                    steps=[Step(action="http_get", target="/", note=f"response lacked {header}")],
                    evidence={"url": url, "status": resp.status_code},
                    repro={"type": "header", "path": "/", "header": header},
                )
            )
    return findings
