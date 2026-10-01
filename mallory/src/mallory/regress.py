"""Compile confirmed findings into EXECUTABLE regression tests.

Each finding carries a machine-readable ``repro`` spec (see the hostile checks). This module
turns that spec into a standalone pytest file that re-runs the same reproduction against the
app and asserts the bug is gone:

    fix the bug  ->  the test PASSES
    reintroduce it ->  the test FAILS, on the PR that broke it

The generated tests need only ``httpx`` and ``pytest`` (plus ``playwright`` for the few that
exercise client-rendered pages). No Mallory install, no API key, no LLM. Credentials are never
embedded; seeded-account logins come from environment variables (see regress_support.py).

A test asserts the *absence of the bug*, not that the feature still works: if a fix removes the
endpoint entirely the test passes. Tests that cannot exercise their reproduction (for example a
form that vanished from the page) fail loudly rather than passing vacuously.
"""
from __future__ import annotations

import hashlib
from pathlib import Path

from .findings import Finding

TRUE_PROBE = "x' OR '1'='1"
FALSE_PROBE = "x' AND '1'='2"

HEADER = '''"""Mallory regression test. Generated; safe to commit.

Finding : __TITLE__
Kind    : __KIND__   Severity: __SEV__   Fingerprint: __FP__

PASSES when the bug is fixed. FAILS if it is (re)introduced.
Run     : MALLORY_BASE_URL=http://localhost:3000 pytest __FILE__
          (add MALLORY_USER1_EMAIL / MALLORY_USER1_PASSWORD for tests that log in)
"""
import pytest  # noqa: F401

import _mallory_support as S  # noqa: F401


'''


def _r(v) -> str:
    return repr(v)


# Each renderer returns the test function source, using __TOKENS__ replaced with repr()'d values.

def _t_header(p, fp):
    return f'''def test_{fp}():
    with S.client() as c:
        r = c.get({_r(p["path"])})
    assert {_r(p["header"].lower())} in {{k.lower() for k in r.headers}}, (
        "REGRESSION: response is missing the {p["header"]} header")
'''


def _t_missing_auth(p, fp):
    return f'''def test_{fp}():
    with S.client() as c:  # deliberately NOT logged in
        r = c.get({_r(p["path"])})
    assert not S.looks_like_data(r), (
        "REGRESSION: {p["path"]} serves data to a request with no session")
'''


def _t_idor(p, fp):
    return f'''def test_{fp}():
    with S.client() as c:
        S.login(c, 1)
        own = S.own_id(c)
        if own is None:
            pytest.skip("could not determine the logged-in user's own id (needs /api/me)")
        r = c.get({_r(p["path"])})
    if not S.looks_like_data(r):
        return  # the endpoint no longer hands this object to this user: fixed
    owner = S.owner_of(r)
    assert not (owner and owner != own), (
        f"REGRESSION: {p["path"]} returned an object owned by user {{owner}} to user {{own}}")
'''


def _t_same_data(p, fp):
    return f'''def test_{fp}():
    with S.client() as a, S.client() as b:
        S.login(a, 1)
        S.login(b, 2)
        ra, rb = a.get({_r(p["path"])}), b.get({_r(p["path"])})
    same = (S.looks_like_data(ra) and S.looks_like_data(rb)
            and ra.text == rb.text and len(ra.content) > 20)
    assert not same, "REGRESSION: {p["path"]} returns identical data to two different users"
'''


def _t_reflected(p, fp):
    if p.get("rendered"):
        return f'''def test_{fp}():
    marker = S.new_marker()
    with S.browser_page() as page:
        html = S.rendered_html(page, {_r(p["path"])}, {{{_r(p["param"])}: S.probe(marker)}})
    assert not S.is_unescaped(html, marker), (
        "REGRESSION: {p["path"]} renders the {p["param"]} value as raw HTML in the DOM")
'''
    return f'''def test_{fp}():
    marker = S.new_marker()
    with S.client() as c:
        r = c.get({_r(p["path"])}, params={{{_r(p["param"])}: S.probe(marker)}})
    assert not S.is_unescaped(r.text, marker), (
        "REGRESSION: {p["path"]} reflects the {p["param"]} value as raw HTML")
'''


def _t_sqli_login(p, fp):
    return f'''def test_{fp}():
    with S.client(follow=False) as c:
        r = S.login_attempt(c, {_r(p["path"])}, {_r(p["probe"])}, "x", {_r(p["shape"])})
    assert r is None or S.login_rejected(r), (
        "REGRESSION: an injection probe in the login form authenticates at {p["path"]}")
'''


