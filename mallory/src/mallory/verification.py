"""Finding-specific replay for machine-readable repro specs."""
from __future__ import annotations

import secrets
from dataclasses import dataclass
from enum import Enum
from urllib.parse import urlencode, urljoin, urlsplit

import httpx

from .agents.checks import access_control, headers, input_reflection, sqli, stored_xss
from .config import Config
from .findings import Finding
from .sandbox import Sandbox


class Status(str, Enum):
    REPRODUCED = "reproduced"
    NOT_REPRODUCED = "not_reproduced"
    INCONCLUSIVE = "inconclusive"


@dataclass(frozen=True)
class VerificationResult:
    status: Status
    reason: str


def _result(status: Status, reason: str) -> VerificationResult:
    return VerificationResult(status, reason)


def _local_path(value: object) -> bool:
    if not isinstance(value, str) or not value.startswith("/") or value.startswith("//"):
        return False
    parts = urlsplit(value)
    return not (parts.scheme or parts.netloc or parts.fragment or "\\" in value
                or any(ord(char) < 32 for char in value))


def _response_issue(response: httpx.Response | None, path: str) -> VerificationResult | None:
    if response is None:
        return _result(Status.INCONCLUSIVE, f"Target could not be reached at {path}.")
    if response.status_code in (404, 405):
        return _result(Status.INCONCLUSIVE, f"No supported endpoint at {path}.")
    if response.status_code >= 500:
        return _result(Status.INCONCLUSIVE, f"Endpoint {path} returned a server error.")
    return None


def _get(sandbox: Sandbox, path: str, **kwargs) -> httpx.Response | None:
    try:
        return httpx.get(sandbox.base_url.rstrip("/") + path, timeout=5.0, **kwargs)
    except httpx.HTTPError:
        return None


def _login(sandbox: Sandbox, cfg: Config, count: int) -> tuple[list[httpx.Client], str | None]:
    clients = []
    for user in cfg.users[:count]:
        client = access_control._login(sandbox.base_url.rstrip("/"), user.email, user.password)
        if client is None:
            for opened in clients:
                opened.close()
            return [], "Configured test-account login failed."
        clients.append(client)
    return clients, None


def _decode_data(response: httpx.Response) -> dict | list | None:
    if not access_control._looks_like_data(response):
        return None
    try:
        return response.json()
    except ValueError:
        return None


def _headers(finding: Finding, sandbox: Sandbox) -> VerificationResult:
    path, name = finding.repro["path"], finding.repro.get("header")
    if path != "/" or not isinstance(name, str) or name not in headers.EXPECTED:
        return _result(Status.INCONCLUSIVE, "Header repro is outside the built-in check's scope.")
    response = _get(sandbox, path)
    issue = _response_issue(response, path)
    if issue:
        return issue
    present = {header.lower() for header in response.headers}
    if name not in present:
        return _result(Status.REPRODUCED, f"The response still omits {name}.")
    return _result(Status.NOT_REPRODUCED, f"The response now includes {name}.")


def _missing_auth(finding: Finding, sandbox: Sandbox) -> VerificationResult:
    path = finding.repro["path"]
    if path not in access_control.LIKELY_PROTECTED:
        return _result(Status.INCONCLUSIVE, "Endpoint is outside the built-in missing-auth check.")
    response = _get(sandbox, path)
    issue = _response_issue(response, path)
    if issue:
        return issue
    if response.status_code in (401, 403) or 300 <= response.status_code < 400:
        return _result(Status.NOT_REPRODUCED, f"Unauthenticated GET {path} is now denied or redirected.")
    if "json" not in response.headers.get("content-type", "").lower():
        return _result(Status.INCONCLUSIVE, f"Endpoint {path} did not return the JSON data this check supports.")
    if access_control._looks_like_data(response):
        return _result(Status.REPRODUCED, f"Unauthenticated GET {path} still returns data.")
    return _result(Status.NOT_REPRODUCED, f"Unauthenticated GET {path} no longer returns data.")


