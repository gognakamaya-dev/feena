"""Run, report, and export cross-service integration scenarios."""
import hashlib
import json
import uuid
from pathlib import Path

from .integration_runtime import run_integration


def write_integration_tests(scenarios, directory):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    source = Path(__file__).parent
    (directory / "_feena_integration.py").write_text(
        (source / "integration_runtime.py").read_text().replace(
            "from .export_support", "from _feena_export_support"))
    (directory / "_feena_export_support.py").write_text((source / "export_support.py").read_text())
    (directory / "conftest.py").write_text(
        'import sys, pathlib\nsys.path.insert(0, str(pathlib.Path(__file__).parent))\n')
    paths = []
    for scenario in scenarios:
        fp = hashlib.sha256(scenario.name.encode()).hexdigest()[:12]
        path = directory / f"test_integration_{fp}.py"
        path.write_text(f'''"""Generated integration scenario; requires disposable service fixtures.
Install pytest and httpx. Supply FEENA_SERVICE_<NAME>_URL for each service.
"""
import json
from _feena_integration import run_integration


def test_integration_{fp}(tmp_path):
    result = run_integration({scenario.model_dump(mode="json")!r})
    evidence = tmp_path / "integration.json"
    evidence.write_text(json.dumps(result, indent=2))
    assert result["status"] == "passed", f"{{result['reason']}} ({{evidence}})"
''')
        paths.append(path)
    return paths


def run_integrations(scenarios, out_dir):
    results = []
    directory = Path(out_dir) / uuid.uuid4().hex
    directory.mkdir(parents=True, exist_ok=True)
    for scenario in scenarios:
        result = run_integration(scenario.model_dump(mode="json"))
        path = directory / f"{scenario.name}.json"
        result["artifact"] = str(path)
        result["scenario"] = scenario.model_dump(mode="json")
        path.write_text(json.dumps(result, indent=2) + "\n")
        results.append(result)
    return results


def render_integrations(results):
    lines = ["### Service integrations", ""]
    for result in results:
        lines.append(f"- **{result['status'].upper()}** `{result['name']}`: "
                     f"{result['reason']} ([evidence]({result['artifact']}))")
    return "\n".join(lines)
