"""Bounded subprocess entry point used by the MCP service."""
import json
import sys
from pathlib import Path

from .simulation import run_simulations
from .simulation_config import BrowserScenario


def main():
    folder, target = Path(sys.argv[1]), sys.argv[2]
    scenario = BrowserScenario.model_validate_json((folder / "scenario.json").read_text())
    results = run_simulations([scenario], target, folder / "evidence")
    (folder / "results.json").write_text(json.dumps([
        {"scenario": r.name, "profile": r.profile, "status": r.status, "reason": r.reason}
        for r in results
    ]))


if __name__ == "__main__":
    main()
