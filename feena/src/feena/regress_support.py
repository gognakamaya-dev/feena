"""Runtime helpers for generated Feena regression tests.

This file is copied next to the generated tests as ``_feena_support.py``. The tests depend on
``httpx`` and ``pytest`` only (``playwright`` too for the few browser-rendered ones), NOT on
Feena itself, so a team can commit them to their own repo and run them in their own CI.

Safety defaults, because these tests send attack-shaped (but inert) probes at whatever
``FEENA_BASE_URL`` points to:
- They refuse to run against anything but a local/private address unless you explicitly set
  ``FEENA_ALLOW_REMOTE=1``. Only ever do that for an environment you own or are authorised to
  test.
- Credentials are never written into the tests. Seeded test-account logins come from
  ``FEENA_USER1_EMAIL`` / ``FEENA_USER1_PASSWORD`` (and ``..USER2..``).
"""
from __future__ import annotations

import ipaddress
import os
import re
import secrets
from contextlib import contextmanager
from urllib.parse import urlencode, urlsplit

import httpx
import pytest

OWNER_FIELDS = ("owner_id", "user_id", "owner", "user", "account_id", "created_by")

DB_ERRORS = re.compile(
    r"(SQL syntax|SQLITE_ERROR|sqlite3\.OperationalError|unrecognized token|SQL logic error"
    r"|near \".*?\": syntax error|You have an error in your SQL|MySQL|PSQLException|PostgreSQL"
    r"|syntax error at or near|Unclosed quotation mark|Microsoft SQL Server|ORA-\d{5}"
    r"|OperationalError|ProgrammingError|column .* does not exist)",
    re.IGNORECASE,
)


# ---------- target + safety ----------

def _is_local(host: str) -> bool:
    if host in ("localhost",) or host.endswith(".localhost"):
        return True
    try:
        ip = ipaddress.ip_address(host)
        return ip.is_loopback or ip.is_private
    except ValueError:
        return "." not in host   # single-label names, e.g. a docker-compose service "web"


def base_url() -> str:
    url = os.environ.get("FEENA_BASE_URL", "").rstrip("/")
    if not url:
        pytest.skip("set FEENA_BASE_URL to the app under test (a local/sandbox copy)")
    host = urlsplit(url).hostname or ""
    if not _is_local(host) and os.environ.get("FEENA_ALLOW_REMOTE") != "1":
        pytest.skip(
            f"{host} is not a local/private address. These tests send injection-style probes; "
            "set FEENA_ALLOW_REMOTE=1 only for an environment you own or are authorised to test."
        )
    return url


def client(follow: bool = True) -> httpx.Client:
    return httpx.Client(base_url=base_url(), timeout=10.0, follow_redirects=follow)


# ---------- auth ----------

def creds(n: int) -> tuple[str, str]:
    email = os.environ.get(f"FEENA_USER{n}_EMAIL")
    pw = os.environ.get(f"FEENA_USER{n}_PASSWORD")
    if not (email and pw):
        pytest.skip(f"set FEENA_USER{n}_EMAIL and FEENA_USER{n}_PASSWORD (a seeded test account)")
    return email, pw


def login(c: httpx.Client, n: int = 1) -> bool:
    email, pw = creds(n)
    for path in ("/api/login", "/login", "/api/auth/login"):
        for kw in ({"json": {"email": email, "password": pw}},
                   {"data": {"email": email, "password": pw}}):
            try:
                r = c.post(path, **kw)
            except httpx.HTTPError:
                continue
            if r.status_code < 400 and len(c.cookies) > 0:
                return True
    pytest.skip(f"could not log in as seeded user {n}; check the credentials and the login route")


# ---------- response inspection ----------

def looks_like_data(r: httpx.Response) -> bool:
    if r.status_code != 200 or "json" not in r.headers.get("content-type", "").lower():
        return False
    return (r.text or "").strip() not in ("", "[]", "{}", "null")


def _json(r: httpx.Response):
    try:
        return r.json()
    except Exception:
        return None


