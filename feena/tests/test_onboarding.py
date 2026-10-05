"""Browser regression checks for the workspace connection flow."""
import json
from pathlib import Path

import pytest
from playwright.sync_api import sync_playwright


@pytest.fixture
def page():
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_page()
        yield page
        browser.close()


def serve(page, *, endpoint="https://qa.example.com/mcp", status=200, workspace=None):
    html = Path("src/feena/onboarding.html").read_text()

    def route(request):
        path = request.request.url.split("example.com", 1)[-1]
        if path == "/connection-info":
            request.fulfill(json={"endpoint": endpoint})
        elif path == "/connection-check":
            request.fulfill(status=status, json={"connected": status == 200, "workspace": workspace})
        else:
            request.fulfill(content_type="text/html", body=html)

    page.route("https://qa.example.com/**", route)
    page.goto("https://qa.example.com/")


def test_keyboard_verification_and_reset(page):
    serve(page, workspace={"name": "Team QA", "environment": "Disposable checkout", "journey_count": 3})
    key = page.get_by_label("Workspace access key", exact=True)
    key.fill("test-key")
    key.press("Enter")
    page.wait_for_function("!document.querySelector('#install').hidden")
    assert "Workspace key verified" in page.locator("#message").inner_text()
    assert page.locator("#workspace-name").inner_text() == "Team QA"
    assert page.locator("#journey-count").inner_text() == "3"
    from urllib.parse import parse_qs, urlsplit
    import base64
    link = page.locator("#install").get_attribute("href")
    config = json.loads(base64.b64decode(parse_qs(urlsplit(link).query)["config"][0]))
    assert config == {"url": "https://qa.example.com/mcp", "headers": {"Authorization": "Bearer test-key"}}
    key.fill("changed-key")
    assert page.locator("#install").is_hidden()
    assert page.locator("#install").get_attribute("href") is None
    assert page.locator("#workspace").is_hidden()
    assert page.locator("#workspace-name").inner_text() == ""
    assert "First check your connection" in page.locator("#installHint").inner_text()


def test_invalid_key_allows_retry(page):
    serve(page, status=401)
    page.locator("#key").fill("wrong-key")
    page.locator("#check").click()
    page.wait_for_function("document.querySelector('#key').getAttribute('aria-invalid') === 'true'")
    assert "not accepted" in page.locator("#message").inner_text()
    assert page.locator("#check").is_enabled()
    assert page.locator("#install").is_hidden()


def test_incomplete_setup_keeps_example_available(page):
    serve(page, endpoint=None)
    page.wait_for_function("document.querySelector('#mode').textContent === 'Preview only'")
    assert page.locator("#key").is_disabled()
    assert page.locator("#check").is_disabled()
    assert page.locator("#example").is_visible()
    assert page.locator("#retry").is_visible()
    page.set_viewport_size({"width": 375, "height": 812})
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")


def test_service_failure_can_recover_without_refresh(page):
    serve(page)
    page.route("**/connection-info", lambda route: route.fulfill(status=503, json={}))
    page.reload()
    page.wait_for_function("document.querySelector('#mode').textContent === 'Unavailable'")
    page.unroute("**/connection-info")
    page.locator("#retry").click()
    page.wait_for_function("!document.querySelector('#key').disabled")
    assert page.locator("#mode").inner_text() == "Private workspace"


def test_copy_prompt_falls_back_to_selection(page):
    serve(page)
    page.evaluate("Object.defineProperty(navigator, 'clipboard', {value: {writeText: () => Promise.reject(new Error('denied'))}, configurable: true})")
    page.locator("#copy").click()
    page.wait_for_function("document.querySelector('#copy-status').textContent.includes('Select and copy')")
    assert page.locator("#prompt").evaluate("el => el.selectionEnd - el.selectionStart === el.value.length")
