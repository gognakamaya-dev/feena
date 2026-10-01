"""Detect SQL injection by observation. Detection only — never exploitation.

This check answers one question: is a given input interpreted as SQL rather than data? It uses
the two standard non-destructive detection signals and stops there:

1. Error-based: a single SQL metacharacter provokes a database error signature (or flips a
   working 200 into a 500 that a second benign value does not), which means the input reached
   the query unsanitised.
2. Boolean / auth differential: a logically-true probe and a logically-false probe produce
   responses that differ in a way that tracks SQL logic. On a login form, an auth-bypass probe
   flips the outcome from "rejected" to "accepted".

It never extracts data, enumerates schema, UNION-dumps, or stacks destructive statements. All
requests are ordinary reads/auth attempts against the sandboxed copy; nothing is modified. Like
the reflection check, it reports "this parameter is injectable, here is the differential that
proves it" — enough to flag and to generate a regression test, not an attack.

Runs only under the hostile agent, which runs only inside a Mallory-built no-egress sandbox.
"""
from __future__ import annotations

import re

import httpx

from ...config import Config
from ...findings import Finding, Kind, Severity, Step
from ...sandbox import Sandbox

# Database error signatures across common engines. Matching one means input hit the parser.
DB_ERRORS = re.compile(
    r"(SQL syntax|SQLITE_ERROR|sqlite3\.OperationalError|unrecognized token|SQL logic error"
    r"|near \".*?\": syntax error|You have an error in your SQL|MySQL|PSQLException|PostgreSQL"
    r"|syntax error at or near|Unclosed quotation mark|Microsoft SQL Server|ORA-\d{5}"
    r"|OperationalError|ProgrammingError|column .* does not exist)",
    re.IGNORECASE,
)

# Detection probes only. A lone quote to trip the parser; a true/false pair to show SQL logic.
QUOTE = "'"
TRUE_PROBE = "x' OR '1'='1"
FALSE_PROBE = "x' AND '1'='2"

# Standard auth-bypass probes. Apps quote inputs differently (string vs numeric context, comment
# style), so a robust detector tries a small battery and flags if ANY flips reject -> accept.
# These are detection probes, not an exploit kit: they prove the login builds SQL from raw input.
BYPASS_PROBES = [
    "' OR 1=1 -- ",
    "' OR '1'='1' -- ",
    "' OR '1'='1",
    "admin' -- ",
    "') OR ('1'='1' -- ",
]

# Login endpoints to test for auth-bypass-by-injection (form and JSON shapes).
LOGIN_PATHS = ["/login", "/api/login", "/api/auth/login", "/signin"]
# GET endpoints with a query parameter worth probing (extended by discovery in future).
GET_SURFACES = [("/search", "q")]


def _err(text: str) -> bool:
    return bool(DB_ERRORS.search(text or ""))


def _strip(text: str, payload: str) -> str:
    """Remove the reflected payload (and a couple of HTML-escaped forms) so a difference that
    remains is genuine SQL-logic signal, not the echo of two different input strings."""
    out = text or ""
    for form in (payload, payload.replace("'", "&#39;"), payload.replace("'", "&#x27;")):
        out = out.replace(form, "")
    return out


def run(cfg: Config, sandbox: Sandbox) -> list[Finding]:
    findings: list[Finding] = []
    base = sandbox.base_url.rstrip("/")

    findings.extend(_check_get_params(base))
    findings.extend(_check_login_bypass(base))
    return findings


