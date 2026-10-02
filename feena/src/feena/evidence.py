"""Bounded browser diagnostics. Raw artifacts remain local and may contain test data."""
from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit


def diagnostic_url(url: str) -> str:
    """Exclude query strings, fragments, and URL credentials from diagnostic logs."""
    parts = urlsplit(url)
    host = parts.netloc.rsplit("@", 1)[-1]
    return urlunsplit((parts.scheme, host, parts.path, "", ""))


class BrowserEvidence:
    def __init__(self, context, directory: Path):
        self.directory = directory
        self.console: list[dict] = []
        self.network: list[dict] = []
        context.on("page", self.attach_page)
        context.on("response", lambda r: self.record(self.network, {
            "url": diagnostic_url(r.url), "method": r.request.method, "status": r.status,
        }))
        context.on("requestfailed", lambda r: self.record(self.network, {
            "url": diagnostic_url(r.url), "method": r.method, "failure": r.failure,
        }))

    @staticmethod
    def record(destination, event):
        if len(destination) < 1000:
            destination.append(event)

    def attach_page(self, page):
        page.on("console", lambda m: self.record(self.console, {
            "type": m.type, "text": m.text[:4000],
        }))
        page.on("pageerror", lambda e: self.record(self.console, {
            "type": "pageerror", "text": str(e)[:4000],
        }))

    def save(self):
        self.directory.mkdir(parents=True, exist_ok=True)
        for name, events in (("console.json", self.console), ("network.json", self.network)):
            (self.directory / name).write_text(json.dumps(events, indent=2) + "\n")
