"""What a finding is, and the rule that no finding ships without a reproduction.

A Finding is only allowed to reach the report if it has been *confirmed*: replayed from its
recorded steps and observed to happen again. This is the whole trust story of the product, so
verification lives here, close to the data model, not in the reporter.
"""
from __future__ import annotations

import hashlib
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum
from typing import Protocol


class Severity(str, Enum):
    INFO = "info"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class Kind(str, Enum):
    BROKEN_FLOW = "broken_flow"          # regular agent: a core flow fails end to end
    STATE_BUG = "state_bug"              # clumsy agent: races, data loss, validation gaps
    ACCESS_CONTROL = "access_control"    # hostile: IDOR / missing authz
    MISSING_AUTH = "missing_auth"        # hostile: protected route served without a session
    INPUT_HANDLING = "input_handling"    # hostile: input reflected unescaped
    SQL_INJECTION = "sql_injection"      # hostile: input interpreted as SQL
    STORED_XSS = "stored_xss"            # hostile: input persists unescaped
    WEAK_HEADERS = "weak_headers"        # hostile: missing security headers


@dataclass
class Step:
    """One reproducible action. ``action`` is a Playwright-ish verb the replayer understands."""
    action: str            # e.g. "goto" | "click" | "fill" | "http_get"
    target: str = ""       # selector, url, or path
    value: str = ""        # text to type, etc.
    note: str = ""


@dataclass
class Finding:
    kind: Kind
    severity: Severity
    title: str
    detail: str
    agent: str
    steps: list[Step] = field(default_factory=list)
    evidence: dict = field(default_factory=dict)   # e.g. {"screenshot": path, "trace": path}
    confirmed: bool = False
    verification_status: str = "pending"
    verification_reason: str = ""
    # Machine-readable reproduction, compiled into an executable regression test by regress.py.
    # e.g. {"type": "idor", "path": "/api/tasks/2"}. Empty => no automated regression test.
    repro: dict = field(default_factory=dict)

    @property
    def fingerprint(self) -> str:
        """Stable id for dedup across agents and runs."""
        basis = f"{self.kind.value}|{self.title}|" + "|".join(
            f"{s.action}:{s.target}" for s in self.steps
        )
        return hashlib.sha256(basis.encode()).hexdigest()[:12]


def dedup(findings: list[Finding]) -> list[Finding]:
    seen: dict[str, Finding] = {}
    for f in findings:
        seen.setdefault(f.fingerprint, f)
    return list(seen.values())


class ReplayResult(Protocol):
    status: object
    reason: str


Replayer = Callable[[Finding], bool | ReplayResult]


def confirm(findings: list[Finding], replayer: Replayer) -> tuple[list[Finding], list[Finding]]:
    """Split findings into (confirmed, dropped). Only confirmed ones are allowed to ship.

    Only a reproduced result is reportable; not-reproduced and inconclusive results are dropped
    but retain distinct status and reason fields on the finding.
    """
    confirmed, dropped = [], []
    for f in findings:
        failure_reason = ""
        try:
            result = replayer(f)
        except Exception as exc:  # noqa: BLE001 - replay failures must not confirm findings
            result = None
            failure_reason = f"Replay raised {type(exc).__name__}."
        if result is not None and hasattr(result, "status") and hasattr(result, "reason"):
            f.verification_status = getattr(result.status, "value", str(result.status))
            f.verification_reason = result.reason
            ok = f.verification_status == "reproduced"
        elif result is not None:
            # Preserve the longstanding bool-replayer interface used by callers and tests.
            ok = bool(result)
            f.verification_status = "reproduced" if ok else "not_reproduced"
            f.verification_reason = "Custom replayer reproduced the finding." if ok else \
                "Custom replayer did not reproduce the finding."
        else:
            ok = False
            f.verification_status = "inconclusive"
            f.verification_reason = failure_reason or "Replayer returned no verification result."
        f.confirmed = ok
        (confirmed if ok else dropped).append(f)
    return confirmed, dropped
