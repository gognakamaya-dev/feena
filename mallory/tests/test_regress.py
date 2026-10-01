"""Tests for the executable regression-test generator."""
from __future__ import annotations

import ast
import os
import subprocess
import sys
import threading
import time
import types
import wsgiref.simple_server
from pathlib import Path

import pytest

from mallory.findings import Finding, Kind, Severity, Step
from mallory.regress import render_test, write_tests


def _f(repro, kind=Kind.ACCESS_CONTROL, title="t"):
    f = Finding(kind=kind, severity=Severity.HIGH, title=title, detail="d", agent="hostile",
                steps=[Step(action="http_get", target="/x")], repro=repro)
    f.confirmed = True
    return f


SPECS = [
    {"type": "header", "path": "/", "header": "content-security-policy"},
    {"type": "missing_auth", "path": "/api/projects"},
    {"type": "idor", "path": "/api/tasks/2"},
    {"type": "same_data", "path": "/api/orders"},
    {"type": "reflected", "path": "/search", "param": "q", "rendered": False},
    {"type": "reflected", "path": "/", "param": "q", "rendered": True},
    {"type": "sqli_login", "path": "/login", "shape": "form", "probe": "' OR 1=1 -- "},
    {"type": "sqli_get", "mode": "error", "path": "/search", "param": "q"},
    {"type": "sqli_get", "mode": "boolean", "path": "/search", "param": "q"},
    {"type": "stored_xss", "rendered": False, "login": True, "page": "/tasks",
     "form_page": "/tasks", "action": "/tasks/new", "method": "post", "fields": ["title"]},
    {"type": "stored_xss", "rendered": True, "login": False, "page": "/",
     "form_page": "/", "action": "/", "method": "post", "fields": ["text"]},
]


@pytest.mark.parametrize("spec", SPECS, ids=lambda s: f"{s['type']}-{s.get('mode', s.get('rendered', ''))}")
def test_every_spec_renders_valid_python(spec):
    src = render_test(_f(spec))
    assert src is not None
    ast.parse(src)                                   # it compiles
    assert "NotImplementedError" not in src         # no more stubs
    assert "def test_" in src and "assert" in src   # it actually asserts something


def test_no_credentials_or_secrets_are_embedded():
    for spec in SPECS:
        src = render_test(_f(spec))
        assert "password123" not in src and "@example.com" not in src


def test_unautomatable_findings_are_reported_not_faked(tmp_path: Path):
    no_spec = _f({})
    unknown = _f({"type": "something_new"})
    no_fields = _f({"type": "stored_xss", "rendered": False, "page": "/", "fields": []})
    assert render_test(no_spec) is None and render_test(unknown) is None
    assert render_test(no_fields) is None            # would be a vacuous test; refuse to fake one
    written, manual = write_tests([no_spec, unknown, no_fields], tmp_path)
    assert written == [] and len(manual) == 3


def test_write_tests_emits_support_and_one_file_per_finding(tmp_path: Path):
    written, manual = write_tests([_f(SPECS[0]), _f(SPECS[1], title="other")], tmp_path)
    assert len(written) == 2 and manual == []
    assert (tmp_path / "_mallory_support.py").exists()
    assert (tmp_path / "conftest.py").exists()


def test_generated_tests_refuse_remote_targets_by_default(tmp_path: Path):
    write_tests([_f(SPECS[0])], tmp_path)
    env = {**os.environ, "MALLORY_BASE_URL": "https://example.com"}
    env.pop("MALLORY_ALLOW_REMOTE", None)
    p = subprocess.run([sys.executable, "-m", "pytest", "-q", "-rs", str(tmp_path)],
                       capture_output=True, text=True, env=env)
    assert "skipped" in p.stdout and "not a local/private address" in p.stdout
    assert "failed" not in p.stdout                  # and it never sent a request


# ---- the red / green / one-red loop, end to end ----

