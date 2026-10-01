"""The findings corpus: what actually breaks, across many real apps.

This is the moat from the business model. Every run can contribute *anonymised* records of
confirmed findings; over time that tells us which checks land, on which stacks, and how often,
so hosted checks get sharper in a way a fresh DIY prompt never does.

Privacy rules, enforced here rather than promised in docs:
- Opt-in only. Nothing is recorded unless ``corpus.enabled: true`` in mallory.yaml.
- A record carries the *pattern*, never the app: kind, severity, check, stack, route shape.
  No URLs, hostnames, response bodies, input values, screenshots, repo names, or user data.
- Route shapes are generalised: numeric and uuid-like segments become ``:id``.
- Records are written locally as JSONL. Upload is a separate, explicit step to an endpoint the
  user configures; the open-source runner never sends anything on its own.
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

import httpx

from .findings import Finding

_ID = re.compile(
    r"^(\d+|[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}|[0-9a-f]{16,})$", re.I
)


def route_shape(target: str) -> str:
    """'/api/orders/42?q=x' -> '/api/orders/:id'. Drops query, host, and ids."""
    path = target.split("?")[0].split("#")[0]
    if "://" in path:
        path = "/" + path.split("://", 1)[1].split("/", 1)[-1]
    segs = [(":id" if _ID.match(s) else s) for s in path.split("/") if s]
    return "/" + "/".join(segs)


@dataclass
class CorpusRecord:
    pattern: str        # stable hash of (kind, check, route shape): same bug class, same id
    kind: str
    severity: str
    agent: str
    check: str          # title with instance-specific bits removed
    route: str
    stack: str
    recorded_at: str


def _check_name(f: Finding) -> str:
    # Titles embed the route ("... at /api/orders"); strip it so the check name generalises.
    return re.split(r"\s(?:at|:)\s/", f.title)[0].strip()


def to_record(f: Finding, stack: str) -> CorpusRecord:
    route = route_shape(f.steps[0].target) if f.steps else "/"
    check = _check_name(f)
    pattern = hashlib.sha256(f"{f.kind.value}|{check}|{route}".encode()).hexdigest()[:16]
    return CorpusRecord(
        pattern=pattern,
        kind=f.kind.value,
        severity=f.severity.value,
        agent=f.agent,
        check=check,
        route=route,
        stack=stack,
        recorded_at=datetime.now(timezone.utc).date().isoformat(),  # day precision only
    )


def record(confirmed: list[Finding], stack: str, out_dir: Path) -> Path:
    """Append anonymised records for confirmed findings only. Unconfirmed never enter."""
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "corpus.jsonl"
    with path.open("a") as fh:
        for f in confirmed:
            if f.confirmed:
                fh.write(json.dumps(asdict(to_record(f, stack))) + "\n")
    return path


def summarize(path: Path) -> list[tuple[str, str, int]]:
    """(check, route, count) across the local corpus, most frequent first."""
    counts: dict[tuple[str, str], int] = {}
    if path.exists():
        for line in path.read_text().splitlines():
            r = json.loads(line)
            key = (r["check"], r["route"])
            counts[key] = counts.get(key, 0) + 1
    return sorted(((c, r, n) for (c, r), n in counts.items()), key=lambda t: -t[2])


def upload(path: Path, endpoint: str, token: str | None) -> int:
    """Explicit, user-invoked upload to a configured endpoint. Returns records sent."""
    if not path.exists():
        return 0
    lines = [json.loads(l) for l in path.read_text().splitlines() if l.strip()]
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    r = httpx.post(endpoint, json={"records": lines}, headers=headers, timeout=20.0)
    r.raise_for_status()
    return len(lines)
