"""Broken access control checks, by observation only.

Three non-destructive checks, all confirm-by-observation, never by writing or deleting:

1. Missing auth: request likely data endpoints with no session. A 200 with data is a finding.
   Endpoints come from a content-discovery wordlist plus anything linked from the app.

2. Object-level IDOR: for endpoints shaped like /api/<resource>/<id>, log in as the attacker
   and fetch objects; if a returned object's owner/user id is not the attacker's own id, the
   endpoint is not scoping to the caller. This catches the real /api/tasks/<id> shape that a
   fixed-path comparison misses.

3. Cross-account IDOR: two seeded accounts receive identical private data from the same
   collection endpoint (kept from the original check).

Everything is a GET. Nothing is modified.
"""
from __future__ import annotations

import re

import httpx

from ...config import Config
from ...findings import Finding, Kind, Severity, Step
from ...sandbox import Sandbox

# Content-discovery wordlist: common data collections a naive app forgets to protect.
COLLECTIONS = [
    "me", "account", "settings", "profile", "users", "orders", "projects", "tasks",
    "notes", "documents", "files", "invoices", "billing", "teams", "workspaces",
    "messages", "notifications", "admin", "config",
]
LIKELY_PROTECTED = [f"/api/{c}" for c in COLLECTIONS] + ["/dashboard", "/account", "/admin"]

# Resources we'll probe for object-level IDOR as /api/<res>/<id>.
OBJECT_RESOURCES = ["tasks", "projects", "orders", "notes", "documents", "invoices", "users"]
OWNER_FIELDS = ("owner_id", "user_id", "owner", "user", "account_id", "created_by")


def _looks_like_data(resp: httpx.Response) -> bool:
    if resp.status_code != 200:
        return False
    if "json" not in resp.headers.get("content-type", "").lower():
        return False
    # An empty collection/null is not "exposed data" — don't flag it (jsonify([]) sends "[]\n",
    # so strip before comparing). Avoids false positives on legitimately public, empty endpoints.
    return (resp.text or "").strip() not in ("", "[]", "{}", "null")


def _login(base: str, email: str, password: str) -> httpx.Client | None:
    client = httpx.Client(base_url=base, timeout=8.0, follow_redirects=True)
    for path in ("/api/login", "/login", "/api/auth/login"):
        try:
            r = client.post(path, json={"email": email, "password": password})
            if r.status_code < 400 and (client.cookies or "authorization" in r.headers):
                return client
        except httpx.HTTPError:
            continue
    client.close()
    return None


def _own_id(client: httpx.Client) -> str | None:
    """Best-effort: the logged-in user's own id, to compare against object owners."""
    for path in ("/api/me", "/api/profile", "/api/account"):
        try:
            r = client.get(path)
        except httpx.HTTPError:
            continue
        if _looks_like_data(r):
            data = r.json()
            for k in ("id", "user_id", "uid"):
                if k in data:
                    return str(data[k])
    return None


def _owner_of(obj: dict) -> str | None:
    for k in OWNER_FIELDS:
        if k in obj:
            return str(obj[k])
    return None


def run(cfg: Config, sandbox: Sandbox) -> list[Finding]:
    findings: list[Finding] = []
    base = sandbox.base_url.rstrip("/")

    # --- Check 1: missing auth (no session at all) ---
    with httpx.Client(base_url=base, timeout=8.0) as anon:
        for path in LIKELY_PROTECTED:
            try:
                r = anon.get(path)
            except httpx.HTTPError:
                continue
            if _looks_like_data(r):
                findings.append(Finding(
                    kind=Kind.MISSING_AUTH, severity=Severity.HIGH,
                    title=f"Protected-looking endpoint served without auth: {path}",
                    detail=(f"`{path}` returned data on a request with no session. If this is "
                            "user or account data, it is exposed to anyone."),
                    agent="hostile",
                    steps=[Step(action="http_get", target=path, note="no cookies / no session")],
                    evidence={"url": base + path, "status": r.status_code},
                    repro={"type": "missing_auth", "path": path},
                ))

    if len(cfg.users) < 2:
        return findings

    attacker, victim = cfg.users[0], cfg.users[1]
    a = _login(base, attacker.email, attacker.password)
    v = _login(base, victim.email, victim.password)
    try:
        # --- Check 2: object-level IDOR via owner mismatch ---
        if a:
            attacker_id = _own_id(a)
            for res in OBJECT_RESOURCES:
                for oid in range(1, 6):  # probe a few low ids, non-destructively
                    path = f"/api/{res}/{oid}"
                    try:
                        r = a.get(path)
                    except httpx.HTTPError:
                        continue
                    if not _looks_like_data(r):
                        continue
                    owner = _owner_of(r.json())
                    if owner and attacker_id and owner != attacker_id:
                        findings.append(Finding(
                            kind=Kind.ACCESS_CONTROL, severity=Severity.CRITICAL,
                            title=f"IDOR: {path} returns an object owned by another user",
                            detail=(f"Logged in as the attacker (id {attacker_id}), `{path}` "
                                    f"returned an object whose owner is {owner}. The endpoint "
                                    "does not scope objects to the caller."),
                            agent="hostile",
                            steps=[Step(action="login", target="attacker", note=attacker.label),
                                   Step(action="http_get", target=path,
                                        note=f"object owner {owner} != caller {attacker_id}")],
                            evidence={"url": base + path},
                            repro={"type": "idor", "path": path},
                        ))
                        break  # one instance per resource is enough to prove it

        # --- Check 3: cross-account identical data on a collection ---
        if a and v:
            for path in [f"/api/{c}" for c in ("orders", "me", "users", "tasks")]:
                try:
                    ra, rv = a.get(path), v.get(path)
                except httpx.HTTPError:
                    continue
                if _looks_like_data(ra) and _looks_like_data(rv) and ra.text == rv.text and len(ra.content) > 20:
                    findings.append(Finding(
                        kind=Kind.ACCESS_CONTROL, severity=Severity.HIGH,
                        title=f"Two accounts receive identical data at {path}",
                        detail=("Two different logged-in accounts got byte-identical responses "
                                "from the same endpoint, suggesting results are not scoped per user."),
                        agent="hostile",
                        steps=[Step(action="http_get", target=path, note="same bytes for two users")],
                        evidence={"url": base + path},
                        repro={"type": "same_data", "path": path},
                    ))
    finally:
        for c in (a, v):
            if c:
                c.close()

    return findings