def owner_of(r: httpx.Response) -> str | None:
    obj = _json(r)
    if isinstance(obj, dict):
        for k in OWNER_FIELDS:
            if k in obj:
                return str(obj[k])
    return None


def own_id(c: httpx.Client) -> str | None:
    for path in ("/api/me", "/api/profile", "/api/account"):
        try:
            r = c.get(path)
        except httpx.HTTPError:
            continue
        obj = _json(r) if looks_like_data(r) else None
        if isinstance(obj, dict):
            for k in ("id", "user_id", "uid"):
                if k in obj:
                    return str(obj[k])
    return None


# ---------- XSS probes ----------

def new_marker() -> str:
    return "MALX" + secrets.token_hex(4)


def probe(marker: str) -> str:
    """Inert probe: a unique token plus a harmless <b> tag. Nothing executes."""
    return f"{marker}<b>x</b>"


def is_unescaped(html: str, marker: str) -> bool:
    """True only if the <b> survived as raw HTML. Escaped (&lt;b&gt;) means the bug is fixed."""
    return f"{marker}<b>" in (html or "") and f"{marker}&lt;b&gt;" not in (html or "")


# ---------- SQLi helpers ----------

def db_error(text: str) -> bool:
    return bool(DB_ERRORS.search(text or ""))


def strip_reflected(text: str, payload: str) -> str:
    out = text or ""
    for form in (payload, payload.replace("'", "&#39;"), payload.replace("'", "&#x27;")):
        out = out.replace(form, "")
    return out


def login_attempt(c: httpx.Client, path: str, email: str, pw: str, shape: str):
    try:
        r = c.post(path, data={"email": email, "password": pw}) if shape == "form" \
            else c.post(path, json={"email": email, "password": pw})
    except httpx.HTTPError:
        return None
    return None if r.status_code in (404, 405) else r


def login_rejected(r: httpx.Response) -> bool:
    body = (r.text or "").lower()
    set_cookie = "set-cookie" in {k.lower() for k in r.headers.keys()}
    explicit_fail = (r.status_code == 401 or "bad login" in body
                     or '"ok": false' in body or '"ok":false' in body)
    accepted = (r.status_code in (301, 302, 303) or set_cookie) and not explicit_fail
    return not accepted


# ---------- browser (for client-rendered apps) ----------

@contextmanager
def browser_page(login_user: int | None = None):
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        pytest.skip("browser test: pip install playwright && playwright install chromium")
    url = base_url()
    with sync_playwright() as p:
        try:
            browser = p.chromium.launch(headless=True)
        except Exception:
            pytest.skip("browser test: run `playwright install chromium`")
        try:
            ctx = browser.new_context()
            if login_user:
                with client() as c:
                    login(c, login_user)
                    ctx.add_cookies([{"name": k.name, "value": k.value, "url": url}
                                     for k in c.cookies.jar])
            yield ctx.new_page()
        finally:
            browser.close()


def rendered_html(page, path: str, params: dict | None = None) -> str:
    target = base_url() + (path if path.startswith("/") else "/" + path)
    if params:
        target += ("&" if "?" in target else "?") + urlencode(params)
    page.goto(target, wait_until="domcontentloaded", timeout=15000)
    try:
        page.wait_for_load_state("networkidle", timeout=800)
    except Exception:
        page.wait_for_timeout(800)
    return page.content()


def submit_form(page, fields: list[str], value: str) -> None:
    """Fill each field and submit by real interaction. Fails loudly if the form isn't there,
    so a changed page can never turn this into a silent, vacuous pass."""
    for name in fields:
        sel = f'[name="{name}"]'
        if not page.query_selector(sel):
            pytest.fail(f"could not exercise the reproduction: field {name!r} not found on the "
                        "page. If the form was removed on purpose, delete this test; otherwise "
                        "the page changed and this test should be regenerated.")
        page.fill(sel, value)
    btn = page.query_selector('button[type="submit"], input[type="submit"], form button')
    if btn:
        btn.click()
    else:
        page.keyboard.press("Enter")
    try:
        page.wait_for_load_state("networkidle", timeout=800)
    except Exception:
        page.wait_for_timeout(800)
