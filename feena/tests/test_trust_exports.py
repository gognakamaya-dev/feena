import json
from pathlib import Path

from click.testing import CliRunner

from feena.cli import main
from feena.evidence import BrowserEvidence, diagnostic_url
from feena.findings import Finding, Kind, Severity, Step, confirm, dedup
from feena.reporter import write_report
from feena.verification import Status, VerificationResult


def finding(agent="regular"):
    return Finding(Kind.WEAK_HEADERS, Severity.LOW, "Missing CSP", "Expected CSP", agent,
                   steps=[Step("http_get", "/")],
                   repro={"type": "header", "path": "/", "header": "content-security-policy"})


def test_corroboration_never_bypasses_failed_replay():
    candidates = dedup([finding(), finding("clumsy"), finding("regular")])
    assert candidates[0].observed_by == ["clumsy", "regular"]
    confirmed, dropped = confirm(candidates, lambda f: VerificationResult(Status.INCONCLUSIVE, "No fixture"))
    assert confirmed == []
    assert not dropped[0].confirmed
    assert dropped[0].verification_method == "none"


def test_report_records_verification_and_missing_evidence(tmp_path):
    verified, _ = confirm([finding()], lambda f: VerificationResult(Status.REPRODUCED, "Header absent"))
    report = write_report(verified, 0, tmp_path)
    assert "Assertion verified" in report.read_text()
    package = json.loads((tmp_path / "evidence" / f"{verified[0].fingerprint}.json").read_text())
    assert package["finding"]["verification_method"] == "assertion_replay"
    assert package["unavailable_evidence"] == ["console", "network", "dom", "trace", "screenshot"]
    assert (tmp_path / package["test"]).exists()
    assert "execution" in package["export_status"]


def test_custom_replay_cannot_claim_builtin_assertion_verification(tmp_path):
    verified, _ = confirm([finding()], lambda f: True)
    report = write_report(verified, 0, tmp_path).read_text()
    assert "Replay confirmed" in report
    assert "Assertion verified" not in report


def test_diagnostic_urls_exclude_credentials_and_queries():
    assert diagnostic_url("https://user:secret@example.com/api?token=secret#value") == "https://example.com/api"


def test_console_and_network_capture_are_bounded(tmp_path):
    class Emitter:
        def __init__(self):
            self.handlers = {}

        def on(self, event, handler):
            self.handlers[event] = handler

    from types import SimpleNamespace
    context, page = Emitter(), Emitter()
    evidence = BrowserEvidence(context, tmp_path)
    context.handlers["page"](page)
    page.handlers["console"](SimpleNamespace(type="error", text="Unexpected checkout failure"))
    context.handlers["response"](SimpleNamespace(url="http://localhost/api?token=secret", status=500,
                                                request=SimpleNamespace(method="POST")))
    for _ in range(1001):
        page.handlers["pageerror"]("boom")
    evidence.save()
    assert len(json.loads((tmp_path / "console.json").read_text())) == 1000
    assert "secret" not in (tmp_path / "network.json").read_text()


def test_export_manifest_validates_and_adopts_all_helpers(tmp_path):
    from feena.config import load_config
    scenario = load_config(Path(__file__).parents[1] / "examples/resilient-checkout/feena.yaml").scenarios[0]
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps({"version": 1, "scenario": scenario.model_dump(),
                                    "profile": scenario.profiles[-1].model_dump()}))
    source, target = tmp_path / "exports", tmp_path / "adopted"
    response = CliRunner().invoke(main, ["export-simulation", str(manifest), "--out", str(source)])
    assert response.exit_code == 0, response.output
    response = CliRunner().invoke(main, ["adopt", "--all", "--from", str(source), "--to", str(target)])
    assert response.exit_code == 0, response.output
    for path in source.glob("*.py"):
        assert (target / path.name).read_text() == path.read_text()
        compile(path.read_text(), str(path), "exec")
        assert "from ." not in path.read_text()
