"""A recorded Playwright session, one per agent run.

Each agent gets its own browser context so recordings and traces don't cross. Recording is on
by default because "every finding comes with a screen recording" is a core promise.
"""
from __future__ import annotations

import json
from collections import deque
from contextlib import contextmanager
from pathlib import Path

from playwright.sync_api import Browser, BrowserContext, Page, sync_playwright


class Session:
    def __init__(self, base_url: str, out_dir: Path, headed: bool = False):
        self.base_url = base_url.rstrip("/")
        self.out_dir = out_dir
        self.headed = headed
        self._pw = None
        self._browser: Browser | None = None
        self._context: BrowserContext | None = None
        self.page: Page | None = None
        self.errors = deque(maxlen=8)
        self.action_index = 0

    def __enter__(self) -> "Session":
        self._pw = sync_playwright().start()
        self._browser = self._pw.chromium.launch(headless=not self.headed)
        self.out_dir.mkdir(parents=True, exist_ok=True)
        self._context = self._browser.new_context(
            base_url=self.base_url,
            record_video_dir=str(self.out_dir / "video"),
            viewport={"width": 1280, "height": 800},
        )
        # Trace captures DOM snapshots + actions so a finding can be replayed step by step.
        self._context.tracing.start(screenshots=True, snapshots=True, sources=True)
        self._context.set_default_timeout(3000)
        self._context.set_default_navigation_timeout(10000)
        self.page = self._context.new_page()
        self.page.on("pageerror", lambda error: self.errors.append(str(error)[:500]))
        self.page.on("console", lambda msg: self.errors.append(msg.text[:500])
                     if msg.type == "error" else None)
        return self

    def goto(self, path: str = "/") -> None:
        assert self.page is not None
        self.page.goto(path if path.startswith("http") else self.base_url + path,
                       wait_until="domcontentloaded")

    def snapshot(self) -> str:
        """A cheap, text-first view of the page for the agent to reason over.

        Uses the current ARIA snapshot API with a visible-text fallback. Screenshots
        are supplied separately to the model by the exploratory loop.
        """
        assert self.page is not None
        try:
            tree = self.page.locator("body").aria_snapshot(timeout=3000)
        except Exception:
            try:
                tree = "Accessibility snapshot unavailable; visible text fallback:\n" + self.page.locator("body").inner_text(timeout=3000)
            except Exception:
                tree = "Page observation unavailable. Do not infer that the page is empty."
        return (f"URL: {self.page.url}\nRecent browser errors (diagnostic, not proof of a bug):\n"
                + "\n".join(self.errors) + "\nPage:\n" + tree[:16000])

    def perform(self, decision, timeout_ms: int = 3000) -> dict:
        """Execute once. A timeout may follow a successful write: never blindly retry."""
        assert self.page is not None
        timeout_ms = max(1, min(timeout_ms, 10000))
        result = {"action": decision.action, "target": decision.target,
                  "role": decision.role, "name": decision.name, "status": "ok"}
        try:
            if decision.action == "goto":
                from urllib.parse import urljoin, urlsplit
                target = urljoin(self.base_url + "/", decision.target or "/")
                origin = lambda url: (urlsplit(url).scheme, urlsplit(url).hostname,
                                      urlsplit(url).port or (443 if urlsplit(url).scheme == "https" else 80))
                if origin(target) != origin(self.base_url) or urlsplit(target).username or urlsplit(target).password:
                    raise ValueError("Navigation must stay on the configured origin")
                self.page.goto(target, wait_until="domcontentloaded", timeout=timeout_ms)
            elif decision.action in {"click", "fill", "dblclick", "press"}:
                locator = (self.page.get_by_role(decision.role, name=decision.name, exact=True)
                           if decision.role else self.page.locator(decision.target))
                # Strict locators and Playwright's actionability waits reject ambiguous targets.
                if decision.action == "fill":
                    locator.fill(decision.value, timeout=timeout_ms)
                elif decision.action == "press":
                    locator.press(decision.value, timeout=timeout_ms)
                else:
                    getattr(locator, decision.action)(timeout=timeout_ms)
            elif decision.action == "back":
                self.page.go_back(wait_until="domcontentloaded", timeout=timeout_ms)
            elif decision.action != "note_finding":
                raise ValueError("Unsupported browser action")
        except Exception as error:
            result.update(status="error", error_type=type(error).__name__,
                          reason="Action did not complete reliably. Inspect the next observation before retrying; side effects may already have occurred.")
        result["url"] = self.page.url
        self.action_index += 1
        self.out_dir.mkdir(parents=True, exist_ok=True)
        try:
            shot = self.out_dir / f"action-{self.action_index:04d}.png"
            self.page.screenshot(path=str(shot), timeout=timeout_ms)
            result["screenshot"] = str(shot)
        except Exception:
            result["screenshot_status"] = "unavailable"
        # Inputs may be credentials: omit values and model reasoning from the action log.
        with (self.out_dir / "agent-actions.jsonl").open("a") as handle:
            handle.write(json.dumps(result) + "\n")
        return result

    def screenshot(self, name: str) -> Path:
        assert self.page is not None
        p = self.out_dir / f"{name}.png"
        self.page.screenshot(path=str(p), full_page=True)
        return p

    def __exit__(self, *exc) -> None:
        try:
            if self._context is not None:
                self._context.tracing.stop(path=str(self.out_dir / "trace.zip"))
                self._context.close()
        finally:
            if self._browser is not None:
                self._browser.close()
            if self._pw is not None:
                self._pw.stop()


def _flatten_ax(node: dict, depth: int = 0, lines: list[str] | None = None) -> str:
    """Turn the accessibility tree into indented text an LLM can read cheaply."""
    lines = lines if lines is not None else []
    role = node.get("role", "")
    name = node.get("name", "")
    if role:
        label = f"{role}: {name}".rstrip(": ").strip()
        if label:
            lines.append("  " * depth + label)
    for child in node.get("children", []) or []:
        _flatten_ax(child, depth + 1, lines)
    return "\n".join(lines)


@contextmanager
def session(base_url: str, out_dir: Path, headed: bool = False):
    s = Session(base_url, out_dir, headed)
    with s:
        yield s
