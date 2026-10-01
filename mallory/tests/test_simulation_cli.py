from contextlib import contextmanager
from types import SimpleNamespace

import pytest
from click.testing import CliRunner
from pydantic import ValidationError

from mallory import cli
from mallory.config import Config, TargetConfig
from mallory.simulation_config import BrowserAssertion, BrowserScenario, BrowserStep, NetworkProfile


def scenario():
    return BrowserScenario(name="checkout", goal="Buy exactly once",
                           steps=[BrowserStep(action="goto", target="/")],
                           assertions=[BrowserAssertion(kind="visible", target="button")])


@pytest.mark.parametrize("model,values", [
    (BrowserStep, {"action": "goto", "target": "https://example.com"}),
    (BrowserStep, {"action": "goto", "target": "//example.com"}),
    (BrowserStep, {"action": "click"}),
    (BrowserStep, {"action": "eval", "value": "anything"}),
    (NetworkProfile, {"name": "../escape"}),
    (NetworkProfile, {"name": "slow", "delay_ms": -1}),
    (NetworkProfile, {"name": "slow", "path": "/\\example.com"}),
    (BrowserAssertion, {"kind": "json", "target": "/", "expected": {}}),
    (BrowserAssertion, {"kind": "count", "target": "button", "expected": True}),
])
def test_reject_invalid_specs(model, values):
    with pytest.raises(ValidationError):
        model(**values)


def test_reject_duplicate_profiles_and_missing_tabs():
    data = scenario().model_dump()
    data["profiles"] *= 2
    with pytest.raises(ValidationError):
        BrowserScenario(**data)
    data = scenario().model_dump()
    data["steps"] = [{"action": "switch_tab", "tab": "unknown"}]
    with pytest.raises(ValidationError):
        BrowserScenario(**data)


@pytest.mark.parametrize("command", ["simulate", "run", "ci"])
@pytest.mark.parametrize("status,code", [("passed", 0), ("failed", 1), ("inconclusive", 1)])
def test_cli_gates_simulations(tmp_path, monkeypatch, command, status, code):
    from mallory import simulation

    cfg = Config(target=TargetConfig(compose="", service="", port=1), scenarios=[scenario()])
    cfg.report.out_dir = str(tmp_path)
    cfg.run.agents = []

    @contextmanager
    def target(*args):
        yield SimpleNamespace(base_url="http://localhost")

    result = SimpleNamespace(name="checkout", profile="normal", status=status, reason="",
                             artifacts=str(tmp_path))
    monkeypatch.setattr(cli, "load_config", lambda *args: cfg)
    monkeypatch.setattr(cli, "_load_or_default", lambda *args: cfg)
    monkeypatch.setattr(cli, "_target", target)
    monkeypatch.setattr(cli, "_scan", lambda *args: ([], 0))
    monkeypatch.setattr(simulation, "run_simulations", lambda *args: [result])
    args = [command, "--url", "http://localhost"]
    if command == "ci":
        args += ["--no-comment", "--fail-on", "none", "--tests", str(tmp_path / "missing")]
    response = CliRunner().invoke(cli.main, args)
    assert response.exit_code == code, response.output
    filename = "simulation-report.md" if command == "simulate" else "report.md"
    assert "checkout" in (tmp_path / filename).read_text()


def test_simulate_rejects_missing_scenario(monkeypatch):
    cfg = Config(target=TargetConfig(compose="", service="", port=1))
    monkeypatch.setattr(cli, "load_config", lambda *args: cfg)
    result = CliRunner().invoke(cli.main, ["simulate", "--url", "http://localhost"])
    assert result.exit_code != 0
    assert "No matching scenarios" in result.output


def test_replay_validates_manifest_and_uses_explicit_target(tmp_path, monkeypatch):
    import json

    from mallory import simulation

    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps({"version": 1, "base_url": "https://untrusted.example",
                                    "scenario": scenario().model_dump(),
                                    "profile": NetworkProfile(name="retry", effect="abort").model_dump()}))
    captured = []

    def run(scenarios, target, out):
        captured.append((scenarios, target))
        return [SimpleNamespace(name="checkout", profile="retry", status="passed",
                                reason="", artifacts=None)]

    monkeypatch.setattr(simulation, "run_simulations", run)
    result = CliRunner().invoke(cli.main, ["replay-simulation", str(manifest),
                                           "--url", "http://127.0.0.1:5055"])
    assert result.exit_code == 0, result.output
    scenarios, target = captured[0]
    assert target == "http://127.0.0.1:5055"
    assert len(scenarios[0].profiles) == 1 and scenarios[0].profiles[0].effect == "abort"
    manifest.write_text('{"version": 99}')
    result = CliRunner().invoke(cli.main, ["replay-simulation", str(manifest),
                                           "--url", "http://127.0.0.1:5055"])
    assert result.exit_code != 0
    assert len(captured) == 1
