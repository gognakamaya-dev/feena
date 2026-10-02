"""Portable multi-service runner. This file is copied into exported test suites."""
# ruff: noqa: BLE001 - setup/transport failures must stay inconclusive and cleanup must run
import os
import time
import uuid
from contextlib import ExitStack

import httpx

from .export_support import _contains, _local_path, local_url


def run_integration(scenario, environment=None):
    environment = os.environ if environment is None else environment
    run_id = uuid.uuid4().hex
    result = {"name": scenario["name"], "run_id": run_id, "status": "inconclusive",
              "reason": "", "events": []}

    def expand(value):
        if isinstance(value, str):
            return value.replace("${run_id}", run_id)
        if isinstance(value, dict):
            return {k: expand(v) for k, v in value.items()}
        if isinstance(value, list):
            return [expand(v) for v in value]
        return value

    phases = {phase: scenario.get(phase, []) for phase in ("setup", "steps", "cleanup")}
    services = sorted({s["service"] for steps in phases.values() for s in steps})
    try:
        # Resolve all targets before any mutation. Never infer endpoints from observed responses.
        targets = {s: local_url(environment[f"FEENA_SERVICE_{s.upper()}_URL"]) for s in services}
        with ExitStack() as stack:
            clients = {s: stack.enter_context(httpx.Client(base_url=url, timeout=5,
                        follow_redirects=False, trust_env=False)) for s, url in targets.items()}

            def execute(step, phase, index):
                step = expand(step)
                path = _local_path(step["path"])
                deadline = time.monotonic() + step.get("poll_seconds", 0)
                attempts = 0
                while True:
                    attempts += 1
                    try:
                        response = clients[step["service"]].request(step.get("method", "GET"), path,
                                                                   json=step.get("json_body"))
                    except httpx.HTTPError as exc:
                        result["events"].append({"phase": phase, "step": index,
                            "service": step["service"], "path": path,
                            "status": "inconclusive", "error_type": type(exc).__name__})
                        raise
                    try:
                        actual = response.json()
                    except ValueError:
                        actual = None
                    matched = (response.status_code == step.get("expected_status", 200)
                               and _contains(actual, step["expected_json"]))
                    if matched or time.monotonic() >= deadline:
                        break
                    time.sleep(min(0.1, max(0, deadline - time.monotonic())))
                result["events"].append({"phase": phase, "step": index, "service": step["service"],
                    "method": step.get("method", "GET"), "path": path, "attempts": attempts,
                    "expected_status": step.get("expected_status", 200),
                    "actual_status": response.status_code, "expected": step["expected_json"],
                    "actual": actual, "status": "passed" if matched else "failed"})
                if not matched:
                    raise AssertionError(f"{phase} step {index} ({step['service']}) did not match")

            try:
                for phase in ("setup", "steps"):
                    for index, step in enumerate(phases[phase], 1):
                        execute(step, phase, index)
                result["status"] = "passed"
            except AssertionError as exc:
                result["status"] = "failed" if phase == "steps" else "inconclusive"
                result["reason"] = str(exc)
            except Exception as exc:
                result["reason"] = f"Request/setup unavailable: {type(exc).__name__}"
            finally:
                # Attempt every cleanup even after an earlier cleanup fails.
                for index, step in enumerate(phases["cleanup"], 1):
                    try:
                        execute(step, "cleanup", index)
                    except Exception as exc:
                        if result["status"] == "passed":
                            result["status"] = "inconclusive"
                        result["reason"] += f"; cleanup {index} failed ({type(exc).__name__})"
    except Exception as exc:
        result["reason"] = f"Service configuration unavailable: {type(exc).__name__}"
    return result
