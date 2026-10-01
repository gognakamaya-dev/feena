"""Detect stored (persistent) XSS by observation. Detection only — never exploitation.

Stored XSS is worse than reflected: the payload is saved once and served to every later viewer,
so no victim has to click a crafted link. Detecting it black-box means three steps:

1. Log in, then discover forms that persist input (a task title, a comment, a profile field).
2. Submit a unique, INERT marker containing a harmless `<b>` tag — no <script>, no event
   handlers, no javascript: URIs. Nothing executes; the tag only reveals the escaping context.
3. Re-fetch other pages and check whether the marker comes back with its `<b>` intact (raw HTML)
   rather than escaped to `&lt;b&gt;`. If it survived unescaped on a page we did not submit to,
   the input is stored and rendered without escaping.

Like the reflection and SQLi checks, this proves "your input persists unescaped here" and stops.
It does not deliver a working payload, steal anything, or run script. Runs only under the
hostile agent, which runs only inside a Feena-built no-egress sandbox.
"""
from __future__ import annotations

import re
import secrets

import httpx

from ...config import Config
from ...findings import Finding, Kind, Severity, Step
from ...sandbox import Sandbox

# Inert probe: a unique token plus a bold tag. <b> renders nothing dangerous; its survival as
# raw HTML (vs &lt;b&gt;) is the whole signal.
def _marker() -> str:
    return f"MALX{secrets.token_hex(4)}"


def _probe(marker: str) -> str:
    return f"{marker}<b>x</b>"


# Pages a small SaaS commonly renders user content on; crawling adds whatever it links to.
SEED_PAGES = ["/", "/tasks", "/dashboard", "/notes", "/posts", "/comments", "/profile", "/feed"]

# Never follow links that would end our own session or destroy data while crawling.
SKIP_LINK = re.compile(r"(logout|log-out|signout|sign-out|delete|destroy|remove)", re.IGNORECASE)

_FORM = re.compile(r"<form\b[^>]*>(.*?)</form>", re.IGNORECASE | re.DOTALL)
# Attribute values may be double-quoted, single-quoted, or unquoted (common in hand/AI-written
# HTML), so every attribute regex accepts all three forms.
_VAL = r'(?:"([^"]*)"|\'([^\']*)\'|([^\s>]+))'
_ACTION = re.compile(r"action\s*=\s*" + _VAL, re.IGNORECASE)
_METHOD = re.compile(r"method\s*=\s*" + _VAL, re.IGNORECASE)
_INPUT = re.compile(r"<(?:input|textarea)\b[^>]*?\bname\s*=\s*" + _VAL, re.IGNORECASE)
_HREF = re.compile(r"href\s*=\s*(?:\"(/[^\"]*)\"|'(/[^']*)'|(/[^\s>]+))", re.IGNORECASE)


def _first(groups) -> str:
    """Pick the populated capture from the quoted/unquoted alternation."""
    for g in groups:
        if g:
            return g
    return ""


def run(cfg: Config, sandbox: Sandbox, renderer=None) -> list[Finding]:
    if renderer is not None:
        try:
            return _run_rendered(cfg, sandbox, renderer)
        except Exception:
            pass  # fall back to the httpx path on any browser trouble
    return _run_httpx(cfg, sandbox)


