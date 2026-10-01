"""A recorded Playwright session, one per agent run.

Each agent gets its own browser context so recordings and traces don't cross. Recording is on
by default because "every finding comes with a screen recording" is a core promise.
"""
from __future__ import annotations

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
        self.page = self._context.new_page()
        return self

    def goto(self, path: str = "/") -> None:
        assert self.page is not None
        self.page.goto(path if path.startswith("http") else self.base_url + path)

    def snapshot(self) -> str:
        """A cheap, text-first view of the page for the agent to reason over.

        Prefers the accessibility tree (cheap, structured) and leaves screenshots to the
        moments the agent explicitly asks for one.
        """
        assert self.page is not None
        tree = self.page.accessibility.snapshot() or {}
        return _flatten_ax(tree)

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
