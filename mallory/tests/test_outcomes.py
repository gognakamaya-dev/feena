from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest
from click.testing import CliRunner
from pydantic import ValidationError

from mallory.cli import main
from mallory.config import Config, OutcomeConfig, OutcomeStep, TargetConfig, UserConfig
from mallory.outcomes import check_outcome, run_outcomes
from mallory.regress import write_tests


def journey():
    return OutcomeConfig(name="own-task-update", steps=[
        OutcomeStep(path="/api/tasks/1", expected_json={"owner_id": 1}),
        OutcomeStep(method="PATCH", path="/api/tasks/1", json_body={"title": "updated"},
                    expected_json={"id": 1}),
        OutcomeStep(path="/api/tasks/1", expected_json={"owner_id": 1, "title": "updated"}),
    ])


@pytest.fixture
def app(monkeypatch):
    state = {"title": "original", "broken": "", "calls": []}

    def handle(request):
        state["calls"].append((request.method, request.url.path))
        if request.url.path in ("/api/login", "/login", "/api/auth/login"):
            return httpx.Response(200, headers={"set-cookie": "session=alice; Path=/"})
        assert "session=alice" in request.headers.get("cookie", "")
        if request.url.path == "/api/me":
            email = "anonymous" if state["broken"] == "anonymous-cookie" else "alice"
            return httpx.Response(200, json={"email": email})
        if state["broken"] == "removed":
            return httpx.Response(404, json={"error": "not found"})
        if state["broken"] == "redirect":
            return httpx.Response(302, headers={"location": "https://example.com"})
        if request.method == "PATCH" and state["broken"] != "lost-update":
            state["title"] = "updated"
        return httpx.Response(200, json={"id": 1, "owner_id": 1, "title": state["title"]})

    original = httpx.Client
    monkeypatch.setattr(httpx, "Client", lambda **kw: original(
        **kw, transport=httpx.MockTransport(handle)))
    return state


def test_read_update_and_read_back(app):
    check_outcome("http://localhost", journey().model_dump(), ("alice", "secret"))
    assert app["calls"] == [("POST", "/api/login"), ("GET", "/api/me"), ("GET", "/api/tasks/1"),
                            ("PATCH", "/api/tasks/1"), ("GET", "/api/tasks/1")]


@pytest.mark.parametrize("broken", ["removed", "lost-update", "redirect"])
def test_broken_features_do_not_pass(app, broken):
    app["broken"] = broken
    users = [UserConfig(label="alice", email="alice", password="secret")]
    result, = run_outcomes([journey()], "http://localhost", users)
    assert result.status == "failed"
    assert "secret" not in result.reason


def test_missing_setup_is_inconclusive(app):
    result, = run_outcomes([journey()], "http://localhost", [])
    assert result.status == "inconclusive"
    assert app["calls"] == []


def test_cookie_without_authenticated_identity_cannot_pass(app):
    app["broken"] = "anonymous-cookie"
    users = [UserConfig(label="alice", email="alice", password="secret")]
    result, = run_outcomes([journey()], "http://localhost", users)
    assert result.status == "inconclusive"
    assert ("PATCH", "/api/tasks/1") not in app["calls"]


@pytest.mark.parametrize("path", ["https://example.com", "//example.com", "/\\example.com", "/a#b"])
def test_outcomes_cannot_address_another_host(path):
    with pytest.raises(ValidationError):
        OutcomeStep(path=path, expected_json={"ok": True})
    with pytest.raises(ValidationError):
        OutcomeConfig(name="invalid", identity_path=path, steps=journey().steps)


def test_outcomes_require_assertions_and_unique_names():
    with pytest.raises(ValidationError):
        OutcomeStep(path="/", expected_json={})
    with pytest.raises(ValidationError):
        Config(target=TargetConfig(compose="", service="", port=1),
               outcomes=[journey(), journey()])


def test_standalone_generation_and_adoption(tmp_path: Path):
    src, dest = tmp_path / "generated", tmp_path / "adopted"
    written, manual = write_tests([], src, [journey()])
    assert len(written) == 1 and not manual
    compile(written[0].read_text(), str(written[0]), "exec")
    assert "secret" not in written[0].read_text()
    result = CliRunner().invoke(main, ["adopt", "--all", "--from", str(src), "--to", str(dest)])
    assert result.exit_code == 0, result.output
    assert (dest / "_mallory_outcomes.py").exists()


