"""Live browser coverage for the resilient checkout example."""
from __future__ import annotations

import importlib.util
import json
import threading
from pathlib import Path

import pytest
from werkzeug.serving import make_server

from feena.config import load_config
from feena.simulation import run_simulations
from feena.simulation_config import BrowserScenario

EXAMPLE = Path(__file__).parents[1] / "examples" / "resilient-checkout"


@pytest.fixture(scope="module")
def checkout_server():
    spec = importlib.util.spec_from_file_location("resilient_checkout", EXAMPLE / "app.py")
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    server = make_server("127.0.0.1", 0, module.app, threaded=True)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_port}", module
    server.shutdown()
    thread.join(timeout=3)


def test_checkout_scenarios_run_in_real_browser(checkout_server, tmp_path):
    base_url, module = checkout_server
    module.ORDERS.clear()
    config = load_config(EXAMPLE / "feena.yaml")
    assert config.target.model_dump() == {
        "compose": "", "service": "web", "port": 5055,
        "healthcheck": "/api/health", "boot_timeout": 120,
    }
    assert config.run.agents == []
    scenarios = config.scenarios

    results = run_simulations(scenarios, base_url, tmp_path / "artifacts")
    by_profile = {(result.name, result.profile): result for result in results}
    expected_passes = {
        ("retry-checkout", profile)
        for profile in ("normal", "slow-response", "aborted-request", "lost-response")
    }
    failures = {
        key: (by_profile[key].status, by_profile[key].reason)
        for key in expected_passes
        if by_profile[key].status != "passed"
    }
    assert not failures, failures
    broken = by_profile[("broken-idempotency", "lost-response")]
    assert broken.status == "failed"
    assert "assertion" in broken.reason
    assert any(event.get("event") == "fault_applied" for event in json.loads(
        (broken.artifacts / "actions.json").read_text()
    ))
    assert by_profile[("offline-recovery", "normal")].status == "passed"
    assert all(result.artifacts is not None for result in results)
    assert sorted(len(orders) for orders in module.ORDERS.values()) == [1, 1, 1, 1, 1, 2]
    delayed = by_profile[("retry-checkout", "slow-response")]
    manifest = json.loads((delayed.artifacts / "manifest.json").read_text())
    action_log = json.loads((delayed.artifacts / "actions.json").read_text())
    assert manifest["fault_applied"] is True
    assert any(event.get("event") == "fault_applied" for event in action_log)
    assert all("elapsed_ms" in event for event in action_log)


def test_tabs_share_context_session_across_navigation(checkout_server, tmp_path):
    base_url, module = checkout_server
    module.ORDERS.clear()
    scenario = BrowserScenario.model_validate({
        "name": "active-tab",
        "goal": "Continue actions and assertions in the newly opened tab.",
        "steps": [
            {"action": "goto", "target": "/"},
            {"action": "new_tab", "tab": "secondary"},
            {"action": "goto", "target": "/"},
            {"action": "click", "target": "#checkout"},
            {"action": "wait", "wait_ms": 700},
            {"action": "switch_tab", "tab": "main"},
            {"action": "goto", "target": "/?page=one"},
            {"action": "goto", "target": "/?page=two"},
            {"action": "back"},
            {"action": "reload"},
        ],
        "assertions": [
            {"kind": "text", "target": "#status", "expected": "Ready to check out."},
            {"kind": "json", "target": "/api/state", "expected": {"orders": 1}},
        ],
    })
    result = run_simulations([scenario], base_url, tmp_path / "artifacts")[0]
    assert result.status == "passed", result.reason
    assert sorted(len(orders) for orders in module.ORDERS.values()) == [1]


def test_untriggered_fault_is_inconclusive_not_a_pass(checkout_server, tmp_path):
    base_url, _ = checkout_server
    scenario = BrowserScenario.model_validate({
        "name": "untriggered-fault-check",
        "goal": "Report a fault profile as inconclusive when no matching request occurs.",
        "steps": [{"action": "goto", "target": "/"}],
        "assertions": [{"kind": "text", "target": "#status", "expected": "Ready to check out."}],
        "profiles": [
            {"name": "unmatched", "effect": "abort", "path": "/never-requested"}
        ],
    })
    result = run_simulations([scenario], base_url, tmp_path / "artifacts")[0]
    assert result.status == "inconclusive"
    assert "not triggered" in result.reason


def test_simulation_config_rejects_invalid_scenario():
    with pytest.raises(ValueError):
        BrowserScenario.model_validate({
            "name": "invalid",
            "goal": "invalid target path",
            "steps": [{"action": "goto", "target": "https://example.com"}],
            "assertions": [{"kind": "json", "target": "/api/state", "expected": {"orders": 0}}],
        })
