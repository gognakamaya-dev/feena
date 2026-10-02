import importlib.util
import json
import os
import subprocess
import sys
import threading
from contextlib import contextmanager
from pathlib import Path

import httpx
import pytest
from click.testing import CliRunner
from werkzeug.serving import make_server

from feena.cli import main
from feena.config import load_config
from feena.integration_config import IntegrationStep
from feena.integration_runtime import run_integration
from feena.integrations import write_integration_tests

EXAMPLE = Path(__file__).parents[1] / "examples" / "service-checkout"


@contextmanager
def serve(app):
    server = make_server("127.0.0.1", 0, app, threaded=True)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        thread.join(timeout=3)


@pytest.fixture
def services():
    spec = importlib.util.spec_from_file_location("service_checkout", EXAMPLE / "app.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    with (serve(module.payment_app()) as payments,
          serve(module.order_app(payments)) as fixed,
          serve(module.order_app(payments, True)) as broken):
        yield {"FEENA_SERVICE_PAYMENTS_URL": payments, "FEENA_SERVICE_ORDERS_URL": fixed}, broken


def test_cross_service_failure_fix_exports_and_cleanup(services, tmp_path):
    environment, broken = services
    scenario = load_config(EXAMPLE / "feena.yaml").integrations[0]
    for target, expected in ((broken, "failed"), (environment["FEENA_SERVICE_ORDERS_URL"], "passed")):
        env = environment | {"FEENA_SERVICE_ORDERS_URL": target}
        result = run_integration(scenario.model_dump(), env)
        assert result["status"] == expected, result
        for service, field in (("ORDERS", "orders"), ("PAYMENTS", "charges")):
            response = httpx.get(f"{env[f'FEENA_SERVICE_{service}_URL']}/state/{result['run_id']}", trust_env=False)
            assert response.json()[field] == 0
        exported = write_integration_tests([scenario], tmp_path)
        process = subprocess.run([sys.executable, "-m", "pytest", "-q", str(exported[0])],
                                 cwd=tmp_path, env=os.environ | env,
                                 capture_output=True, text=True, timeout=30, check=False)
        assert process.returncode == (1 if expected == "failed" else 0), process.stdout + process.stderr
        assert not any("from feena" in p.read_text() for p in tmp_path.glob("*.py"))


def test_missing_service_is_inconclusive():
    scenario = load_config(EXAMPLE / "feena.yaml").integrations[0]
    result = run_integration(scenario.model_dump(), {})
    assert result["status"] == "inconclusive"
    assert not result["events"]


def test_failed_setup_and_cleanup_are_inconclusive_and_cleanup_continues(services):
    environment, _ = services
    from feena.integration_config import IntegrationScenario

    scenario = IntegrationScenario.model_validate({
        "name": "setup-failure", "goal": "Do not pass when fixtures cannot be established",
        "setup": [{"service": "orders", "path": "/state/${run_id}", "expected_json": {"orders": 1}}],
        "steps": [{"service": "orders", "path": "/state/${run_id}", "expected_json": {"orders": 0}}],
        "cleanup": [
            {"service": "orders", "path": "/state/${run_id}", "expected_json": {"orders": 1}},
            {"service": "payments", "path": "/state/${run_id}", "expected_json": {"charges": 0}},
        ],
    })
    result = run_integration(scenario.model_dump(), environment)
    assert result["status"] == "inconclusive"
    assert [e["phase"] for e in result["events"]] == ["setup", "cleanup", "cleanup"]
    assert result["events"][-1]["status"] == "passed"
    scenario.setup = []
    result = run_integration(scenario.model_dump(), environment)
    assert result["status"] == "inconclusive"
    assert result["events"][0]["status"] == "passed"


@pytest.mark.parametrize("command", ["run", "ci"])
@pytest.mark.parametrize("status,code", [("passed", 0), ("failed", 1), ("inconclusive", 1)])
def test_integration_results_gate_existing_commands(command, status, code, monkeypatch, tmp_path):
    from types import SimpleNamespace

    from feena import cli
    config = load_config(EXAMPLE / "feena.yaml")
    config.report.out_dir = str(tmp_path)

    @contextmanager
    def target(*args):
        yield SimpleNamespace(base_url="http://localhost")

    monkeypatch.setattr(cli, "_load_or_default", lambda *args: config)
    monkeypatch.setattr(cli, "_target", target)
    monkeypatch.setattr(cli, "_scan", lambda *args: ([], 0))
    monkeypatch.setattr(cli, "_integrations", lambda *args: [
        {"name": "checkout", "status": status, "reason": "", "artifact": "evidence.json"}])
    args = [command, "--url", "http://localhost"]
    if command == "ci":
        args += ["--no-comment", "--fail-on", "none", "--tests", str(tmp_path / "missing")]
    result = CliRunner().invoke(main, args)
    assert result.exit_code == code, result.output
    assert "Service integrations" in (tmp_path / "report.md").read_text()


@pytest.mark.parametrize("values", [
    {"path": "https://example.com"}, {"path": "//example.com"},
    {"path": "/", "method": "POST", "poll_seconds": 1},
    {"path": "/", "expected_json": {}},
])
def test_invalid_integration_steps(values):
    with pytest.raises(ValueError):
        IntegrationStep(**({"service": "orders", "expected_json": {"ok": True}} | values))


def test_integrate_cli_writes_report_and_exports(services, tmp_path, monkeypatch):
    env, broken = services
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    config = load_config(EXAMPLE / "feena.yaml")
    config.report.out_dir = str(tmp_path)
    config_path = tmp_path / "config.json"
    config_path.write_text(config.model_dump_json())
    response = CliRunner().invoke(main, ["integrate", "--config", str(config_path)])
    assert response.exit_code == 0, response.output
    assert "PASSED" in (tmp_path / "integration-report.md").read_text()
    assert list((tmp_path / "tests").glob("test_integration_*.py"))
    monkeypatch.setenv("FEENA_SERVICE_ORDERS_URL", broken)
    response = CliRunner().invoke(main, ["integrate", "--config", str(config_path)])
    assert response.exit_code == 1, response.output
    artifacts = list((tmp_path / "integrations").glob("*/*.json"))
    assert {json.loads(p.read_text())["status"] for p in artifacts} == {"passed", "failed"}