def _idor(finding: Finding, cfg: Config, sandbox: Sandbox) -> VerificationResult:
    path = finding.repro["path"]
    parts = path.strip("/").split("/")
    if (len(parts) != 3 or parts[0] != "api" or parts[1] not in access_control.OBJECT_RESOURCES
            or not parts[2].isdigit() or not 1 <= int(parts[2]) <= 5):
        return _result(Status.INCONCLUSIVE, "Object path is outside the built-in IDOR probes.")
    if not cfg.users:
        return _result(Status.INCONCLUSIVE, "IDOR replay requires configured attacker credentials.")
    clients, error = _login(sandbox, cfg, 1)
    if error:
        return _result(Status.INCONCLUSIVE, error)
    client = clients[0]
    try:
        attacker_id = access_control._own_id(client)
        if attacker_id is None:
            return _result(Status.INCONCLUSIVE, "Could not determine the logged-in account ID.")
        try:
            response = client.get(path)
        except httpx.HTTPError:
            return _result(Status.INCONCLUSIVE, f"Target could not be reached at {path}.")
        issue = _response_issue(response, path)
        if issue:
            return issue
        if response.status_code in (401, 403):
            return _result(Status.NOT_REPRODUCED, "Authenticated request was denied access to the object.")
        data = _decode_data(response)
        if not isinstance(data, dict):
            return _result(Status.INCONCLUSIVE, "Object response did not contain a JSON object.")
        owner = access_control._owner_of(data)
        if owner is None:
            return _result(Status.INCONCLUSIVE, "Object response has no recognized owner field.")
        if owner != attacker_id:
            return _result(Status.REPRODUCED, f"Object owner {owner} differs from attacker {attacker_id}.")
        return _result(Status.NOT_REPRODUCED, "Object is scoped to the authenticated account.")
    finally:
        client.close()


def _same_data(finding: Finding, cfg: Config, sandbox: Sandbox) -> VerificationResult:
    path = finding.repro["path"]
    if path not in ("/api/orders", "/api/me", "/api/users", "/api/tasks"):
        return _result(Status.INCONCLUSIVE, "Collection path is outside the built-in same-data probes.")
    if len(cfg.users) < 2:
        return _result(Status.INCONCLUSIVE, "Two configured accounts are required for this access check.")
    clients, error = _login(sandbox, cfg, 2)
    if error:
        return _result(Status.INCONCLUSIVE, error)
    try:
        identities = []
        for client, user in zip(clients, cfg.users[:2]):
            try:
                response = client.get("/api/me")
                identity = response.json() if response.status_code == 200 else None
            except (httpx.HTTPError, ValueError):
                identity = None
            if not isinstance(identity, dict):
                return _result(Status.INCONCLUSIVE, "Could not verify authenticated account identity at /api/me.")
            account_id, email = identity.get("id"), identity.get("email")
            if account_id is None or not isinstance(email, str):
                return _result(Status.INCONCLUSIVE, "Authenticated identity must include an account ID and email.")
            if email.casefold() != user.email.casefold():
                return _result(Status.INCONCLUSIVE, "Authenticated identity did not match the configured account email.")
            identities.append(str(account_id))
        if identities[0] == identities[1]:
            return _result(Status.INCONCLUSIVE, "Configured accounts resolved to the same authenticated account ID.")

        responses = []
        for client in clients:
            try:
                response = client.get(path)
            except httpx.HTTPError:
                return _result(Status.INCONCLUSIVE, f"Target could not be reached at {path}.")
            issue = _response_issue(response, path)
            if issue:
                return issue
            if response.status_code in (401, 403):
                return _result(Status.INCONCLUSIVE, "Configured account could not access the collection.")
            responses.append(response)
        if any("json" not in response.headers.get("content-type", "").lower()
               for response in responses):
            return _result(Status.INCONCLUSIVE, f"Endpoint {path} did not return supported JSON data.")
        if all(access_control._looks_like_data(response) for response in responses):
            if responses[0].content == responses[1].content and len(responses[0].content) > 20:
                return _result(Status.REPRODUCED, "Both accounts still receive byte-identical data.")
            return _result(Status.NOT_REPRODUCED, "The two accounts receive different data.")
        return _result(Status.NOT_REPRODUCED, "The collection no longer returns data to both accounts.")
    finally:
        for client in clients:
            client.close()


def _browser_renderer(sandbox: Sandbox):
    from .render import Renderer

    try:
        return Renderer(sandbox.base_url).start(), None
    except Exception as exc:  # noqa: BLE001 - browser setup failure cannot prove absence
        return None, _result(Status.INCONCLUSIVE, f"Browser replay could not start ({type(exc).__name__}).")


