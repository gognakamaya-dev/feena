from __future__ import annotations

import json
import threading
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit

import pytest

from feena.config import Config, TargetConfig, UserConfig
from feena.findings import Finding, Kind, Severity, Step, confirm
from feena.sandbox import Sandbox
from feena.verification import Status, verify_finding


@pytest.fixture
def local_app():
    state = {"header": False, "root_status": 200, "tasks": False,
             "reflect": False, "stored": "", "same_account": False,
             "email_mismatch": False,
             "tasks_unauth": False, "tokens": {}}

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_args):
            pass

        def do_GET(self):
            path = urlsplit(self.path).path
            if path == "/":
                self.send_response(state["root_status"])
                if state["header"]:
                    self.send_header("Content-Security-Policy", "default-src 'self'")
                self.send_header("Content-Type", "text/html")
                value = parse_qs(urlsplit(self.path).query).get("q", [""])[0]
                body = f"<html>local fixture {'<p>' + value + '</p>' if state['reflect'] else ''}</html>".encode()
            elif path == "/form":
                self.send_response(200)
                self.send_header("Content-Type", "text/html")
                body = b'<form method="post" action="/submit"><input name="title"><button type="submit">Save</button></form>'
            elif path == "/tasks":
                self.send_response(200)
                self.send_header("Content-Type", "text/html")
                body = f"<html>{state['stored']}</html>".encode()
            elif path == "/api/me":
                token = SimpleCookie(self.headers.get("Cookie", "")).get("session")
                email = state["tokens"].get(token.value) if token else None
                if not email:
                    self.send_response(401)
                    self.send_header("Content-Type", "application/json")
                    body = b'{"error":"auth required"}'
                else:
                    account_id = "1" if state["same_account"] else email
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    observed_email = "alice@example.com" if state["email_mismatch"] else email
                    body = json.dumps({"id": account_id, "email": observed_email}).encode()
            elif path == "/api/tasks" and state["tasks"]:
                token = SimpleCookie(self.headers.get("Cookie", "")).get("session")
                if not token and not state["tasks_unauth"]:
                    self.send_response(401)
                    self.send_header("Content-Type", "application/json")
                    body = b'{"error":"auth required"}'
                    self.end_headers()
                    self.wfile.write(body)
                    return
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                body = json.dumps([{"id": 1, "owner_id": "same"}]).encode()
            else:
                self.send_response(404)
                self.send_header("Content-Type", "text/plain")
                body = b"not found"
            self.end_headers()
            self.wfile.write(body)

        def do_POST(self):
            path = urlsplit(self.path).path
            if path == "/api/login":
                length = int(self.headers.get("Content-Length", "0"))
                payload = json.loads(self.rfile.read(length).decode())
                email = payload.get("email")
                if email not in ("alice@example.com", "bob@example.com") or \
                        payload.get("password") != "password123":
                    self.send_response(401)
                    self.end_headers()
                    return
                token = "token-" + email
                state["tokens"][token] = email
                self.send_response(200)
                self.send_header("Set-Cookie", f"session={token}; Path=/")
                self.end_headers()
                return
            if path != "/submit":
                self.send_error(404)
                return
            length = int(self.headers.get("Content-Length", "0"))
            form = parse_qs(self.rfile.read(length).decode())
            state["stored"] = form.get("title", [""])[0]
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(b"saved")

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_address[1]}"
    try:
        yield state, Sandbox(base_url=base), Config(
            target=TargetConfig(compose="", service="", port=0))
    finally:
        server.shutdown()
        thread.join()
        server.server_close()


def _header_finding() -> Finding:
    return Finding(
        kind=Kind.WEAK_HEADERS, severity=Severity.MEDIUM, title="Missing CSP",
        detail="The root response has no CSP.", agent="hostile",
        steps=[Step(action="http_get", target="/")],
        evidence={"status": 200},
        repro={"type": "header", "path": "/", "header": "content-security-policy"},
    )


def test_missing_header_is_reproduced_and_header_added_is_fixed(local_app):
    state, sandbox, cfg = local_app
    finding = _header_finding()

    result = verify_finding(finding, cfg, sandbox)
    assert result.status is Status.REPRODUCED

    state["header"] = True
    result = verify_finding(finding, cfg, sandbox)
    assert result.status is Status.NOT_REPRODUCED


def test_http_status_alone_does_not_confirm_and_missing_route_is_inconclusive(local_app):
    state, sandbox, cfg = local_app
    finding = _header_finding()
    state["header"] = True
    assert verify_finding(finding, cfg, sandbox).status is Status.NOT_REPRODUCED

    state["root_status"] = 404
    result = verify_finding(finding, cfg, sandbox)
    assert result.status is Status.INCONCLUSIVE
    confirmed, dropped = confirm([finding], lambda _finding: result)
    assert not confirmed and dropped == [finding]
    assert finding.verification_status == "inconclusive"
    assert finding.verification_reason


def test_evidence_without_supported_repro_does_not_confirm(local_app):
    _, sandbox, cfg = local_app
    finding = _header_finding()
    finding.repro = {}
    finding.steps = [Step(action="click", target="button")]
    assert verify_finding(finding, cfg, sandbox).status is Status.INCONCLUSIVE

    finding.repro = {"type": "reflected", "path": "/", "param": "q", "rendered": True}
    assert verify_finding(finding, cfg, sandbox).status is Status.NOT_REPRODUCED


