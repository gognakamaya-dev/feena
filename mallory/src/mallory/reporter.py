"""Turn confirmed findings into a report and a regression test per finding.

Local runs get a markdown file; CI runs post the same body as a PR comment. Every confirmed
finding also emits a Playwright test stub built from its steps, so a fix can be locked in.
"""
from __future__ import annotations

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
    test = (f"`tests/test_{f.fingerprint}.py`" if _automated(f)
            else "none (no machine-readable reproduction; verify manually)")
    lines.append(f"\n_Fingerprint:_ `{f.fingerprint}`  ·  _Regression test:_ {test}")
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
    lines = ["## Mallory report", ""]
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
                  "Commit the generated tests and run them after each fix: "
                  "`mallory regress --base-url http://localhost:3000` "
                  "(or `MALLORY_BASE_URL=... pytest .mallory/tests`). "
                  "Each passes when its bug is fixed and fails if it comes back."]
    return "\n".join(lines)


def _automated(f: Finding) -> bool:
    from .regress import render_test
    return render_test(f) is not None


def write_report(confirmed: list[Finding], dropped_count: int, out_dir: Path, outcomes=()) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    body = render_markdown(confirmed, dropped_count)
    report_path = out_dir / "report.md"
    report_path.write_text(body)
    from .regress import write_tests
    write_tests(confirmed, out_dir / "tests", outcomes)
    return report_path