def _browser_get(renderer, path: str, params: dict | None = None):
    url = renderer.base_url + path
    if params:
        url += "?" + urlencode(params)
    try:
        response = renderer.page.goto(url, wait_until="domcontentloaded", timeout=15000)
        if response is None:
            return None, "Browser navigation returned no HTTP response."
        status = response.status
        if status in (404, 405):
            return None, f"No supported browser endpoint at {path}."
        if status in (401, 403):
            return None, f"Browser endpoint {path} requires unavailable authentication."
        if status >= 500:
            return None, f"Browser endpoint {path} returned a server error."
        if "html" not in response.headers.get("content-type", "").lower():
            return None, f"Browser endpoint {path} did not return HTML."
        settle_ms = getattr(renderer, "settle_ms", 700)
        try:
            renderer.page.wait_for_load_state("networkidle", timeout=settle_ms)
        except Exception:  # noqa: BLE001 - preserve Renderer settle fallback on idle timeout
            renderer.page.wait_for_timeout(settle_ms)
        return renderer.page.content(), None
    except Exception as exc:  # noqa: BLE001 - navigation errors are inconclusive
        return None, f"Browser navigation failed ({type(exc).__name__})."


def _reflected(finding: Finding, sandbox: Sandbox) -> VerificationResult:
    repro = finding.repro
    path, param = repro["path"], repro.get("param")
    if (path, param) not in input_reflection.SURFACES:
        return _result(Status.INCONCLUSIVE, "Reflection surface is outside the built-in probe set.")
    marker = "MALX" + secrets.token_hex(4)
    probe = marker + "<b>x</b>"
    if repro.get("rendered") is False:
        try:
            response = _get(sandbox, path, params={param: probe})
            issue = _response_issue(response, path)
            if issue:
                return issue
            if response.status_code in (401, 403):
                return _result(Status.INCONCLUSIVE, "Reflection endpoint requires unavailable authentication.")
            if "html" not in response.headers.get("content-type", "").lower():
                return _result(Status.INCONCLUSIVE, "Reflection endpoint did not return HTML.")
            html = response.text
        except httpx.HTTPError:
            return _result(Status.INCONCLUSIVE, "Target could not be reached during reflection replay.")
        is_unescaped = input_reflection._unescaped(html, marker)
    elif repro.get("rendered") is True:
        renderer, error = _browser_renderer(sandbox)
        if error:
            return error
        try:
            html, navigation_error = _browser_get(renderer, path, {param: probe})
            if navigation_error:
                return _result(Status.INCONCLUSIVE, navigation_error)
            is_unescaped = input_reflection._unescaped(html, marker)
        finally:
            renderer.close()
    else:
        return _result(Status.INCONCLUSIVE, "Reflection repro is missing its rendering mode.")
    if is_unescaped:
        return _result(Status.REPRODUCED, f"Input remains unescaped at {path}.")
    return _result(Status.NOT_REPRODUCED, f"Input is escaped or no longer reflected at {path}.")


