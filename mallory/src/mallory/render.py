"""A thin Playwright wrapper the hostile checks use to see the *rendered* DOM.

The httpx-based checks only see server-sent HTML, so on a client-rendered app (React, Next,
Angular) a reflected or stored value that JavaScript injects after load is invisible to them.
The Renderer navigates in a real browser, lets the app settle, and hands back the rendered HTML,
so the XSS checks test what a user's browser actually builds.

Everything here is read/interaction against the sandboxed copy — same non-destructive posture as
the rest of the hostile agent. If a browser can't start, ``browser_available()`` is False and the
XSS checks fall back to httpx.
"""
from __future__ import annotations

from urllib.parse import urlencode, urlsplit


def browser_available() -> bool:
    try:
        from playwright.sync_api import sync_playwright

        with sync_playwright() as p:
            b = p.chromium.launch(headless=True)
            b.close()
        return True
    except Exception:
        return False


class Renderer:
    def __init__(self, base_url: str, headed: bool = False, settle_ms: int = 700):
        self.base_url = base_url.rstrip("/")
        self.headed = headed
        self.settle_ms = settle_ms
        self._pw = None
        self._browser = None
        self._ctx = None
        self.page = None

    def start(self) -> "Renderer":
        from playwright.sync_api import sync_playwright

        self._pw = sync_playwright().start()
        self._browser = self._pw.chromium.launch(headless=not self.headed)
        self._ctx = self._browser.new_context()
        self.page = self._ctx.new_page()
        return self

    def close(self) -> None:
        for obj, meth in ((self._ctx, "close"), (self._browser, "close")):
            try:
                if obj:
                    getattr(obj, meth)()
            except Exception:
                pass
        try:
            if self._pw:
                self._pw.stop()
        except Exception:
            pass

    def __enter__(self):
        return self.start()

    def __exit__(self, *exc):
        self.close()

    # --- auth bridge: reuse a working httpx login instead of driving every login UI ---
    def add_cookies_from_httpx(self, client) -> None:
        host = urlsplit(self.base_url).netloc.split(":")[0]
        cookies = []
        for c in client.cookies.jar:
            cookies.append({
                "name": c.name, "value": c.value,
                "domain": c.domain or host, "path": c.path or "/",
            })
        if cookies and self._ctx:
            try:
                self._ctx.add_cookies(cookies)
            except Exception:
                pass

    # --- rendered reads ---
    def rendered_html(self, path: str, params: dict | None = None) -> str:
        url = self.base_url + (path if path.startswith("/") else "/" + path)
        if params:
            url += ("&" if "?" in url else "?") + urlencode(params)
        try:
            self.page.goto(url, wait_until="domcontentloaded", timeout=15000)
            try:
                self.page.wait_for_load_state("networkidle", timeout=self.settle_ms)
            except Exception:
                self.page.wait_for_timeout(self.settle_ms)  # SPA still settling; give it a beat
            return self.page.content()
        except Exception:
            return ""

    def links(self) -> list[str]:
        """Same-origin path links from the currently rendered page."""
        try:
            hrefs = self.page.eval_on_selector_all(
                "a[href]", "els => els.map(e => e.getAttribute('href'))"
            ) or []
        except Exception:
            return []
        out = []
        for h in hrefs:
            if h and h.startswith("/"):
                out.append(h.split("?")[0].split("#")[0])
        return out

    def find_forms(self) -> list[dict]:
        """Forms from the *rendered* DOM: [{action, method, fields:[name,...]}]."""
        try:
            return self.page.evaluate(
                """() => Array.from(document.forms).map(f => ({
                    action: f.getAttribute('action') || location.pathname,
                    method: (f.getAttribute('method') || 'post').toLowerCase(),
                    fields: Array.from(f.querySelectorAll('input,textarea'))
                        .filter(i => !['password','hidden','submit','button','file']
                            .includes((i.getAttribute('type')||'text').toLowerCase()))
                        .map(i => i.getAttribute('name'))
                        .filter(Boolean)
                }))"""
            ) or []
        except Exception:
            return []

    def submit_form(self, form: dict, value: str) -> bool:
        """Fill each text field with the marker and submit by interaction (real SPA path)."""
        try:
            for name in form.get("fields", []):
                sel = f'[name="{name}"]'
                if self.page.query_selector(sel):
                    self.page.fill(sel, value)
            btn = self.page.query_selector(
                'button[type="submit"], input[type="submit"], form button'
            )
            if btn:
                btn.click()
            else:
                self.page.keyboard.press("Enter")
            try:
                self.page.wait_for_load_state("networkidle", timeout=self.settle_ms)
            except Exception:
                self.page.wait_for_timeout(self.settle_ms)
            return True
        except Exception:
            return False