@pytest.mark.parametrize("command", ["run", "ci"])
def test_commands_gate_on_outcomes_even_without_findings(tmp_path, monkeypatch, command):
    from contextlib import contextmanager

    from mallory import cli

    @contextmanager
    def target(*args):
        yield SimpleNamespace(base_url="http://localhost")

    cfg = Config(target=TargetConfig(compose="", service="", port=1), outcomes=[journey()])
    cfg.report.out_dir = str(tmp_path)
    monkeypatch.setattr(cli, "_load_or_default", lambda *args: cfg)
    monkeypatch.setattr(cli, "_target", target)
    monkeypatch.setattr(cli, "_scan", lambda *args: ([], 0))
    args = [command, "--url", "http://localhost"]
    if command == "ci":
        args += ["--no-comment", "--fail-on", "none", "--tests", str(tmp_path / "absent")]
    result = CliRunner().invoke(main, args)
    assert result.exit_code == 1, result.output
    assert "INCONCLUSIVE" in (tmp_path / "report.md").read_text()


@pytest.mark.parametrize("mode,passed,failed", [
    ("fixed", 2, 0), ("idor", 1, 1), ("removed", 1, 1), ("lost-update", 1, 1),
])
def test_paired_generated_tests_against_live_app(tmp_path, mode, passed, failed):
    import threading
    from wsgiref.simple_server import WSGIRequestHandler, make_server

    from flask import Flask, request, session

    from mallory.ci import run_regression
    from mallory.findings import Finding, Kind, Severity

    app = Flask(__name__)
    app.secret_key = "disposable-test-key"
    tasks = {1: {"id": 1, "owner_id": 1, "title": "original"},
             2: {"id": 2, "owner_id": 2, "title": "other user's task"}}

    @app.post("/api/login")
    def login():
        if request.json != {"email": "alice", "password": "test-password"}:
            return {"error": "bad login"}, 401
        session["user"] = 1
        return {"ok": True}

    @app.get("/api/me")
    def me():
        return {"id": session["user"], "email": "alice"}

    @app.route("/api/tasks/<int:task_id>", methods=["GET", "PATCH"])
    def task(task_id):
        if mode == "removed":
            return {"error": "not found"}, 404
        row = tasks[task_id]
        if row["owner_id"] != session["user"] and mode != "idor":
            return {"error": "forbidden"}, 403
        if request.method == "PATCH" and mode != "lost-update":
            row["title"] = request.json["title"]
        return row

    class Quiet(WSGIRequestHandler):
        def log_message(self, *args):
            pass

    finding = Finding(kind=Kind.ACCESS_CONTROL, severity=Severity.HIGH, title="IDOR",
                      detail="", agent="hostile", repro={"type": "idor", "path": "/api/tasks/2"})
    write_tests([finding], tmp_path, [journey()])
    users = [UserConfig(label="alice", email="alice", password="test-password")]
    with make_server("127.0.0.1", 0, app, handler_class=Quiet) as server:
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            result = run_regression(tmp_path, f"http://127.0.0.1:{server.server_port}", users)
        finally:
            server.shutdown()
            thread.join()
    assert result.ran and result.passed == passed and result.failed == failed
    assert result.skipped == 0


def test_generated_outcome_missing_credentials_fails_not_skips(tmp_path, monkeypatch):
    from mallory.ci import run_regression

    monkeypatch.delenv("MALLORY_USER1_EMAIL", raising=False)
    monkeypatch.delenv("MALLORY_USER1_PASSWORD", raising=False)
    write_tests([], tmp_path, [journey()])
    result = run_regression(tmp_path, "http://127.0.0.1:1", [])
    assert result.ran and result.failed == 1 and result.skipped == 0


def test_scan_retains_inconclusive_status_without_raw_evidence(tmp_path, monkeypatch):
    import json

    from mallory import cli
    from mallory.findings import Finding, Kind, Severity
    from mallory.sandbox import Sandbox

    finding = Finding(kind=Kind.BROKEN_FLOW, severity=Severity.HIGH,
                      title="Unverified browser issue", detail="private page contents",
                      agent="regular", evidence={"screenshot": "private.png"})
    cfg = Config(target=TargetConfig(compose="", service="", port=1))
    cfg.report.out_dir = str(tmp_path)
    monkeypatch.setattr(cli, "_run_agents", lambda *args: [finding])
    confirmed, dropped = cli._scan(cfg, Sandbox(base_url="http://localhost"), [])
    assert confirmed == [] and dropped == 1
    text = (tmp_path / "verification.json").read_text()
    assert json.loads(text)[0]["status"] == "inconclusive"
    assert "private" not in text
