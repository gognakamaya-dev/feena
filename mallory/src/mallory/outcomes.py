"""Positive HTTP journeys, also copied alongside standalone regression tests."""
from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlsplit

import httpx


class OutcomeUnavailable(RuntimeError):
    """The journey could not be exercised, rather than a successful result."""


def _contains(actual, expected) -> bool:
    if isinstance(expected, dict):
        return isinstance(actual, dict) and all(
            key in actual and _contains(actual[key], value) for key, value in expected.items()
        )
    return type(actual) is type(expected) and actual == expected


def _local_path(path: str) -> str:
    parts = urlsplit(path)
    if (not path.startswith("/") or path.startswith("//") or "\\" in path
            or parts.scheme or parts.netloc or parts.fragment
            or any(ord(c) < 32 for c in path)):
        raise OutcomeUnavailable("outcome path is not target-relative")
    return path


def check_outcome(base_url: str, spec: dict, credentials: tuple[str, str] | None) -> None:
    """Assert every step, including a read-back when persistence matters. Never follow redirects."""
    with httpx.Client(base_url=base_url, timeout=10, follow_redirects=False) as client:
        if spec.get("user") is not None:
            if not credentials or not all(credentials):
                raise OutcomeUnavailable("seeded user credentials are missing")
            email, password = credentials
            identity_path = _local_path(spec.get("identity_path", "/api/me"))
            logged_in = False
            for path in ("/api/login", "/login", "/api/auth/login"):
                for encoding in ("json", "data"):
                    client.cookies.clear()
                    response = client.post(path, **{encoding: {"email": email, "password": password}})
                    if 200 <= response.status_code < 400 and client.cookies:
                        identity = client.get(identity_path)
                        try:
                            data = identity.json()
                        except ValueError:
                            data = None
                        if (identity.status_code == 200 and isinstance(data, dict)
                                and data.get("email") == email):
                            logged_in = True
                            break
                if logged_in:
                    break
            if not logged_in:
                raise OutcomeUnavailable("could not verify the seeded user's authenticated identity")

        for index, step in enumerate(spec["steps"], 1):
            path = _local_path(step["path"])
            response = client.request(step["method"], path, json=step.get("json_body"))
            assert response.status_code == step["expected_status"], (
                f"step {index}: expected HTTP {step['expected_status']}, got {response.status_code}"
            )
            try:
                actual = response.json()
            except ValueError:
                raise AssertionError(f"step {index}: expected a JSON response") from None
            assert _contains(actual, step["expected_json"]), (
                f"step {index}: response did not contain the expected JSON fields"
            )


@dataclass
class OutcomeResult:
    name: str
    status: str
    reason: str = ""


def run_outcomes(checks, base_url: str, users) -> list[OutcomeResult]:
    results = []
    for check in checks:
        credentials = None
        if check.user is not None and check.user <= len(users):
            user = users[check.user - 1]
            credentials = (user.email, user.password)
        try:
            check_outcome(base_url, check.model_dump(), credentials)
        except AssertionError as exc:
            results.append(OutcomeResult(check.name, "failed", str(exc)))
        except (OutcomeUnavailable, httpx.HTTPError) as exc:
            reason = str(exc) if isinstance(exc, OutcomeUnavailable) else "target request failed"
            results.append(OutcomeResult(check.name, "inconclusive", reason))
        else:
            results.append(OutcomeResult(check.name, "passed"))
    return results


def render_outcomes(results: list[OutcomeResult]) -> str:
    if not results:
        return ""
    lines = ["### User outcomes", ""]
    for result in results:
        reason = f" — {result.reason}" if result.reason else ""
        lines.append(f"- **{result.status.upper()}** `{result.name}`{reason}")
    return "\n".join(lines)
