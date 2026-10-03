"""Export validated browser scenarios as standalone pytest/Playwright suites."""
import hashlib
from pathlib import Path


def write_browser_tests(scenarios, directory: Path):
    directory.mkdir(parents=True, exist_ok=True)
    source = Path(__file__).parent
    runtime = (source / "simulation.py").read_text().replace(
        "from .outcomes import _contains, _local_path",
        "from _feena_export_support import _contains, _local_path").replace(
        "from .evidence import BrowserEvidence", "from _feena_evidence import BrowserEvidence")
    (directory / "_feena_browser.py").write_text(runtime)
    (directory / "_feena_evidence.py").write_text((source / "evidence.py").read_text())
    (directory / "_feena_export_support.py").write_text((source / "export_support.py").read_text())
    (directory / "conftest.py").write_text(
        'import sys, pathlib\nsys.path.insert(0, str(pathlib.Path(__file__).parent))\n')
    written = []
    for scenario in scenarios:
        for profile in scenario.profiles:
            fingerprint = hashlib.sha256(f"{scenario.name}/{profile.name}".encode()).hexdigest()[:12]
            path = directory / f"test_browser_{fingerprint}.py"
            path.write_text(f'''"""Generated Playwright journey. Reset/seed disposable data before running.
Install: pip install pytest playwright; playwright install chromium
Run: FEENA_BASE_URL=http://localhost:3000 pytest {path.name}
Generated export; its execution status is established by running pytest.
"""
from _feena_browser import _run_profile
from _feena_export_support import base_url, spec


def test_browser_{fingerprint}(tmp_path):
    scenario = spec({scenario.model_dump(mode="json")!r})
    profile = spec({profile.model_dump(mode="json")!r})
    result = _run_profile(scenario, profile, base_url(), tmp_path / "evidence")
    assert result.status == "passed", f"{{result.status}}: {{result.reason}} ({{result.artifacts}})"
''')
            written.append(path)
    return written
