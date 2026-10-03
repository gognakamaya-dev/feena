"""Turn confirmed findings into a report and a regression test per finding.

Local runs get a markdown file; CI runs post the same body as a PR comment. Every confirmed
finding also emits a Playwright test stub built from its steps, so a fix can be locked in.
"""
from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

from .findings import Finding, Severity

_SEV_ORDER = {
    Severity.CRITICAL: 0,
    Severity.HIGH: 1,
    Severity.MEDIUM: 2,
    Severity.LOW: 3,
    Severity.INFO: 4,
}
_SEV_BADGE = {
    Severity.CRITICAL: "🔴 CRITICAL",
    Severity.HIGH: "🟠 HIGH",
    Severity.MEDIUM: "🟡 MEDIUM",
    Severity.LOW: "🔵 LOW",
    Severity.INFO: "⚪ INFO",
}


def _finding_body(f: Finding) -> list[str]:
    lines = [f"*Found by the `{f.agent}` agent.*", "", f.detail, "", "**Steps to reproduce:**"]
    for s in f.steps:
        bit = f"- `{s.action}` {s.target}".rstrip()
        if s.value:
            bit += f" = `{s.value}`"
        if s.note:
            bit += f"  _( {s.note} )_"
        lines.append(bit)
    if f.evidence.get("screenshot"):
        lines.append(f"\n_Screenshot:_ `{f.evidence['screenshot']}`")
    label = ("Assertion verified" if f.confirmed and f.verification_method == "assertion_replay"
             else "Replay confirmed" if f.confirmed else "Needs review")
    lines += ["", f"**Verification: {label}.** {f.verification_reason}"]
    if len(f.observed_by) > 1:
        lines.append(f"Observed by: {', '.join(f.observed_by)} (corroboration, not independent verification).")
    lines += ["", "**Trust package:**"]
    for key in ("console", "network", "dom", "trace"):
        value = f.evidence.get(key)
        lines.append(f"- {key}: [{key}]({value})" if value else f"- {key}: unavailable for this check")
    test = (f"`tests/test_{f.fingerprint}.py`" if _automated(f)
            else "none (no machine-readable reproduction; verify manually)")
    lines.append(f"\n_Fingerprint:_ `{f.fingerprint}`  ·  _Regression test:_ {test}")
    if f.evidence.get("trust_package"):
        lines.append(f"[Machine-readable trust package]({f.evidence['trust_package']})")
    return lines


def render_findings_section(findings: list[Finding], collapsible: bool = True) -> str:
    """Just the per-finding blocks (no report header). Collapsible <details> for PR comments."""
    findings = sorted(findings, key=lambda f: _SEV_ORDER[f.severity])
    lines: list[str] = []
    for i, f in enumerate(findings, 1):
        if collapsible:
            lines += [f"<details><summary>{_SEV_BADGE[f.severity]} — {f.title}</summary>", ""]
            lines += _finding_body(f)
            lines += ["", "</details>", ""]
        else:
            lines += [f"### {i}. {_SEV_BADGE[f.severity]} — {f.title}", ""] + _finding_body(f) + [""]
    return "\n".join(lines)


def render_markdown(confirmed: list[Finding], dropped_count: int) -> str:
    confirmed = sorted(confirmed, key=lambda f: _SEV_ORDER[f.severity])
    lines = ["## Feena report", ""]
    if not confirmed:
        lines.append("No confirmed findings.")
        if dropped_count:
            lines.append(f"\n_{dropped_count} candidate(s) were not confirmed. "
                         "This does not prove the app is bug-free; see `verification.json` "
                         "for replay statuses and unavailable checks._")
        return "\n".join(lines)

    lines.append(f"**{len(confirmed)} confirmed finding(s)** — each reproduced before reporting.")
    if dropped_count:
        lines.append(f"_{dropped_count} candidate(s) not confirmed; see `verification.json` "
                     "for replay statuses._")
    lines.append("")
    lines.append(render_findings_section(confirmed, collapsible=False))
    if any(_automated(f) for f in confirmed):
        lines += ["---",
                  ("Commit the generated tests and run them after each fix: "
                  "`feena regress --base-url http://localhost:3000` "
                  "(or `FEENA_BASE_URL=... pytest .feena/tests`). "
                  "Each passes when its bug is fixed and fails if it comes back.")]
    return "\n".join(lines)


def _automated(f: Finding) -> bool:
    from .regress import render_test
    return render_test(f) is not None


def write_report(confirmed: list[Finding], dropped_count: int, out_dir: Path, outcomes=()) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    from .regress import write_tests
    write_tests(confirmed, out_dir / "tests", outcomes)
    for finding in confirmed:
        path = out_dir / "evidence" / f"{finding.fingerprint}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        finding.evidence["trust_package"] = str(path)
        path.write_text(json.dumps({
            "version": 1, "finding": asdict(finding),
            "setup": "Restore disposable seeded data and configure the same test accounts before replay.",
            "test": f"tests/test_{finding.fingerprint}.py" if _automated(finding) else None,
            "run": f"FEENA_BASE_URL=http://localhost:3000 pytest tests/test_{finding.fingerprint}.py"
                   if _automated(finding) else None,
            "export_status": "generated; execution against your reset target is required",
            "unavailable_evidence": [key for key in ("console", "network", "dom", "trace", "screenshot")
                                     if not finding.evidence.get(key)],
        }, indent=2) + "\n")
    body = render_markdown(confirmed, dropped_count)
    report_path = out_dir / "report.md"
    report_path.write_text(body)
    return report_path