def _serve(src: str, name: str, tmp: Path):
    os.environ["TASKFLOW_DB"] = str(tmp / f"{name}.db")
    mod = types.ModuleType(name)
    exec(compile(src, name, "exec"), mod.__dict__)
    mod.init_db()

    class Q(wsgiref.simple_server.WSGIRequestHandler):
        def log_message(self, *a):
            pass

    srv = wsgiref.simple_server.make_server("127.0.0.1", 0, mod.app, handler_class=Q)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    time.sleep(0.3)
    return srv, f"http://127.0.0.1:{srv.server_address[1]}"


def _run_generated(tests: Path, cfg_file: Path, base: str):
    p = subprocess.run([sys.executable, "-m", "mallory.cli", "regress", "--base-url", base,
                        "--config", str(cfg_file), "--tests", str(tests)],
                       capture_output=True, text=True)
    return p.returncode, p.stdout + p.stderr


def test_generated_tests_go_red_on_bugs_green_on_fix_and_catch_a_single_regression(tmp_path: Path):
    from mallory.render import browser_available
    if not browser_available():
        pytest.skip("needs a browser: two of the generated tests exercise the rendered DOM")
    from mallory.agents.hostile import HostileAgent
    from mallory.config import Config, TargetConfig, UserConfig
    from mallory.findings import confirm, dedup
    from mallory.reporter import write_report
    from mallory.sandbox import Sandbox

    vuln = Path("examples/taskflow/app.py").read_text()
    fixed = Path("examples/taskflow-fixed/app.py").read_text()
    idor_fix = '"SELECT * FROM tasks WHERE id=? AND owner_id=?", (task_id, u["id"])'
    assert idor_fix in fixed
    regressed = fixed.replace(idor_fix, '"SELECT * FROM tasks WHERE id=?", (task_id,)')

    users = [UserConfig(label="alice", email="alice@example.com", password="password123"),
             UserConfig(label="bob", email="bob@example.com", password="password123")]
    cfg = Config(target=TargetConfig(compose="x", service="web", port=1), users=users)
    cfg_file = tmp_path / "mallory.yaml"
    cfg_file.write_text(
        "target: {compose: x, service: web, port: 1}\n"
        "users:\n  - {label: alice, email: alice@example.com, password: password123}\n"
        "  - {label: bob, email: bob@example.com, password: password123}\n")

    # 1) Mallory scans the vulnerable app and generates the tests
    srv, base = _serve(vuln, "vuln", tmp_path)
    try:
        found = dedup(HostileAgent(cfg, Sandbox(base_url=base)).run())

        from mallory.cli import _make_replayer
        confirmed, dropped = confirm(found, _make_replayer(cfg, Sandbox(base_url=base)))
    finally:
        srv.shutdown()
    write_report(confirmed, len(dropped), tmp_path / "out")
    tests = tmp_path / "out" / "tests"
    n = len(list(tests.glob("test_*.py")))
    assert n >= 6                                    # every serious class produced a real test

    # 2) red: every bug present -> every generated test fails
    srv, base = _serve(vuln, "vuln2", tmp_path)
    try:
        rc, out = _run_generated(tests, cfg_file, base)
    finally:
        srv.shutdown()
    assert rc == 1 and f"{n} failed" in out and "passed" not in out

    # 3) green: every bug fixed -> every generated test passes, nothing skipped
    srv, base = _serve(fixed, "fixed", tmp_path)
    try:
        rc, out = _run_generated(tests, cfg_file, base)
    finally:
        srv.shutdown()
    assert rc == 0 and f"{n} passed" in out and "skipped" not in out

    # 4) one bug reintroduced -> exactly that one test goes red
    srv, base = _serve(regressed, "regressed", tmp_path)
    try:
        rc, out = _run_generated(tests, cfg_file, base)
    finally:
        srv.shutdown()
    assert rc == 1 and "1 failed" in out and f"{n - 1} passed" in out
    idor_test = next(p for p in tests.glob("test_*.py") if "IDOR" in p.read_text())
    assert idor_test.name in out                     # ...and it is the IDOR one
