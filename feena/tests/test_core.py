"""Unit tests that run without Docker or a network."""
from __future__ import annotations

from pathlib import Path

import httpx

from feena.config import load_config
from feena.findings import Finding, Kind, Severity, Step, confirm, dedup


def test_load_example_config(tmp_path: Path):
    cfg_file = tmp_path / "feena.yaml"
    cfg_file.write_text(
        "target:\n"
        "  compose: ./docker-compose.yml\n"
        "  service: web\n"
        "  port: 3000\n"
        "users:\n"
        "  - {label: alice, email: a@x.com, password: p}\n"
    )
    cfg = load_config(cfg_file)
    assert cfg.target.service == "web"
    assert cfg.users[0].label == "alice"
    assert cfg.out_path.name == ".feena"


def _finding(title="t", steps=None):
    return Finding(
        kind=Kind.WEAK_HEADERS, severity=Severity.LOW, title=title,
        detail="d", agent="hostile", steps=steps or [Step(action="http_get", target="/")],
    )


def test_dedup_collapses_identical_findings():
    a, b = _finding(), _finding()
    assert len(dedup([a, b])) == 1


def test_confirm_drops_unreproducible():
    good, bad = _finding("good"), _finding("bad")
    confirmed, dropped = confirm([good, bad], replayer=lambda f: f.title == "good")
    assert [f.title for f in confirmed] == ["good"]
    assert [f.title for f in dropped] == ["bad"]
    assert confirmed[0].confirmed is True


def test_header_check_flags_missing_headers():
    from feena.agents.checks import headers
    from feena.config import Config, TargetConfig
    from feena.sandbox import Sandbox

    # A fake app that returns no security headers at all.
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="<html>hi</html>")

    transport = httpx.MockTransport(handler)
    # Monkeypatch httpx.get used inside the check to go through the mock transport.
    real_get = httpx.get

    def fake_get(url, **kw):
        with httpx.Client(transport=transport) as c:
            return c.get(url, **{k: v for k, v in kw.items() if k != "timeout"})

    httpx.get = fake_get
    try:
        cfg = Config(target=TargetConfig(compose="x", service="web", port=1))
        sandbox = Sandbox(base_url="http://sandbox.local")
        found = headers.run(cfg, sandbox)
    finally:
        httpx.get = real_get

    titles = {f.title for f in found}
    assert any("content-security-policy" in t for t in titles)
    assert all(f.kind is Kind.WEAK_HEADERS for f in found)