def _run_rendered(cfg: Config, sandbox: Sandbox, renderer) -> list[Finding]:
    """Browser path: discover forms in the rendered DOM, submit by interaction, re-read the DOM.
    Catches stored XSS in client-rendered apps that the httpx path cannot see."""
    base = sandbox.base_url.rstrip("/")
    user = cfg.users[0] if cfg.users else None
    label = user.label if user else "anonymous"

    # Log in with httpx if we have credentials (public forms need none), bridge into the browser.
    if user:
        with httpx.Client(base_url=base, timeout=8.0, follow_redirects=True) as client:
            _do_login(client, user.email, user.password)
            renderer.add_cookies_from_httpx(client)

    # crawl pages via the rendered DOM
    pages: list[str] = []
    to_visit = list(SEED_PAGES)
    seen: set[str] = set()
    while to_visit and len(pages) < 15:
        path = to_visit.pop(0)
        if path in seen or SKIP_LINK.search(path):
            continue
        seen.add(path)
        html = renderer.rendered_html(path)
        if not html:
            continue
        pages.append(path)
        for href in renderer.links()[:20]:
            if href and href not in seen and href not in to_visit:
                to_visit.append(href)

    # submit an inert marker to each discovered form, by real interaction
    submitted: list[tuple[str, str]] = []
    meta: dict[str, dict] = {}   # marker -> how it was submitted (for the regression test)
    for path in pages:
        renderer.rendered_html(path)
        forms = renderer.find_forms()
        for i in range(len(forms)):
            renderer.rendered_html(path)                 # fresh page (submit may navigate away)
            forms_now = renderer.find_forms()
            if i >= len(forms_now) or not forms_now[i].get("fields"):
                continue
            marker = _marker()
            if renderer.submit_form(forms_now[i], _probe(marker)):
                submitted.append((marker, forms_now[i].get("action", path)))
                meta[marker] = {"form_page": path, "action": forms_now[i].get("action", path),
                                "method": forms_now[i].get("method", "post"),
                                "fields": forms_now[i].get("fields", [])}

    # re-read pages from the rendered DOM and look for unescaped, persisted markers
    findings: list[Finding] = []
    seen_markers: set[str] = set()
    for path in pages:
        body = renderer.rendered_html(path)
        for marker, action in submitted:
            if _is_unescaped(body, marker) and marker not in seen_markers:
                seen_markers.add(marker)
                stored = _norm(action) != _norm(path)
                findings.append(Finding(
                    kind=Kind.STORED_XSS,
                    severity=Severity.HIGH if stored else Severity.MEDIUM,
                    title=(f"Stored XSS: input persists unescaped at {path} (rendered DOM)"
                           if stored else f"Persistent unescaped input at {path} (rendered DOM)"),
                    detail=("An inert marker submitted through a form appears as raw HTML in the "
                            f"rendered DOM at {path} (a `<b>` tag survived unescaped), including "
                            "any client-side rendering. A real script payload would run for every "
                            "viewer. Detection only; the probe is inert."),
                    agent="hostile",
                    steps=[Step(action="login", target=label),
                           Step(action="form_submit", target=action, note="inert <b> marker"),
                           Step(action="http_get", target=path, note="marker unescaped in DOM")],
                    evidence={"url": base + path, "submitted_to": base + action},
                    repro={"type": "stored_xss", "rendered": True, "login": bool(user),
                           "page": path, **meta.get(marker, {"form_page": path, "action": action,
                                                             "method": "post", "fields": []})},
                ))
    return findings