def _sqli_get(finding: Finding, sandbox: Sandbox) -> VerificationResult:
    repro = finding.repro
    path, param, mode = repro["path"], repro.get("param"), repro.get("mode")
    if (path, param) not in sqli.GET_SURFACES or mode not in ("error", "boolean"):
        return _result(Status.INCONCLUSIVE, "SQLi GET repro is outside the built-in probe set.")
    try:
        with httpx.Client(base_url=sandbox.base_url.rstrip("/"), timeout=5.0) as client:
            if mode == "error":
                benign = client.get(path, params={param: "mallory"})
                quoted = client.get(path, params={param: "mallory" + sqli.QUOTE})
                issue = _response_issue(benign, path)
                if issue:
                    return issue
                if quoted.status_code in (404, 405):
                    return _result(Status.INCONCLUSIVE, "Quoted SQLi probe returned an unsupported response.")
                if quoted.status_code in (401, 403):
                    return _result(Status.INCONCLUSIVE, "SQLi endpoint requires unavailable authentication.")
                if quoted.status_code >= 500:
                    if benign.status_code < 500:
                        return _result(Status.REPRODUCED, "Quote probe changed a successful page to a server error.")
                    return _result(Status.INCONCLUSIVE, "Both benign and quoted SQLi probes errored.")
                vulnerable = sqli._err(quoted.text) or (
                    benign.status_code < 500 <= quoted.status_code)
            else:
                true_response = client.get(path, params={param: sqli.TRUE_PROBE})
                false_response = client.get(path, params={param: sqli.FALSE_PROBE})
                for response in (true_response, false_response):
                    issue = _response_issue(response, path)
                    if issue:
                        return issue
                    if response.status_code in (401, 403):
                        return _result(Status.INCONCLUSIVE, "SQLi endpoint requires unavailable authentication.")
                true_body = sqli._strip(true_response.text, sqli.TRUE_PROBE)
                false_body = sqli._strip(false_response.text, sqli.FALSE_PROBE)
                vulnerable = (true_response.status_code == false_response.status_code
                              and true_body != false_body
                              and abs(len(true_body) - len(false_body)) > 0)
    except httpx.HTTPError:
        return _result(Status.INCONCLUSIVE, "Target could not be reached during SQLi replay.")
    if vulnerable:
        return _result(Status.REPRODUCED, f"The {mode}-based SQLi assertion still holds at {path}.")
    return _result(Status.NOT_REPRODUCED, f"The {mode}-based SQLi assertion no longer holds at {path}.")


def _sqli_login(finding: Finding, sandbox: Sandbox) -> VerificationResult:
    repro = finding.repro
    path, shape, probe = repro["path"], repro.get("shape"), repro.get("probe")
    if path not in sqli.LOGIN_PATHS or shape not in ("form", "json") or probe not in sqli.BYPASS_PROBES:
        return _result(Status.INCONCLUSIVE, "SQLi login repro is outside the built-in probe set.")
    try:
        with httpx.Client(base_url=sandbox.base_url.rstrip("/"), timeout=5.0) as client:
            baseline = sqli._attempt(client, path, "nouser@example.com", "wrongpass", shape)
            if baseline is None:
                return _result(Status.INCONCLUSIVE, f"No supported login endpoint at {path}.")
            issue = _response_issue(baseline, path)
            if issue:
                return issue
            if not sqli._rejected(baseline):
                return _result(Status.INCONCLUSIVE, "Bad-credential login did not establish a rejection baseline.")
            injected = sqli._attempt(client, path, probe, "x", shape)
            if injected is None:
                return _result(Status.INCONCLUSIVE, f"Login endpoint {path} became unavailable.")
            issue = _response_issue(injected, path)
            if issue:
                return issue
    except httpx.HTTPError:
        return _result(Status.INCONCLUSIVE, "Target could not be reached during login replay.")
    if not sqli._rejected(injected):
        return _result(Status.REPRODUCED, "The injection probe still turns rejected login into accepted login.")
    return _result(Status.NOT_REPRODUCED, "The injection probe no longer bypasses login.")


def _form_repro(repro: dict) -> tuple[str, str, str, list[str]] | VerificationResult:
    form_page, page = repro.get("form_page"), repro.get("page")
    action, method, fields = repro.get("action"), repro.get("method"), repro.get("fields")
    for value in (form_page, page):
        if not _local_path(value):
            return _result(Status.INCONCLUSIVE, "Stored-XSS repro has an unsupported page path.")
    if (not isinstance(action, str) or not action or "\\" in action
            or urlsplit(action).scheme or urlsplit(action).netloc or action.startswith("//")):
        return _result(Status.INCONCLUSIVE, "Stored-XSS repro has an unsupported form action.")
    action_path = urljoin("http://mallory.local" + form_page, action)
    parsed_action = urlsplit(action_path)
    if parsed_action.netloc != "mallory.local" or parsed_action.scheme != "http":
        return _result(Status.INCONCLUSIVE, "Stored-XSS form action must stay on the local target.")
    if method not in ("get", "post") or not isinstance(fields, list) or not fields \
            or any(not isinstance(field, str) or not field for field in fields):
        return _result(Status.INCONCLUSIVE, "Stored-XSS repro has unsupported form fields or method.")
    return form_page, page, parsed_action.path, fields


