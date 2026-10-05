"""CI client for an approved journey on an operator-configured workspace."""
import time
import re
from urllib.parse import urlsplit, urlunsplit

import httpx


def run_reviewed(endpoint, token, journey_id, version, request_id, timeout=300):
    parsed = urlsplit(endpoint)
    if (parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password
            or parsed.query or parsed.fragment or parsed.path not in ('', '/', '/mcp')):
        raise ValueError('Use a stable HTTPS workspace URL without credentials or query strings')
    if not re.fullmatch(r'[a-f0-9]{32}', journey_id) or not re.fullmatch(r'[a-f0-9]{64}', version):
        raise ValueError('Use the journey ID and exact version from the approved workspace proposal')
    if not token:
        raise ValueError('FEENA_WORKSPACE_KEY is required')
    origin = urlunsplit((parsed.scheme, parsed.netloc, '', '', ''))
    deadline = time.monotonic() + timeout
    with httpx.Client(base_url=origin, headers={'Authorization': 'Bearer '+token},
                      timeout=15, follow_redirects=False) as client:
        response = client.post(f'/workflow-api/journeys/{journey_id}/run',
                               json={'version': version, 'request_id': request_id})
        response.raise_for_status()
        result = response.json()
        while result['status'] in ('queued', 'running', 'cancelling'):
            if time.monotonic() >= deadline:
                # A CI timeout never implies cancellation or rollback of server-side writes.
                return {**result, 'ci_status': 'timed_out', 'ci_reason': 'Polling timed out; inspect the results link. The server run may still be active.'}
            time.sleep(min(2, max(0, deadline-time.monotonic())))
            response = client.get('/workflow-api/runs/'+result['campaign_id'])
            response.raise_for_status()
            result = response.json()
        return {**result, 'ci_status': result['status']}


def summary(result):
    # Keep raw page contents and worker evidence out of PR comments.
    status = result['ci_status']
    lines = ['## Feena reviewed journey', '', f'Status: **{status}**',
             f"Journey: `{result['journey_id']}`", f"Version: `{result['version']}`", '',
             f"[Open authenticated results]({result['results_url']})", '',
             'This tests the workspace’s configured target. The deployment must match the commit being reviewed.']
    if result.get('ci_reason'):
        lines += ['', result['ci_reason']]
    return '\n'.join(lines)+'\n'
