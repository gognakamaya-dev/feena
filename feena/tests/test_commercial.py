"""Tests for the commercial layer: attestations, corpus, plugin seam."""
from __future__ import annotations

import json
from pathlib import Path

from feena.attest import build_record, generate_keypair, render_compliance_md, sign, verify
from feena.corpus import record, route_shape, summarize, to_record
from feena.findings import Finding, Kind, Severity, Step


def _f(kind=Kind.ACCESS_CONTROL, sev=Severity.CRITICAL, title="Possible IDOR at /api/orders/42",
       target="/api/orders/42?token=secret"):
    f = Finding(kind=kind, severity=sev, title=title, detail="d", agent="hostile",
                steps=[Step(action="http_get", target=target)],
                evidence={"url": "http://internal.acme.corp/api/orders/42", "context": "PII"})
    f.confirmed = True
    return f


# ---- attestations ----

def test_attestation_roundtrip_and_tamper(tmp_path: Path):
    priv, pub = generate_keypair(tmp_path)
    att = sign(build_record([_f()], ["hostile"], 2), priv)
    assert verify(att, pub)

    tampered = json.loads(json.dumps(att))
    tampered["record"]["summary"]["critical"] = 0          # hide the critical bug
    assert not verify(tampered, pub)


def test_attestation_rejects_other_key(tmp_path: Path):
    priv, _ = generate_keypair(tmp_path / "a")
    _, other_pub = generate_keypair(tmp_path / "b")
    assert not verify(sign(build_record([], ["hostile"], 0), priv), other_pub)


def test_record_maps_owasp_and_excludes_evidence(tmp_path: Path):
    rec = build_record([_f()], ["hostile"], 0)
    assert rec["findings"][0]["owasp"].startswith("A01")
    assert "internal.acme.corp" not in json.dumps(rec)
    md = render_compliance_md(sign(rec, generate_keypair(tmp_path)[0]))
    assert "not a certification" in md


# ---- corpus ----

def test_route_shape_generalises():
    assert route_shape("/api/orders/42?q=x") == "/api/orders/:id"
    assert route_shape("http://h:3000/u/3f2b8c1e-1111-2222-3333-444455556666/x") == "/u/:id/x"


def test_corpus_record_strips_identifying_data():
    blob = json.dumps(to_record(_f(), "nextjs-postgres").__dict__)
    for leak in ("internal.acme.corp", "token=secret", "42", "PII"):
        assert leak not in blob


def test_same_bug_on_different_ids_shares_a_pattern():
    a = to_record(_f(target="/api/orders/1", title="Possible IDOR at /api/orders/1"), "s")
    b = to_record(_f(target="/api/orders/999", title="Possible IDOR at /api/orders/999"), "s")
    assert a.pattern == b.pattern


def test_unconfirmed_findings_never_enter_corpus(tmp_path: Path):
    f = _f()
    f.confirmed = False
    path = record([f, _f()], "s", tmp_path)
    assert len(path.read_text().splitlines()) == 1
    assert summarize(path)[0][2] == 1


# ---- plugin seam ----

def test_plugin_loader_survives_no_plugins():
    from feena.plugins import load_plugin_checks
    assert isinstance(load_plugin_checks(), list)


# ---- sqli detection ----

def test_sqli_error_signature_matches():
    from feena.agents.checks.sqli import _err
    assert _err("near \"'\": syntax error")
    assert _err("sqlite3.OperationalError: unrecognized token")
    assert not _err("Results for: hello")  # benign page must not match


def test_sqli_rejected_vs_accepted_heuristic():
    import httpx
    from feena.agents.checks.sqli import _rejected
    rejected = httpx.Response(200, text="bad login")
    accepted = httpx.Response(302, headers={"set-cookie": "session=abc"})
    ok_false = httpx.Response(401, json={"ok": False})
    assert _rejected(rejected)
    assert not _rejected(accepted)
    assert _rejected(ok_false)


def test_sqli_strip_collapses_reflected_probes():
    # Regression guard: a pure-reflection endpoint must not read as boolean-based SQLi.
    # Two different probes, once their echo is stripped, are identical -> no signal.
    from feena.agents.checks.sqli import _strip, TRUE_PROBE, FALSE_PROBE
    t = _strip(f"<p>Results for: {TRUE_PROBE}</p>", TRUE_PROBE)
    f = _strip(f"<p>Results for: {FALSE_PROBE}</p>", FALSE_PROBE)
    assert t == f == "<p>Results for: </p>"


# ---- stored xss detection ----

def test_stored_xss_flags_unescaped_but_not_escaped():
    from feena.agents.checks.stored_xss import _is_unescaped
    m = "MALXdeadbeef"
    assert _is_unescaped(f"<li>{m}<b>x</b></li>", m)            # raw tag survived -> vulnerable
    assert not _is_unescaped(f"<li>{m}&lt;b&gt;x&lt;/b&gt;</li>", m)  # escaped -> safe, no flag
    assert not _is_unescaped("<li>no marker here</li>", m)      # absent -> no flag