def _check_get_params(base: str) -> list[Finding]:
    """Error-based and boolean-based detection on GET query parameters."""
    out: list[Finding] = []
    with httpx.Client(base_url=base, timeout=8.0, follow_redirects=True) as c:
        for path, param in GET_SURFACES:
            try:
                benign = c.get(path, params={param: "mallory"})
                quoted = c.get(path, params={param: "mallory" + QUOTE})
            except httpx.HTTPError:
                continue

            # Error-based: an error signature appears, or the quote alone breaks a working page.
            error_based = _err(quoted.text) or (
                benign.status_code < 500 <= quoted.status_code
            )
            if error_based:
                out.append(_finding(
                    f"SQL injection (error-based) in `{param}` at {path}",
                    (f"A single quote in `{param}` produced a database error or a server error "
                     "that a benign value did not, so the input reaches the SQL query "
                     "unsanitised. Detection only; no data was extracted."),
                    Step(action="http_get", target=f"{path}?{param}=<quote>",
                         note="quote triggers DB error / 500"),
                    base + path,
                    repro={"type": "sqli_get", "mode": "error", "path": path, "param": param},
                ))
                continue  # already proven for this surface

            # Boolean-based: true vs false probe diverge in a way consistent with SQL logic.
            # An endpoint that merely reflects input will differ just because the probe strings
            # differ, so strip the reflected payloads before comparing. A remaining difference is
            # not explained by reflection and points at the injected SQL condition.
            try:
                t = c.get(path, params={param: TRUE_PROBE})
                f = c.get(path, params={param: FALSE_PROBE})
            except httpx.HTTPError:
                continue
            t_norm = _strip(t.text, TRUE_PROBE)
            f_norm = _strip(f.text, FALSE_PROBE)
            if t.status_code == f.status_code and t_norm != f_norm and abs(len(t_norm) - len(f_norm)) > 0:
                out.append(_finding(
                    f"SQL injection (boolean-based) in `{param}` at {path}",
                    (f"Logically-true and logically-false SQL probes in `{param}` returned "
                     "different responses, which tracks the injected condition. Detection only."),
                    Step(action="http_get", target=f"{path}?{param}=<boolean probe>",
                         note="true/false probes diverge"),
                    base + path,
                    repro={"type": "sqli_get", "mode": "boolean", "path": path, "param": param},
                ))
    return out


def _check_login_bypass(base: str) -> list[Finding]:
    """Auth-bypass detection: does an injection probe flip a rejected login into an accepted one?

    Non-destructive: these are authentication attempts (reads), not writes. We compare a known
    bad credential against an injection probe and look for the outcome flipping to success.
    """
    out: list[Finding] = []
    for path in LOGIN_PATHS:
        proven = False
        for shape in ("form", "json"):
            with httpx.Client(base_url=base, timeout=8.0, follow_redirects=False) as c:
                bad = _attempt(c, path, "nouser@example.com", "wrongpass", shape)
            if bad is None:
                break  # endpoint/shape not present; try next path
            if not _rejected(bad):
                continue  # can't tell accept from reject here; this shape is uninformative
            for probe in BYPASS_PROBES:
                with httpx.Client(base_url=base, timeout=8.0, follow_redirects=False) as c:
                    inj = _attempt(c, path, probe, "x", shape)
                if inj is None:
                    continue
                if not _rejected(inj):  # a rejected login flipped to accepted
                    out.append(_finding(
                        f"SQL injection auth bypass at {path}",
                        ("An injection probe in the login field turned a rejected login into an "
                         "accepted one, so the credential check builds its SQL from raw input. "
                         "Detection only; no account was altered."),
                        Step(action="login", target=path, note="injection flips reject -> accept"),
                        base + path,
                        severity=Severity.CRITICAL,
                        repro={"type": "sqli_login", "path": path, "shape": shape, "probe": probe},
                    ))
                    proven = True
                    break
            if proven:
                break
    return out


def _attempt(c: httpx.Client, path: str, email: str, pw: str, shape: str):
    """Return the response of a login attempt, or None if the endpoint/shape isn't there."""
    try:
        if shape == "form":
            r = c.post(path, data={"email": email, "password": pw})
        else:
            r = c.post(path, json={"email": email, "password": pw})
    except httpx.HTTPError:
        return None
    # A 404/405 means this path/shape isn't a real login here.
    if r.status_code in (404, 405):
        return None
    return r


def _rejected(r: httpx.Response) -> bool:
    """Heuristic: was this login rejected? (no session set, or an explicit failure)."""
    set_cookie = "set-cookie" in {k.lower() for k in r.headers.keys()}
    body = (r.text or "").lower()
    explicit_fail = r.status_code == 401 or "bad login" in body or '"ok": false' in body or '"ok":false' in body
    # Accepted usually means a redirect and/or a session cookie and no failure marker.
    accepted_signal = (r.status_code in (301, 302, 303) or set_cookie) and not explicit_fail
    return not accepted_signal


def _finding(title: str, detail: str, step: Step, url: str, severity=Severity.HIGH,
             repro: dict | None = None) -> Finding:
    return Finding(
        kind=Kind.SQL_INJECTION, severity=severity, title=title, detail=detail,
        agent="hostile", steps=[step], evidence={"url": url}, repro=repro or {},
    )