def _run_httpx(cfg: Config, sandbox: Sandbox) -> list[Finding]:
    base = sandbox.base_url.rstrip("/")
    user = cfg.users[0] if cfg.users else None

    client = httpx.Client(base_url=base, timeout=8.0, follow_redirects=True)
    try:
        if user:
            _do_login(client, user.email, user.password)  # best-effort; public forms need none

        # 1) crawl a little to collect pages and the forms on them
        pages = _discover_pages(client)
        forms = _discover_forms(client, pages)
        if not forms:
            return []

        # 2) submit an inert marker to every text field of every discovered form.
        #    Re-authenticate first: discovery may have touched something that ended the session.
        if user:
            _do_login(client, user.email, user.password)
        submitted: list[tuple[str, str]] = []  # (marker, form action)
        meta: dict[str, dict] = {}
        for action, method, fields in forms:
            marker = _marker()
            payload = {name: _probe(marker) for name in fields}
            try:
                if method == "post":
                    client.post(action, data=payload)
                else:
                    client.get(action, params=payload)
                submitted.append((marker, action))
                meta[marker] = {"form_page": action, "action": action, "method": method,
                                "fields": list(fields)}
            except httpx.HTTPError:
                continue

        # 3) re-fetch pages and look for a marker that survived unescaped on a page we did NOT
        #    just submit to (that persistence is what makes it stored, not merely reflected)
        findings: list[Finding] = []
        seen: set[str] = set()
        for path in pages:
            try:
                body = client.get(path).text
            except httpx.HTTPError:
                continue
            for marker, action in submitted:
                if _is_unescaped(body, marker) and marker not in seen:
                    seen.add(marker)
                    stored = _norm(action) != _norm(path)  # showed up somewhere else
                    findings.append(Finding(
                        kind=Kind.STORED_XSS,
                        severity=Severity.HIGH if stored else Severity.MEDIUM,
                        title=(f"Stored XSS: input persists unescaped at {path}"
                               if stored else f"Persistent unescaped input at {path}"),
                        detail=("An inert marker submitted through a form came back as raw HTML "
                                f"on {path} (a `<b>` tag survived unescaped). Content is stored "
                                "and rendered without escaping, so a real script payload would "
                                "run for every viewer. Detection only; the probe is inert."),
                        agent="hostile",
                        steps=[
                            Step(action="login", target=user.label if user else "anonymous"),
                            Step(action="form_submit", target=action, note="inert <b> marker"),
                            Step(action="http_get", target=path, note="marker rendered unescaped"),
                        ],
                        evidence={"url": base + path, "submitted_to": base + action},
                        repro={"type": "stored_xss", "rendered": False, "login": bool(user),
                               "page": path, **meta.get(marker, {"form_page": action, "action": action,
                                                                 "method": "post", "fields": []})},
                    ))
        return findings
    finally:
        client.close()


def _do_login(client: httpx.Client, email: str, password: str) -> bool:
    for path in ("/api/login", "/login", "/api/auth/login"):
        try:
            r = client.post(path, json={"email": email, "password": password})
            if r.status_code < 400 and (client.cookies or "authorization" in r.headers):
                return True
            r = client.post(path, data={"email": email, "password": password})
            if r.status_code < 400 and client.cookies:
                return True
        except httpx.HTTPError:
            continue
    return bool(client.cookies)


def _discover_pages(client: httpx.Client) -> list[str]:
    pages: list[str] = []
    to_visit = list(SEED_PAGES)
    seen: set[str] = set()
    while to_visit and len(pages) < 15:
        path = to_visit.pop(0)
        if path in seen or SKIP_LINK.search(path):
            continue
        seen.add(path)
        try:
            r = client.get(path)
        except httpx.HTTPError:
            continue
        if r.status_code >= 400 or "html" not in r.headers.get("content-type", "").lower():
            continue
        pages.append(path)
        for groups in _HREF.findall(r.text)[:20]:
            href = _first(groups)
            clean = href.split("?")[0].split("#")[0]
            if clean and clean not in seen and clean not in to_visit:
                to_visit.append(clean)
    return pages


def _discover_forms(client: httpx.Client, pages: list[str]) -> list[tuple[str, str, list[str]]]:
    forms: list[tuple[str, str, list[str]]] = []
    for path in pages:
        try:
            html = client.get(path).text
        except httpx.HTTPError:
            continue
        for block in _FORM.finditer(html):
            inner = block.group(1)
            whole = block.group(0)
            action_m = _ACTION.search(whole)
            action = _first(action_m.groups()) if action_m else path
            action = action.split("?")[0] or path
            method_m = _METHOD.search(whole)
            method = (_first(method_m.groups()).lower() if method_m else "post")
            fields = [_first(g if isinstance(g, tuple) else (g,))
                      for g in _INPUT.findall(inner)]
            fields = [f for f in fields if f and f.lower() not in
                      ("password", "csrf", "csrf_token", "_token")]
            if fields:
                forms.append((action, method, fields))
        if len(forms) >= 10:
            break
    return forms


def _norm(path: str) -> str:
    return "/" + path.strip("/").split("?")[0]


def _is_unescaped(body: str, marker: str) -> bool:
    """True only if the marker's <b> survived as raw HTML. If the app escaped it to &lt;b&gt;,
    this is False and nothing is flagged — that's the precision guard against safe fields."""
    return f"{marker}<b>" in (body or "") and f"{marker}&lt;b&gt;" not in (body or "")
