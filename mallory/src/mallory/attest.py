"""Signed run attestations: the auditor-ready record that a release was tested.

An attestation binds together *what was tested* (repo, commit), *when*, *which agents ran*, and
*what was found* (a hash of every confirmed finding), and signs it with an Ed25519 key. Anyone
with the public key can verify it later with ``mallory verify``; changing a single byte of the
record breaks the signature.

This is the enterprise artifact from the business model: engineers adopt the runner for free,
and the compliance team pays for a verifiable, per-release record they can hand to an auditor.

Control mappings below are *suggested* references to help a reviewer file the evidence. They
are not a certification, and whether a given record satisfies a control is the auditor's call.
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)

from .findings import Finding, Kind, Severity

SCHEMA = "mallory.attestation/v1"

# Finding kind -> OWASP Top 10 (2021) category. Factual mapping of the weakness class.
OWASP = {
    Kind.ACCESS_CONTROL: "A01:2021 Broken Access Control",
    Kind.MISSING_AUTH: "A01:2021 Broken Access Control",
    Kind.INPUT_HANDLING: "A03:2021 Injection",
    Kind.SQL_INJECTION: "A03:2021 Injection",
    Kind.STORED_XSS: "A03:2021 Injection",
    Kind.WEAK_HEADERS: "A05:2021 Security Misconfiguration",
    Kind.BROKEN_FLOW: "n/a (functional)",
    Kind.STATE_BUG: "A04:2021 Insecure Design",
}

# Suggested evidence mapping for the run as a whole. A reviewer decides whether it applies.
SUGGESTED_CONTROLS = [
    ("SOC 2 CC7.1", "Procedures to identify vulnerabilities and configuration weaknesses"),
    ("SOC 2 CC8.1", "Changes are tested before release"),
    ("ISO 27001 A.8.29", "Security testing in development and acceptance"),
]


# ---------- keys ----------

def generate_keypair(out_dir: Path) -> tuple[Path, Path]:
    """Write mallory_signing.key (keep secret) and mallory_signing.pub (share with auditors)."""
    out_dir.mkdir(parents=True, exist_ok=True)
    key = Ed25519PrivateKey.generate()
    priv = out_dir / "mallory_signing.key"
    pub = out_dir / "mallory_signing.pub"
    priv.write_bytes(
        key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
    )
    os.chmod(priv, 0o600)
    pub.write_bytes(
        key.public_key().public_bytes(
            serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo
        )
    )
    return priv, pub


def _load_private(path: Path) -> Ed25519PrivateKey:
    k = serialization.load_pem_private_key(path.read_bytes(), password=None)
    if not isinstance(k, Ed25519PrivateKey):
        raise ValueError("Signing key must be Ed25519.")
    return k


def _load_public(path: Path) -> Ed25519PublicKey:
    k = serialization.load_pem_public_key(path.read_bytes())
    if not isinstance(k, Ed25519PublicKey):
        raise ValueError("Public key must be Ed25519.")
    return k


# ---------- record ----------

def _git(*args: str) -> str | None:
    try:
        return subprocess.check_output(["git", *args], stderr=subprocess.DEVNULL, text=True).strip()
    except Exception:
        return None


def _finding_digest(f: Finding) -> dict:
    """What the attestation commits to per finding. Evidence paths stay out; their content
    is not portable, but the fingerprint and steps are enough to re-run the reproduction."""
    return {
        "fingerprint": f.fingerprint,
        "kind": f.kind.value,
        "severity": f.severity.value,
        "title": f.title,
        "agent": f.agent,
        "owasp": OWASP.get(f.kind, "unmapped"),
        "confirmed": f.confirmed,
    }


def build_record(confirmed: list[Finding], agents: list[str], dropped_count: int) -> dict:
    findings = [_finding_digest(f) for f in confirmed]
    counts = {s.value: 0 for s in Severity}
    for f in confirmed:
        counts[f.severity.value] += 1
    return {
        "schema": SCHEMA,
        "tested_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "repo": os.environ.get("GITHUB_REPOSITORY") or _git("config", "--get", "remote.origin.url"),
        "commit": os.environ.get("GITHUB_SHA") or _git("rev-parse", "HEAD"),
        "agents": agents,
        "sandbox": {"egress": "blocked", "isolation": "throwaway container per run"},
        "summary": {"confirmed": len(confirmed), "dropped_unreproducible": dropped_count, **counts},
        "findings": findings,
        "suggested_controls": [{"id": i, "description": d} for i, d in SUGGESTED_CONTROLS],
    }


def _canonical(record: dict) -> bytes:
    return json.dumps(record, sort_keys=True, separators=(",", ":")).encode()


def sign(record: dict, key_path: Path) -> dict:
    key = _load_private(key_path)
    payload = _canonical(record)
    pub = key.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    return {
        "record": record,
        "sha256": hashlib.sha256(payload).hexdigest(),
        "signature": base64.b64encode(key.sign(payload)).decode(),
        "public_key_fingerprint": hashlib.sha256(pub).hexdigest()[:16],
    }


def verify(attestation: dict, pub_path: Path) -> bool:
    payload = _canonical(attestation["record"])
    if hashlib.sha256(payload).hexdigest() != attestation.get("sha256"):
        return False
    try:
        _load_public(pub_path).verify(base64.b64decode(attestation["signature"]), payload)
        return True
    except (InvalidSignature, KeyError, ValueError):
        return False


# ---------- human-readable report ----------

def render_compliance_md(att: dict) -> str:
    r = att["record"]
    s = r["summary"]
    lines = [
        "# Mallory security test attestation",
        "",
        f"- **Repository:** {r.get('repo') or 'unknown'}",
        f"- **Commit:** `{r.get('commit') or 'unknown'}`",
        f"- **Tested at (UTC):** {r['tested_at']}",
        f"- **Agents:** {', '.join(r['agents'])}",
        f"- **Environment:** isolated throwaway container, outbound network blocked",
        f"- **Record SHA-256:** `{att['sha256']}`",
        f"- **Signing key fingerprint:** `{att['public_key_fingerprint']}`",
        "",
        "## Result",
        "",
        f"{s['confirmed']} confirmed finding(s), each reproduced before being recorded. "
        f"{s['dropped_unreproducible']} candidate(s) could not be reproduced and were excluded.",
        "",
        "| Severity | Count |",
        "| --- | --- |",
    ]
    for sev in ("critical", "high", "medium", "low", "info"):
        lines.append(f"| {sev} | {s[sev]} |")
    if r["findings"]:
        lines += ["", "## Findings", "", "| Fingerprint | Severity | OWASP | Title |", "| --- | --- | --- | --- |"]
        for f in r["findings"]:
            lines.append(f"| `{f['fingerprint']}` | {f['severity']} | {f['owasp']} | {f['title']} |")
    lines += ["", "## Suggested control mapping", ""]
    for c in r["suggested_controls"]:
        lines.append(f"- **{c['id']}**: {c['description']}")
    lines += [
        "",
        "_Suggested mappings help file this evidence. They are not a certification; "
        "whether this record satisfies a control is the auditor's determination._",
        "",
        "Verify this record: `mallory verify attestation.json --pub mallory_signing.pub`",
    ]
    return "\n".join(lines)


def write_attestation(
    confirmed: list[Finding], agents: list[str], dropped_count: int, key_path: Path, out_dir: Path
) -> tuple[Path, Path]:
    att = sign(build_record(confirmed, agents, dropped_count), key_path)
    out_dir.mkdir(parents=True, exist_ok=True)
    j = out_dir / "attestation.json"
    m = out_dir / "attestation.md"
    j.write_text(json.dumps(att, indent=2))
    m.write_text(render_compliance_md(att))
    return j, m