def _stored_http(finding: Finding, cfg: Config, sandbox: Sandbox,
                 form_page: str, page: str, action: str, fields: list[str], method: str):
    if finding.repro.get("login") is True:
        if not cfg.users:
            return _result(Status.INCONCLUSIVE, "Stored-XSS replay requires configured login credentials.")
        client = httpx.Client(base_url=sandbox.base_url.rstrip("/"), timeout=8.0,
                              follow_redirects=True)
        user = cfg.users[0]
        if not stored_xss._do_login(client, user.email, user.password):
            client.close()
            return _result(Status.INCONCLUSIVE, "Configured stored-XSS test-account login failed.")
    elif finding.repro.get("login") is False:
        client = httpx.Client(base_url=sandbox.base_url.rstrip("/"), timeout=8.0,
                              follow_redirects=True)
    else:
        return _result(Status.INCONCLUSIVE, "Stored-XSS repro is missing its login requirement.")
    try:
        try:
            response = client.get(form_page)
        except httpx.HTTPError:
            return _result(Status.INCONCLUSIVE, f"Target could not be reached at {form_page}.")
        issue = _response_issue(response, form_page)
        if issue:
            return issue
        if "html" not in response.headers.get("content-type", "").lower():
            return _result(Status.INCONCLUSIVE, "Stored-XSS form page did not return HTML.")
        forms = stored_xss._discover_forms(client, [form_page])
        if not any(a == action and m == method and list(f) == fields for a, m, f in forms):
            return _result(Status.INCONCLUSIVE, "The recorded stored-XSS form is no longer available.")
        marker = stored_xss._marker()
        payload = {name: stored_xss._probe(marker) for name in fields}
        try:
            submitted = (client.post(action, data=payload) if method == "post"
                         else client.get(action, params=payload))
        except httpx.HTTPError:
            return _result(Status.INCONCLUSIVE, "Stored-XSS form submission failed.")
        issue = _response_issue(submitted, action)
        if issue:
            return issue
        if submitted.status_code >= 400:
            return _result(Status.INCONCLUSIVE, "Stored-XSS form submission was rejected.")
        try:
            rendered = client.get(page)
        except httpx.HTTPError:
            return _result(Status.INCONCLUSIVE, f"Target could not be reached at {page}.")
        issue = _response_issue(rendered, page)
        if issue:
            return issue
        if "html" not in rendered.headers.get("content-type", "").lower():
            return _result(Status.INCONCLUSIVE, "Stored-XSS display page did not return HTML.")
        vulnerable = stored_xss._is_unescaped(rendered.text, marker)
    finally:
        client.close()
    if vulnerable:
        return _result(Status.REPRODUCED, f"Submitted input remains unescaped at {page}.")
    return _result(Status.NOT_REPRODUCED, f"Submitted input is escaped or absent at {page}.")