def test_missing_auth_setup_is_inconclusive(local_app):
    _, sandbox, cfg = local_app
    finding = _header_finding()
    finding.repro = {"type": "idor", "path": "/api/tasks/1"}
    result = verify_finding(finding, cfg, sandbox)
    assert result.status is Status.INCONCLUSIVE
    assert "credentials" in result.reason


def test_unreachable_target_is_inconclusive(local_app, monkeypatch):
    _, sandbox, cfg = local_app
    finding = _header_finding()

    monkeypatch.setattr("feena.verification._get", lambda *_args, **_kwargs: None)
    result = verify_finding(finding, cfg, sandbox)
    assert result.status is Status.INCONCLUSIVE
    assert "could not be reached" in result.reason


def test_missing_auth_finding_requires_data_not_just_status(local_app):
    state, sandbox, cfg = local_app
    finding = _header_finding()
    finding.kind = Kind.MISSING_AUTH
    finding.repro = {"type": "missing_auth", "path": "/api/tasks"}
    assert verify_finding(finding, cfg, sandbox).status is Status.INCONCLUSIVE

    state["tasks"] = True
    state["tasks_unauth"] = True
    assert verify_finding(finding, cfg, sandbox).status is Status.REPRODUCED


def test_rendered_reflection_replays_recorded_surface(local_app):
    state, sandbox, cfg = local_app
    finding = _header_finding()
    finding.repro = {"type": "reflected", "path": "/", "param": "q", "rendered": True}
    state["reflect"] = True
    assert verify_finding(finding, cfg, sandbox).status is Status.REPRODUCED
    state["reflect"] = False
    assert verify_finding(finding, cfg, sandbox).status is Status.NOT_REPRODUCED


def test_rendered_stored_xss_replays_form_and_page_spec(local_app):
    state, sandbox, cfg = local_app
    finding = _header_finding()
    finding.repro = {
        "type": "stored_xss", "rendered": True, "login": False,
        "page": "/tasks", "form_page": "/form", "action": "/submit",
        "method": "post", "fields": ["title"],
    }
    assert verify_finding(finding, cfg, sandbox).status is Status.REPRODUCED
    assert "<b>" in state["stored"]


def test_same_data_requires_distinct_authenticated_account_identities(local_app):
    state, sandbox, cfg = local_app
    cfg.users = [
        UserConfig(label="alice", email="alice@example.com", password="password123"),
        UserConfig(label="bob", email="bob@example.com", password="password123"),
    ]
    finding = _header_finding()
    finding.repro = {"type": "same_data", "path": "/api/tasks"}
    state["tasks"] = True

    state["same_account"] = True
    result = verify_finding(finding, cfg, sandbox)
    assert result.status is Status.INCONCLUSIVE
    assert "same authenticated account ID" in result.reason

    state["same_account"] = False
    result = verify_finding(finding, cfg, sandbox)
    assert result.status is Status.REPRODUCED


def test_same_data_requires_api_me_email_to_match_configured_account(local_app):
    state, sandbox, cfg = local_app
    cfg.users = [
        UserConfig(label="alice", email="alice@example.com", password="password123"),
        UserConfig(label="bob", email="bob@example.com", password="password123"),
    ]
    finding = _header_finding()
    finding.repro = {"type": "same_data", "path": "/api/tasks"}
    state["tasks"] = True

    state["email_mismatch"] = True
    result = verify_finding(finding, cfg, sandbox)
    assert result.status is Status.INCONCLUSIVE
    assert "did not match" in result.reason


def test_browser_replay_waits_for_spa_settle_and_falls_back_on_timeout():
    from feena.verification import _browser_get

    class Response:
        status = 200

        def __init__(self):
            self.headers = {"content-type": "text/html"}

    class Page:
        def __init__(self, timeout=False):
            self.timeout = timeout
            self.settled = False

        def goto(self, *_args, **_kwargs):
            return Response()

        def wait_for_load_state(self, state, timeout):
            assert state == "networkidle"
            assert timeout == 123
            if self.timeout:
                raise TimeoutError
            self.settled = True

        def wait_for_timeout(self, _milliseconds):
            self.settled = True

        def content(self):
            assert self.settled
            return "<html><main>client-rendered</main></html>"

    class Renderer:
        base_url = "http://127.0.0.1:1234"
        settle_ms = 123

        def __init__(self, timeout=False):
            self.page = Page(timeout)

    for timeout in (False, True):
        html, error = _browser_get(Renderer(timeout), "/")
        assert error is None
        assert "client-rendered" in html


def test_verification_fields_are_json_serializable(local_app):
    _, sandbox, cfg = local_app
    finding = _header_finding()
    result = verify_finding(finding, cfg, sandbox)
    confirmed, _ = confirm([finding], lambda _finding: result)
    encoded = json.dumps({"status": finding.verification_status,
                          "reason": finding.verification_reason,
                          "detail_status": result.status,
                          "detail_reason": result.reason})
    assert json.loads(encoded)["status"] == "reproduced"
    assert confirmed == [finding]


def test_boolean_custom_replayer_uses_not_reproduced_status():
    finding = _header_finding()
    confirmed, dropped = confirm([finding], lambda _finding: False)
    assert not confirmed and dropped == [finding]
    assert finding.verification_status == "not_reproduced"