def _t_sqli_get(p, fp):
    if p.get("mode") == "boolean":
        return f'''def test_{fp}():
    with S.client() as c:
        t = c.get({_r(p["path"])}, params={{{_r(p["param"])}: {_r(TRUE_PROBE)}}})
        f = c.get({_r(p["path"])}, params={{{_r(p["param"])}: {_r(FALSE_PROBE)}}})
    diverge = (t.status_code == f.status_code
               and S.strip_reflected(t.text, {_r(TRUE_PROBE)}) != S.strip_reflected(f.text, {_r(FALSE_PROBE)}))
    assert not diverge, "REGRESSION: true/false SQL probes in {p["param"]} change the response"
'''
    return f'''def test_{fp}():
    with S.client() as c:
        benign = c.get({_r(p["path"])}, params={{{_r(p["param"])}: "mallory"}})
        quoted = c.get({_r(p["path"])}, params={{{_r(p["param"])}: "mallory'"}})
    broke = S.db_error(quoted.text) or (benign.status_code < 500 <= quoted.status_code)
    assert not broke, "REGRESSION: a quote in {p["param"]} reaches the SQL parser"
'''


def _t_stored_xss(p, fp):
    fields = p.get("fields") or []
    if not fields:
        return None  # we did not record how to submit; cannot build a meaningful test
    login = 1 if p.get("login") else None
    if p.get("rendered"):
        return f'''def test_{fp}():
    marker = S.new_marker()
    with S.browser_page(login_user={_r(login)}) as page:
        S.rendered_html(page, {_r(p.get("form_page", p["page"]))})
        S.submit_form(page, {_r(fields)}, S.probe(marker))
        html = S.rendered_html(page, {_r(p["page"])})
    assert not S.is_unescaped(html, marker), (
        "REGRESSION: stored input is rendered as raw HTML at {p["page"]}")
'''
    submit = (f'c.post({_r(p["action"])}, data=payload)' if p.get("method", "post") == "post"
              else f'c.get({_r(p["action"])}, params=payload)')
    login_line = "        S.login(c, 1)\n" if login else ""
    return f'''def test_{fp}():
    marker = S.new_marker()
    payload = {{name: S.probe(marker) for name in {_r(fields)}}}
    with S.client() as c:
{login_line}        sub = {submit}
        if sub.status_code in (404, 405) or sub.status_code >= 500:
            pytest.fail(f"could not exercise the reproduction: {{sub.status_code}} from the form "
                        "endpoint. If it was removed on purpose, delete this test.")
        body = c.get({_r(p["page"])}).text
    assert not S.is_unescaped(body, marker), (
        "REGRESSION: stored input is rendered as raw HTML at {p["page"]}")
'''


RENDERERS = {
    "header": _t_header,
    "missing_auth": _t_missing_auth,
    "idor": _t_idor,
    "same_data": _t_same_data,
    "reflected": _t_reflected,
    "sqli_login": _t_sqli_login,
    "sqli_get": _t_sqli_get,
    "stored_xss": _t_stored_xss,
}


def render_test(f: Finding) -> str | None:
    """Source for one finding's regression test, or None if it has no automatable reproduction."""
    fn = RENDERERS.get((f.repro or {}).get("type", ""))
    if fn is None:
        return None
    body = fn(f.repro, f.fingerprint)
    if body is None:
        return None
    head = (HEADER.replace("__TITLE__", f.title.replace('"""', "'''"))
            .replace("__KIND__", f.kind.value).replace("__SEV__", f.severity.value)
            .replace("__FP__", f.fingerprint).replace("__FILE__", f"test_{f.fingerprint}.py"))
    return head + body


def write_tests(confirmed: list[Finding], test_dir: Path, outcomes=()) -> tuple[list[Path], list[Finding]]:
    """Write one test per automatable finding plus the shared support module.

    Returns (written test paths, findings that could not be automated)."""
    test_dir.mkdir(parents=True, exist_ok=True)
    (test_dir / "_mallory_support.py").write_text(
        (Path(__file__).parent / "regress_support.py").read_text())
    (test_dir / "_mallory_outcomes.py").write_text(
        (Path(__file__).parent / "outcomes.py").read_text())
    (test_dir / "conftest.py").write_text('import sys, pathlib\nsys.path.insert(0, str(pathlib.Path(__file__).parent))\n')
    written: list[Path] = []
    manual: list[Finding] = []
    for f in confirmed:
        src = render_test(f)
        if src is None:
            manual.append(f)
            continue
        path = test_dir / f"test_{f.fingerprint}.py"
        path.write_text(src)
        written.append(path)
    for outcome in outcomes:
        fp = hashlib.sha256(outcome.name.encode()).hexdigest()[:12]
        credentials = f"S.creds({outcome.user})" if outcome.user is not None else "None"
        src = f'''"""Mallory user outcome: {outcome.name}. Requires seeded disposable data."""
import pytest
import _mallory_support as S
from _mallory_outcomes import check_outcome, OutcomeUnavailable


def test_outcome_{fp}():
    try:
        credentials = {credentials}
        check_outcome(S.base_url(), {outcome.model_dump()!r}, credentials)
    except (pytest.skip.Exception, OutcomeUnavailable):
        pytest.fail("could not exercise the configured user outcome; check target and seeded login")
'''
        path = test_dir / f"test_outcome_{fp}.py"
        path.write_text(src)
        written.append(path)
    return written, manual
