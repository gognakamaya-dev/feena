"""Everything the GitHub Action needs beyond a plain scan.

- **Baseline.** A committed ``mallory.baseline.json`` of accepted/known findings, so CI fails only
  on NEW problems. Without it a team's first run fails forever on pre-existing issues and the check
  gets deleted.
- **Regression tests.** Runs the committed, generated tests against the same running app and
  reports which ones went red (results parsed from JUnit XML, not scraped from text).
- **One sticky comment.** Updated in place on every push instead of a new comment each time,
  plus a job-summary fallback for fork PRs where the token is read-only.
- **Exit code.** Non-zero on a new finding at or above ``--fail-on``, or on any failing
  regression test.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import httpx

from .findings import Finding, Severity

MARKER = "<!-- mallory-report -->"
SEVERITY_RANK = {"info": 0, "low": 1, "medium": 2, "high": 3, "critical": 4}
FAIL_ON_CHOICES = ["critical", "high", "medium", "low", "none"]
MAX_COMMENT = 60000   # GitHub caps a comment at 65,536 characters


# ---------------------------------------------------------------- baseline

def load_baseline(path: Path) -> dict[str, dict]:
    """fingerprint -> {severity, title}. A missing file is an empty baseline."""
    if not path.exists():
        return {}
    data = json.loads(path.read_text())
    return {e["fingerprint"]: e for e in data.get("findings", [])}


def write_baseline(confirmed: list[Finding], path: Path) -> int:
    entries = [{"fingerprint": f.fingerprint, "severity": f.severity.value, "title": f.title}
               for f in sorted(confirmed, key=lambda f: (-SEVERITY_RANK[f.severity.value], f.title))]
    path.write_text(json.dumps({
        "version": 1,
        "note": ("Known/accepted findings. `mallory ci` fails only on findings NOT listed here. "
                 "Regenerate with `mallory baseline` after fixing things to prune it."),
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "findings": entries,
    }, indent=2) + "\n")
    return len(entries)


def split_by_baseline(confirmed: list[Finding], baseline: dict[str, dict]):
    """-> (new findings, known findings, baselined entries that no longer reproduce)."""
    current = {f.fingerprint for f in confirmed}
    new = [f for f in confirmed if f.fingerprint not in baseline]
    known = [f for f in confirmed if f.fingerprint in baseline]
    fixed = [e for fp, e in baseline.items() if fp not in current]
    return new, known, fixed


# ---------------------------------------------------------------- regression tests

@dataclass
class RegressionResult:
    ran: bool = False
    passed: int = 0
    failed: int = 0
    skipped: int = 0
    failures: list[tuple[str, str]] = field(default_factory=list)   # (finding title, test file)
    note: str = ""


def _title_of(tests_dir: Path, module: str) -> str:
    try:
        text = (tests_dir / f"{module}.py").read_text()
        m = re.search(r"^Finding\s*:\s*(.+)$", text, re.MULTILINE)
        if m:
            return m.group(1).strip()
    except OSError:
        pass
    return module


def run_regression(tests_dir: Path, base_url: str, users: list) -> RegressionResult:
    """Run the committed generated tests against the running app."""
    if not tests_dir.exists() or not list(tests_dir.glob("test_*.py")):
        return RegressionResult(ran=False, note=f"no committed regression tests in `{tests_dir}` yet")
    env = os.environ.copy()
    for secret in ("GITHUB_TOKEN", "ANTHROPIC_API_KEY"):   # tests never need these
        env.pop(secret, None)
    env["MALLORY_BASE_URL"] = base_url
    for i, u in enumerate(users[:2], 1):
        env[f"MALLORY_USER{i}_EMAIL"] = u.email
        env[f"MALLORY_USER{i}_PASSWORD"] = u.password
    with tempfile.TemporaryDirectory() as tmp:
        junit = Path(tmp) / "junit.xml"
        p = subprocess.run(
            [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider",
             f"--junitxml={junit}", str(tests_dir)],
            env=env, capture_output=True, text=True)
        if not junit.exists():
            return RegressionResult(ran=False, note="pytest produced no results: "
                                    + (p.stdout + p.stderr).strip()[-300:])
        root = ET.parse(junit).getroot()
    res = RegressionResult(ran=True)
    for tc in root.iter("testcase"):
        module = (tc.get("classname") or "").split(".")[-1] or (tc.get("name") or "")
        if tc.find("failure") is not None or tc.find("error") is not None:
            res.failed += 1
            res.failures.append((_title_of(tests_dir, module), f"{module}.py"))
        elif tc.find("skipped") is not None:
            res.skipped += 1
        else:
            res.passed += 1
    return res


# ---------------------------------------------------------------- verdict + rendering

@dataclass
class Verdict:
    failed: bool
    new_blocking: int
    reasons: list[str]


def decide(new: list[Finding], regression: RegressionResult, fail_on: str) -> Verdict:
    reasons: list[str] = []
    blocking = 0
    if fail_on != "none":
        threshold = SEVERITY_RANK[fail_on]
        blocking = sum(1 for f in new if SEVERITY_RANK[f.severity.value] >= threshold)
        if blocking:
            reasons.append(f"{blocking} new finding(s) at or above `{fail_on}`")
    if regression.ran and regression.failed:
        reasons.append(f"{regression.failed} regression test(s) failing")
    return Verdict(failed=bool(reasons), new_blocking=blocking, reasons=reasons)


_BADGE = {"critical": "🔴 CRITICAL", "high": "🟠 HIGH", "medium": "🟡 MEDIUM",
          "low": "🔵 LOW", "info": "⚪ INFO"}


def render_comment(new: list[Finding], known: list[Finding], fixed: list[dict],
                   regression: RegressionResult, verdict: Verdict, dropped: int,
                   fail_on: str, has_baseline: bool) -> str:
    from .reporter import render_findings_section

    icon = "❌" if verdict.failed else "✅"
    head = ("**Failing:** " + "; ".join(verdict.reasons)) if verdict.failed else \
           "**No new problems.** Nothing new at or above the failure threshold."
    lines = [MARKER, f"## {icon} Mallory", "", head, ""]

    # regression tests
    lines.append("### Regression tests")
    if not regression.ran:
        lines.append(f"_{regression.note}._ Commit generated tests (`mallory adopt --all`) so fixed "
                     "bugs stay fixed.")
    else:
        bits = [f"✅ {regression.passed} passing"]
        if regression.failed:
            bits.append(f"❌ {regression.failed} failing")
        if regression.skipped:
            bits.append(f"⚠️ {regression.skipped} skipped")
        lines.append(" · ".join(bits))
        for title, fname in regression.failures:
            lines.append(f"- ❌ **{title}** is back (`{fname}`)")
        if regression.skipped:
            lines.append("\n_A skipped regression test guards nothing. Usually a missing test "
                         "login or browser; see the job log._")
    lines.append("")

    # new findings
    lines.append("### New findings")
    if new:
        lines.append(render_findings_section(new))
    else:
        lines.append("None. 🎉")
    lines.append("")

    # context
    notes = []
    if known:
        notes.append(f"{len(known)} known finding(s) hidden by the baseline")
    if fixed:
        notes.append(f"{len(fixed)} baselined finding(s) were not observed in this scan; "
                     "verify coverage and fixes before pruning with `mallory baseline`")
    if dropped:
        notes.append(f"{dropped} candidate(s) not confirmed; inspect `verification.json` "
                     "for inconclusive replays")
    if not has_baseline and new and not regression.ran:
        # First-adoption hint only. Once regression tests exist, a finding is more likely a bug
        # that came back than a pre-existing issue, so never nudge anyone to baseline it away.
        notes.append("first run? `mallory baseline` accepts today's findings so CI fails only on "
                     "new ones. Fix real bugs instead where you can")
    if notes:
        lines.append("<sub>" + " · ".join(notes) + f" · failing threshold: `{fail_on}`</sub>")

    body = "\n".join(lines)
    if len(body) > MAX_COMMENT:
        body = body[:MAX_COMMENT] + "\n\n_…truncated. Full report is in the workflow artifact._"
    return body


# ---------------------------------------------------------------- GitHub plumbing

def write_step_summary(body: str) -> bool:
    path = os.environ.get("GITHUB_STEP_SUMMARY")
    if not path:
        return False
    with open(path, "a") as fh:
        fh.write(body + "\n")
    return True


def write_outputs(new_findings: int, regression_failed: int, failed: bool) -> None:
    path = os.environ.get("GITHUB_OUTPUT")
    if not path:
        return
    with open(path, "a") as fh:
        fh.write(f"new-findings={new_findings}\n"
                 f"regression-failures={regression_failed}\n"
                 f"failed={'true' if failed else 'false'}\n")


def pr_number() -> int | None:
    event_path = os.environ.get("GITHUB_EVENT_PATH")
    if not event_path or not Path(event_path).exists():
        return None
    try:
        event = json.loads(Path(event_path).read_text())
    except (OSError, ValueError):
        return None
    return (event.get("pull_request") or {}).get("number") or event.get("number")


def upsert_pr_comment(body: str) -> str:
    """Create the Mallory comment, or update it in place if one already exists.

    Returns a short status string. Never raises: fork PRs get a read-only token, and a failed
    comment must not fail the build (the job summary carries the same content)."""
    token = os.environ.get("GITHUB_TOKEN")
    repo = os.environ.get("GITHUB_REPOSITORY")
    pr = pr_number()
    if not (token and repo and pr):
        return "skipped (not a pull_request run, or no GITHUB_TOKEN)"
    api = os.environ.get("GITHUB_API_URL", "https://api.github.com").rstrip("/")
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json",
               "X-GitHub-Api-Version": "2022-11-28"}
    try:
        existing = None
        for page in range(1, 6):
            r = httpx.get(f"{api}/repos/{repo}/issues/{pr}/comments",
                          params={"per_page": 100, "page": page}, headers=headers, timeout=15.0)
            if r.status_code >= 300:
                return f"skipped (could not list comments: HTTP {r.status_code})"
            batch = r.json()
            existing = next((c for c in batch if MARKER in (c.get("body") or "")), None)
            if existing or len(batch) < 100:
                break
        if existing:
            r = httpx.patch(f"{api}/repos/{repo}/issues/comments/{existing['id']}",
                            headers=headers, json={"body": body}, timeout=15.0)
            verb = "updated"
        else:
            r = httpx.post(f"{api}/repos/{repo}/issues/{pr}/comments",
                           headers=headers, json={"body": body}, timeout=15.0)
            verb = "created"
        if r.status_code >= 300:
            return (f"skipped (HTTP {r.status_code}; fork PRs have a read-only token, "
                    "see the job summary instead)")
        return verb
    except httpx.HTTPError as e:
        return f"skipped ({type(e).__name__})"
