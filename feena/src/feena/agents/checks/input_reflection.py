"""Detect whether user input is reflected into the page WITHOUT escaping.

Surface check, not an exploit. It submits a unique, inert marker followed by a harmless `<b>`
tag and checks whether the tag comes back as raw HTML (vulnerable) or escaped to `&lt;b&gt;`
(safe). The `<b>` matters: a purely alphanumeric marker is reflected identically whether or not
the app escapes anything, so it can't tell a fixed page from a broken one.

When a browser is available it inspects the RENDERED DOM, so it catches reflection performed by
client-side JavaScript (invisible to a raw HTTP fetch); otherwise it falls back to httpx.
Feena stops at "this input is reflected unescaped, look here" and never ships a payload.
"""
from __future__ import annotations

import secrets

import httpx

from ...config import Config
from ...findings import Finding, Kind, Severity, Step
from ...sandbox import Sandbox

SURFACES = [("/", "q"), ("/search", "q")]


def _unescaped(html: str, marker: str) -> bool:
    """Raw `<b>` survived right after the marker, and it was not also escaped."""
    return f"{marker}<b>" in (html or "") and f"{marker}&lt;b&gt;" not in (html or "")


def run(cfg: Config, sandbox: Sandbox, renderer=None) -> list[Finding]:
    findings: list[Finding] = []
    base = sandbox.base_url.rstrip("/")

    for path, param in SURFACES:
        marker = "MALX" + secrets.token_hex(4)
        html, rendered = _get(base, path, {param: marker + "<b>x</b>"}, renderer)
        if not _unescaped(html, marker):
            continue
        idx = html.find(marker)
        window = html[max(0, idx - 20): idx + len(marker) + 30]
        where = "rendered DOM" if rendered else "HTML response"
        findings.append(Finding(
            kind=Kind.INPUT_HANDLING,
            severity=Severity.MEDIUM,
            title=f"User input reflected in {where} at {path}",
            detail=("An inert `<b>` tag sent as input came back as raw HTML"
                    + (" via client-side JavaScript" if rendered else "")
                    + ", so the value is reflected without escaping. That is the surface for "
                    "reflected XSS. Feena sends only an inert tag and does not attempt an exploit."),
            agent="hostile",
            steps=[Step(action="http_get", target=f"{path}?{param}=<marker>",
                        note=f"inert <b> reflected unescaped in {where}")],
            evidence={"url": base + path, "context": window},
            repro={"type": "reflected", "path": path, "param": param, "rendered": rendered},
        ))
    return findings


def _get(base: str, path: str, params: dict, renderer):
    """Return (html, rendered?). Prefer the rendered DOM; fall back to httpx."""
    if renderer is not None:
        html = renderer.rendered_html(path, params)
        if html:
            return html, True
    try:
        r = httpx.get(base + path, params=params, timeout=5.0)
        if "html" in r.headers.get("content-type", "").lower():
            return r.text, False
    except httpx.HTTPError:
        pass
    return "", False