def test_stored_xss_parses_unquoted_html_attributes():
    from feena.agents.checks.stored_xss import _FORM, _ACTION, _INPUT, _first
    html = '<form method=post action=/tasks/new><input name=title placeholder="new task"></form>'
    inner = _FORM.search(html)
    assert inner
    assert _first(_ACTION.search(html).groups()) == "/tasks/new"
    fields = [_first(g) for g in _INPUT.findall(inner.group(1))]
    assert "title" in fields


# ---- benchmark harness ----

def test_bench_report_aggregates_and_lists_failures():
    from feena.bench import AppResult, render_bench_md
    from feena.findings import Finding, Kind, Severity
    good = AppResult("app-a", "ok", findings=[
        Finding(kind=Kind.SQL_INJECTION, severity=Severity.CRITICAL, title="SQLi at /login",
                detail="d", agent="hostile"),
    ], duration_s=3)
    empty = AppResult("app-b", "ok", findings=[], duration_s=1)
    broken = AppResult("app-c", "error", detail="no Docker", duration_s=0)
    md = render_bench_md([good, empty, broken])
    assert "1 confirmed finding(s) across 1 app(s)" in md
    assert "SQLi at /login" in md
    assert "Could not be brought up" in md and "no Docker" in md


def test_bench_runs_process_target_end_to_end():
    import os
    from feena.bench import Target, run_target
    if os.path.exists("/tmp/taskflow.db"):
        os.remove("/tmp/taskflow.db")
    t = Target(name="taskflow", kind="process", module="examples/taskflow/app.py:app",
               port=0, healthcheck="/api/health",
               users=[{"label": "alice", "email": "alice@example.com", "password": "password123"},
                      {"label": "bob", "email": "bob@example.com", "password": "password123"}])
    r = run_target(t)
    assert r.status == "ok"
    kinds = {f.kind.value for f in r.findings}
    # the harness should surface the serious access-control + injection classes
    assert "access_control" in kinds and "sql_injection" in kinds and "stored_xss" in kinds


# ---- rendered-DOM (browser) path ----

def test_input_reflection_falls_back_to_httpx_without_renderer():
    # With renderer=None the check must use httpx and still work on server-rendered reflection.
    import threading, wsgiref.simple_server, time
    from flask import Flask, request
    from feena.agents.checks import input_reflection
    from feena.config import Config, TargetConfig
    from feena.sandbox import Sandbox
    app = Flask(__name__)
    @app.get("/search")
    def s():
        return f"<html><body>Results for: {request.args.get('q','')}</body></html>"
    @app.get("/")
    def h():
        return "<html>hi</html>"
    class Q(wsgiref.simple_server.WSGIRequestHandler):
        def log_message(self, *a): pass
    srv = wsgiref.simple_server.make_server("127.0.0.1", 0, app, handler_class=Q)
    threading.Thread(target=srv.serve_forever, daemon=True).start(); time.sleep(0.2)
    base = f"http://127.0.0.1:{srv.server_address[1]}"
    try:
        found = input_reflection.run(Config(target=TargetConfig(compose="x", service="w", port=1)),
                                     Sandbox(base_url=base), None)
        assert any("/search" in f.title for f in found)
    finally:
        srv.shutdown()


def test_renderer_catches_spa_xss_that_httpx_misses():
    import threading, wsgiref.simple_server, time, importlib.util
    from pathlib import Path
    import pytest
    from feena.render import Renderer, browser_available
    from feena.agents.checks import input_reflection, stored_xss
    from feena.config import Config, TargetConfig
    from feena.sandbox import Sandbox
    if not browser_available():
        pytest.skip("no browser available")
    spec = importlib.util.spec_from_file_location("spa_t", Path("examples/spa-notes/app.py").resolve())
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
    class Q(wsgiref.simple_server.WSGIRequestHandler):
        def log_message(self, *a): pass
    srv = wsgiref.simple_server.make_server("127.0.0.1", 0, m.app, handler_class=Q)
    threading.Thread(target=srv.serve_forever, daemon=True).start(); time.sleep(0.2)
    base = f"http://127.0.0.1:{srv.server_address[1]}"
    cfg = Config(target=TargetConfig(compose="x", service="w", port=1))
    sb = Sandbox(base_url=base)
    try:
        httpx_only = input_reflection.run(cfg, sb, None) + stored_xss.run(cfg, sb, None)
        assert httpx_only == []                      # SPA is invisible to raw HTTP
        r = Renderer(base).start()
        try:
            rendered = input_reflection.run(cfg, sb, r) + stored_xss.run(cfg, sb, r)
        finally:
            r.close()
        kinds = {f.kind.value for f in rendered}
        assert "input_handling" in kinds and "stored_xss" in kinds
    finally:
        srv.shutdown()