def _stored_rendered(finding: Finding, cfg: Config, sandbox: Sandbox,
                     form_page: str, page: str, action: str, fields: list[str], method: str):
    if finding.repro.get("login") is True:
        if not cfg.users:
            return _result(Status.INCONCLUSIVE, "Stored-XSS replay requires configured login credentials.")
        user = cfg.users[0]
        client = httpx.Client(base_url=sandbox.base_url.rstrip("/"), timeout=8.0,
                              follow_redirects=True)
        try:
            authenticated = stored_xss._do_login(client, user.email, user.password)
            has_cookies = bool(client.cookies)
        except Exception as exc:  # noqa: BLE001 - login setup failure is inconclusive
            client.close()
            return _result(Status.INCONCLUSIVE, f"Stored-XSS login failed ({type(exc).__name__}).")
        if not authenticated or not has_cookies:
            client.close()
            return _result(Status.INCONCLUSIVE, "Configured login did not provide browser-compatible cookies.")
    elif finding.repro.get("login") is False:
        client = None
    else:
        return _result(Status.INCONCLUSIVE, "Stored-XSS repro is missing its login requirement.")

    renderer, error = _browser_renderer(sandbox)
    if error:
        if client:
            client.close()
        return error
    try:
        if client:
            renderer.add_cookies_from_httpx(client)
            client.close()
        _html, nav_error = _browser_get(renderer, form_page)
        if nav_error:
            return _result(Status.INCONCLUSIVE, nav_error)
        forms = renderer.find_forms()
        matches = [(i, form) for i, form in enumerate(forms)
                   if form.get("action") == finding.repro.get("action")
                   and form.get("method", "post").lower() == method
                   and form.get("fields") == fields]
        if not matches:
            return _result(Status.INCONCLUSIVE, "The recorded rendered form is no longer available.")
        form_index, _form_data = matches[0]
        marker = stored_xss._marker()
        action_statuses = []

        def record_action_response(response):
            if urlsplit(response.url).path == action:
                action_statuses.append(response.status)

        renderer.page.on("response", record_action_response)
        try:
            form = renderer.page.locator("form").nth(form_index)
            for name in fields:
                field = form.locator(f'[name="{name}"]')
                if field.count() == 0:
                    return _result(Status.INCONCLUSIVE, f"Recorded form field {name} is unavailable.")
                field.fill(stored_xss._probe(marker))
            submit = form.locator('button[type="submit"], input[type="submit"], button').first
            if submit.count():
                submit.click(timeout=5000)
            else:
                first_field = form.locator(f'[name="{fields[0]}"]')
                first_field.press("Enter", timeout=5000)
            renderer.page.wait_for_timeout(250)
        except Exception as exc:  # noqa: BLE001 - failed form interaction is inconclusive
            return _result(Status.INCONCLUSIVE, f"Stored-XSS form submission failed ({type(exc).__name__}).")
        finally:
            renderer.page.remove_listener("response", record_action_response)
        if not action_statuses:
            return _result(Status.INCONCLUSIVE, "Stored-XSS submission produced no response for its recorded action.")
        if any(status >= 500 for status in action_statuses):
            return _result(Status.INCONCLUSIVE, "Stored-XSS submission returned a server error.")
        if not any(status < 400 for status in action_statuses):
            return _result(Status.INCONCLUSIVE, "Stored-XSS submission was rejected.")
        html, nav_error = _browser_get(renderer, page)
        if nav_error:
            return _result(Status.INCONCLUSIVE, nav_error)
        vulnerable = stored_xss._is_unescaped(html, marker)
    finally:
        renderer.close()
    if vulnerable:
        return _result(Status.REPRODUCED, f"Submitted input remains unescaped in rendered DOM at {page}.")
    return _result(Status.NOT_REPRODUCED, f"Submitted input is escaped or absent from rendered DOM at {page}.")


def _stored_xss(finding: Finding, cfg: Config, sandbox: Sandbox) -> VerificationResult:
    details = _form_repro(finding.repro)
    if isinstance(details, VerificationResult):
        return details
    form_page, page, action, fields = details
    method = finding.repro["method"]
    if finding.repro.get("rendered") is True:
        return _stored_rendered(finding, cfg, sandbox, form_page, page, action, fields, method)
    if finding.repro.get("rendered") is False:
        return _stored_http(finding, cfg, sandbox, form_page, page, action, fields, method)
    return _result(Status.INCONCLUSIVE, "Stored-XSS repro is missing its rendering mode.")


def verify_finding(finding: Finding, cfg: Config, sandbox: Sandbox) -> VerificationResult:
    """Replay one recorded repro and report reproduced, not reproduced, or inconclusive."""
    repro = finding.repro
    kind = repro.get("type")
    if not repro or not isinstance(kind, str):
        return _result(Status.INCONCLUSIVE, "Finding has no supported machine-readable repro spec.")
    if kind == "stored_xss":
        return _stored_xss(finding, cfg, sandbox)
    path = repro.get("path")
    if not _local_path(path):
        return _result(Status.INCONCLUSIVE, "Repro spec has no supported local path.")
    if kind == "header":
        return _headers(finding, sandbox)
    if kind == "missing_auth":
        return _missing_auth(finding, sandbox)
    if kind == "idor":
        return _idor(finding, cfg, sandbox)
    if kind == "same_data":
        return _same_data(finding, cfg, sandbox)
    if kind == "reflected":
        return _reflected(finding, sandbox)
    if kind == "sqli_get":
        return _sqli_get(finding, sandbox)
    if kind == "sqli_login":
        return _sqli_login(finding, sandbox)
    return _result(Status.INCONCLUSIVE, f"Unsupported repro type: {kind}.")
