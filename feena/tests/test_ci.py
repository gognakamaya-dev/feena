"""Tests for the CI layer: attach guard, baseline, verdict, sticky comment, and the Action."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import time
import types
import wsgiref.simple_server
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest
import yaml

from feena import ci
from feena.findings import Finding, Kind, Severity, Step
from feena.sandbox import SandboxError, attach

ROOT = Path(__file__).resolve().parent.parent


def _f(sev=Severity.HIGH, title="t", steps=None):
    f = Finding(kind=Kind.ACCESS_CONTROL, severity=sev, title=title, detail="d", agent="hostile",
                steps=steps or [Step(action="http_get", target=f"/{title}")])
    f.confirmed = True
    return f


# ---------------------------------------------------------------- attach guard

def test_attach_accepts_local_and_private_targets(monkeypatch):
    assert attach("http://127.0.0.1:3000").base_url == "http://127.0.0.1:3000"
    assert attach("http://localhost:3000/").base_url == "http://localhost:3000"
    monkeypatch.setattr("socket.getaddrinfo", lambda h, p, *a, **k: [(2, 1, 6, "", ("10.0.4.7", 0))])
    assert attach("http://web:3000")                    # a docker-compose service on a private net


@pytest.mark.parametrize("url", ["http://8.8.8.8", "ftp://127.0.0.1", "not a url", "http://"])
def test_attach_refuses_public_and_malformed(url):
    with pytest.raises(SandboxError):
        attach(url)


def test_attach_resolves_names_instead_of_trusting_them(monkeypatch):
    # 'localhost.evil.com' looks local but resolves public: must be refused.
    monkeypatch.setattr("socket.getaddrinfo", lambda h, p, *a, **k: [(2, 1, 6, "", ("93.184.216.34", 0))])
    with pytest.raises(SandboxError):
        attach("http://localhost.evil.com")
    # A name with ANY public address is refused, even if others are private.
    monkeypatch.setattr("socket.getaddrinfo", lambda h, p, *a, **k: [
        (2, 1, 6, "", ("10.0.0.5", 0)), (2, 1, 6, "", ("93.184.216.34", 0))])
    with pytest.raises(SandboxError):
        attach("http://mixed.internal")
    # Unresolvable: refused.
    import socket
    def boom(*a, **k):
        raise socket.gaierror("nope")
    monkeypatch.setattr("socket.getaddrinfo", boom)
    with pytest.raises(SandboxError):
        attach("http://nonexistent.invalid")


def test_cli_refuses_public_host_with_exit_2(tmp_path):
    p = subprocess.run([sys.executable, "-m", "feena.cli", "ci", "--url", "http://8.8.8.8"],
                       cwd=tmp_path, capture_output=True, text=True)
    assert p.returncode == 2 and "Refusing to attach" in (p.stdout + p.stderr)


# ---------------------------------------------------------------- baseline

def test_baseline_roundtrip_and_split(tmp_path):
    a, b, c = _f(Severity.CRITICAL, "a"), _f(Severity.LOW, "b"), _f(Severity.HIGH, "c")
    path = tmp_path / "feena.baseline.json"
    assert ci.write_baseline([a, b], path) == 2
    baseline = ci.load_baseline(path)
    assert set(baseline) == {a.fingerprint, b.fingerprint}
    new, known, fixed = ci.split_by_baseline([b, c], baseline)   # 'a' was fixed, 'c' is new
    assert [f.title for f in new] == ["c"]
    assert [f.title for f in known] == ["b"]
    assert [e["title"] for e in fixed] == ["a"]


def test_missing_baseline_is_empty(tmp_path):
    assert ci.load_baseline(tmp_path / "nope.json") == {}


# ---------------------------------------------------------------- verdict

@pytest.mark.parametrize("sev,fail_on,expect_fail", [
    (Severity.MEDIUM, "high", False), (Severity.HIGH, "high", True),
    (Severity.CRITICAL, "high", True), (Severity.LOW, "low", True),
    (Severity.CRITICAL, "none", False), (Severity.MEDIUM, "critical", False),
])
def test_decide_threshold(sev, fail_on, expect_fail):
    v = ci.decide([_f(sev)], ci.RegressionResult(), fail_on)
    assert v.failed is expect_fail


def test_regression_failure_always_fails_even_with_fail_on_none():
    v = ci.decide([], ci.RegressionResult(ran=True, passed=3, failed=1), "none")
    assert v.failed and "regression" in v.reasons[0]


def test_skipped_regression_tests_warn_but_do_not_fail():
    r = ci.RegressionResult(ran=True, passed=2, skipped=1)
    v = ci.decide([], r, "high")
    assert not v.failed
    body = ci.render_comment([], [], [], r, v, 0, "high", True)
    assert "skipped" in body and "guards nothing" in body


# ---------------------------------------------------------------- comment rendering

def test_comment_never_nudges_baselining_once_regression_tests_exist():
    new = [_f(Severity.CRITICAL, "idor")]
    reg = ci.RegressionResult(ran=True, passed=8, failed=1, failures=[("IDOR back", "test_x.py")])
    v = ci.decide(new, reg, "high")
    body = ci.render_comment(new, [], [], reg, v, 0, "high", has_baseline=False)
    assert "feena baseline" not in body and "IDOR back" in body and ci.MARKER in body
    # ...but on a genuine first run it does explain baselining.
    first = ci.render_comment(new, [], [], ci.RegressionResult(note="none yet"),
                              ci.decide(new, ci.RegressionResult(), "high"), 0, "high", False)
    assert "feena baseline" in first


def test_comment_is_truncated_to_githubs_limit():
    many = [Finding(kind=Kind.WEAK_HEADERS, severity=Severity.LOW, title=f"t{i}", detail="x" * 900,
                    agent="hostile", steps=[Step(action="http_get", target=f"/{i}")]) for i in range(200)]
    body = ci.render_comment(many, [], [], ci.RegressionResult(), ci.decide(many, ci.RegressionResult(), "none"),
                             0, "none", True)
    assert len(body) < 65536 and "truncated" in body


# ---------------------------------------------------------------- regression runner

def test_run_regression_parses_junit_and_names_the_failing_finding(tmp_path):
    (tmp_path / "test_aaa.py").write_text('"""\nFinding : IDOR is back\n"""\ndef test_a():\n    assert False\n')
    (tmp_path / "test_bbb.py").write_text("def test_b():\n    assert True\n")
    (tmp_path / "test_ccc.py").write_text("import pytest\ndef test_c():\n    pytest.skip('no login')\n")
    r = ci.run_regression(tmp_path, "http://127.0.0.1:1", [])
    assert (r.ran, r.passed, r.failed, r.skipped) == (True, 1, 1, 1)
    assert r.failures == [("IDOR is back", "test_aaa.py")]


def test_run_regression_without_tests_is_not_a_failure(tmp_path):
    r = ci.run_regression(tmp_path / "missing", "http://127.0.0.1:1", [])
    assert r.ran is False and "no committed regression tests" in r.note
    assert not ci.decide([], r, "high").failed


def test_regression_tests_do_not_receive_ci_secrets(tmp_path, monkeypatch):
    monkeypatch.setenv("GITHUB_TOKEN", "super-secret")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "also-secret")
    (tmp_path / "test_env.py").write_text(
        "import os\ndef test_no_secrets():\n"
        "    assert 'GITHUB_TOKEN' not in os.environ and 'ANTHROPIC_API_KEY' not in os.environ\n")
    assert ci.run_regression(tmp_path, "http://127.0.0.1:1", []).passed == 1


# ---------------------------------------------------------------- sticky comment

class _GH(BaseHTTPRequestHandler):
    comments: list = []
    calls: list = []
    mode = "ok"

    def log_message(self, *a): pass

    def _send(self, code, obj):
        b = json.dumps(obj).encode()
        self.send_response(code); self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(b))); self.end_headers(); self.wfile.write(b)

    def do_GET(self):
        type(self).calls.append("GET"); self._send(200, type(self).comments)

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        type(self).calls.append("POST")
        if type(self).mode == "forbidden":
            return self._send(403, {"message": "Resource not accessible by integration"})
        c = {"id": len(type(self).comments) + 1, "body": body["body"]}
        type(self).comments.append(c); self._send(201, c)

    def do_PATCH(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        cid = int(self.path.rsplit("/", 1)[1]); type(self).calls.append("PATCH")
        for c in type(self).comments:
            if c["id"] == cid:
                c["body"] = body["body"]
        self._send(200, {"id": cid})


@pytest.fixture
def gh(tmp_path, monkeypatch):
    handler = type("H", (_GH,), {"comments": [], "calls": [], "mode": "ok"})
    srv = HTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    event = tmp_path / "event.json"
    event.write_text(json.dumps({"pull_request": {"number": 7}}))
    for k, v in {"GITHUB_TOKEN": "t", "GITHUB_REPOSITORY": "o/r", "GITHUB_EVENT_PATH": str(event),
                 "GITHUB_API_URL": f"http://127.0.0.1:{srv.server_port}"}.items():
        monkeypatch.setenv(k, v)
    yield handler
    srv.shutdown()


def test_comment_is_created_once_then_updated_in_place(gh):
    assert ci.upsert_pr_comment(ci.MARKER + "\nfirst") == "created"
    assert ci.upsert_pr_comment(ci.MARKER + "\nsecond") == "updated"
    assert ci.upsert_pr_comment(ci.MARKER + "\nthird") == "updated"
    assert len(gh.comments) == 1 and "third" in gh.comments[0]["body"]
    assert gh.calls.count("POST") == 1 and gh.calls.count("PATCH") == 2


def test_a_forbidden_comment_never_raises_or_fails_the_build(gh):
    gh.mode = "forbidden"     # what a fork PR's read-only token looks like
    out = ci.upsert_pr_comment(ci.MARKER + "x")
    assert out.startswith("skipped") and "fork" in out


def test_comment_is_skipped_outside_a_pull_request(monkeypatch):
    monkeypatch.delenv("GITHUB_EVENT_PATH", raising=False)
    assert ci.upsert_pr_comment(ci.MARKER).startswith("skipped")


def test_step_summary_and_outputs_are_written(tmp_path, monkeypatch):
    s, o = tmp_path / "summary.md", tmp_path / "out.txt"
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(s)); monkeypatch.setenv("GITHUB_OUTPUT", str(o))
    assert ci.write_step_summary("hello")
    ci.write_outputs(2, 1, True)
    assert "hello" in s.read_text()
    assert "new-findings=2" in o.read_text() and "failed=true" in o.read_text()


# ---------------------------------------------------------------- the Action itself

ACTION = yaml.safe_load((ROOT / "action.yml").read_text())


def test_action_is_a_composite_with_local_or_hosted_target_and_shells():
    assert ACTION["runs"]["using"] == "composite"
    assert ACTION["inputs"]["url"]["required"] is False
    assert "workspace-url" in ACTION["inputs"]
    for step in ACTION["runs"]["steps"]:
        if "run" in step:
            assert step.get("shell") == "bash", step


def test_action_never_interpolates_inputs_into_shell_scripts():
    """Script-injection guard: `${{ ... }}` may appear in env/with, never inside a `run:` body."""
    for step in ACTION["runs"]["steps"]:
        if "run" in step:
            assert "${{" not in step["run"], f"expression interpolated into a script: {step['name']}"


def test_action_outputs_come_from_the_feena_step_and_report_uploads_always():
    ids = {s.get("id") for s in ACTION["runs"]["steps"]}
    assert "feena" in ids
    for out in ACTION["outputs"].values():
        assert "steps.feena.outputs" in out["value"]
    upload = next(s for s in ACTION["runs"]["steps"] if "upload-artifact" in s.get("uses", ""))
    assert "always()" in upload["if"]


def test_action_only_calls_cli_flags_that_exist():
    run_step = next(s for s in ACTION["runs"]["steps"] if s.get("id") == "feena")["run"]
    import re
    hosted, local = run_step.split('\nfi\n', 1)
    for command, script in [("workflow-ci", hosted), ("ci", local)]:
        help_text = subprocess.run([sys.executable, "-m", "feena.cli", command, "--help"],
                                  capture_output=True, text=True).stdout
        for flag in set(re.findall(r"--[a-z][a-z-]+", script)):
            assert flag in help_text, f"action uses {flag} which {command} does not accept"


def test_example_and_selftest_workflows_are_valid_and_reference_real_paths():
    for wf in [*sorted((ROOT / "examples/ci").glob("*.yml")), *sorted((ROOT / ".github/workflows").glob("*.yml"))]:
        doc = yaml.safe_load(wf.read_text())
        assert "jobs" in doc, wf
    selftest = yaml.safe_load((ROOT / ".github/workflows/selftest.yml").read_text())
    step = next(s for s in selftest["jobs"]["selftest"]["steps"] if s.get("uses") == "./")
    assert (ROOT / step["with"]["tests"]).is_dir() and (ROOT / step["with"]["config"]).is_file()


# ---------------------------------------------------------------- adopt

def test_adopt_copies_selected_tests_and_support(tmp_path):
    src = tmp_path / "gen"
    src.mkdir()
    for n in ("_feena_support.py", "conftest.py", "test_aaa.py", "test_bbb.py"):
        (src / n).write_text("# x")
    run = lambda *a: subprocess.run([sys.executable, "-m", "feena.cli", "adopt", *a, "--from", str(src),
                                     "--to", str(tmp_path / "tests/feena")], capture_output=True, text=True)
    assert run("aaa").returncode == 0
    got = {p.name for p in (tmp_path / "tests/feena").iterdir()}
    assert got == {"_feena_support.py", "conftest.py", "test_aaa.py"}    # only what was asked for
    assert run("zzz").returncode == 2                                     # unknown fingerprint
    assert run().returncode == 2                                          # nothing selected


# ---------------------------------------------------------------- the whole story, end to end

def _serve(src, name, tmp):
    os.environ["TASKFLOW_DB"] = str(tmp / f"{name}.db")
    mod = types.ModuleType(name)
    exec(compile(src, name, "exec"), mod.__dict__)
    mod.init_db()

    class Q(wsgiref.simple_server.WSGIRequestHandler):
        def log_message(self, *a): pass

    srv = wsgiref.simple_server.make_server("127.0.0.1", 0, mod.app, handler_class=Q)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    time.sleep(0.3)
    return srv, f"http://127.0.0.1:{srv.server_address[1]}"


def test_ci_end_to_end_baseline_adopt_and_single_regression(tmp_path, gh):
    from feena.render import browser_available
    if not browser_available():
        pytest.skip("needs a browser for the rendered-DOM checks")
    vuln = (ROOT / "examples/taskflow/app.py").read_text()
    fixed = (ROOT / "examples/taskflow-fixed/app.py").read_text()
    fix = '"SELECT * FROM tasks WHERE id=? AND owner_id=?", (task_id, u["id"])'
    regressed = fixed.replace(fix, '"SELECT * FROM tasks WHERE id=?", (task_id,)')

    work = tmp_path / "work"
    work.mkdir()
    (work / "feena.yaml").write_text(
        "target: {compose: x, service: web, port: 1, healthcheck: /api/health}\n"
        "users:\n  - {label: alice, email: alice@example.com, password: password123}\n"
        "  - {label: bob, email: bob@example.com, password: password123}\n"
        "run: {agents: [hostile]}\n")

    def feena(*args):
        p = subprocess.run([sys.executable, "-m", "feena.cli", *args], cwd=work,
                           capture_output=True, text=True, env={**os.environ, "GITHUB_TOKEN": "t"})
        return p.returncode, p.stdout + p.stderr

    def against(src, name, *args):
        srv, base = _serve(src, name, tmp_path)
        try:
            return feena(*args, "--url", base)
        finally:
            srv.shutdown()

    # first PR on a vulnerable app: serious findings fail the check, the comment is created
    rc, out = against(vuln, "a", "ci")
    assert rc == 1 and "new finding(s) at or above `high`" in out and len(gh.comments) == 1

    # the team accepts today's findings: CI is green and only NEW ones can fail it
    assert against(vuln, "b", "baseline")[0] == 0
    rc, out = against(vuln, "c", "ci")
    assert rc == 0 and "0 new" in out and "9 baselined" in out

    # the team fixes everything and commits the generated tests; baseline is pruned
    assert against(vuln, "d", "run")[0] in (0, 1)              # generates .feena/tests
    assert feena("adopt", "--all")[0] == 0
    (work / "feena.baseline.json").unlink()
    rc, out = against(fixed, "e", "ci")
    assert rc == 0 and "9 passed, 0 failed" in out and "0 new" in out

    # a refactor reintroduces exactly one bug: exactly that one bug fails the PR
    rc, out = against(regressed, "f", "ci")
    assert rc == 1 and "1 failed" in out and "1 new" in out
    body = gh.comments[0]["body"]
    assert "IDOR" in body and "is back" in body and "feena baseline" not in body
    assert len(gh.comments) == 1                                # one comment, updated all along
    assert gh.calls.count("POST") == 1 and gh.calls.count("PATCH") >= 3

