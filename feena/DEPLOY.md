# Private hosted workspace

## What your users do

1. Open your Feena website.
2. Paste the workspace access key you gave them.
3. Click **Check connection**, then **Add to Cursor** and approve installation.
4. Ask Cursor: “Show me the available Feena tests.”

They do not install Python, run a terminal, or edit JSON. Cursor desktop must already be
installed. The installation link contains their access key: never share it or commit the
resulting Cursor configuration. This first release uses a shared workspace key, not individual
accounts. Use it only with a trusted team.

## One-time administrator setup

The repository includes a Dockerfile for a Linux container host. This is deployment preparation,
not a claim that a production service has been provisioned. The container build needs internet
access for Python dependencies and Chromium. Use one Linux service replica per campaign store; an exclusive lock rejects a second owner.

Configure these secrets/settings at your hosting provider:

| Setting | Value |
| --- | --- |
| `FEENA_MCP_TOKEN` | Random secret, at least 32 characters; share privately with authorized users |
| `FEENA_MCP_PUBLIC_URL` | Stable HTTPS endpoint, e.g. `https://qa.example.com/mcp` |
| `FEENA_MCP_HOSTS` | Exact public hostname, e.g. `qa.example.com` |
| `FEENA_WORKSPACE_NAME` | Optional display label, e.g. `Acme QA` |
| `FEENA_ENVIRONMENT_NAME` | Optional display label, e.g. `Disposable staging checkout` |

The display labels and configured journey count are returned only after a valid workspace
key is supplied. Use human-readable labels, not internal URLs, paths, or secrets. A successful
key check does not confirm Cursor installation: users should add Feena, then ask Cursor to
list available tests using the copyable prompt on the page. The public sample result is an
illustration of the bundled broken checkout, not a live run. Visitors without a key can read
the hosting guide and inspect the example before asking their administrator for access.

Terminate HTTPS at the hosting provider and forward to port 3000. The health route is `/health`.
Do not configure the temporary Hoplite preview URL as the public installation URL. The onboarding
page deliberately disables installation until the stable public URL is configured.

Mount the prepared `feena.yaml` at `/config/feena.yaml` read-only. Supply container arguments:

```
--config /config/feena.yaml --target http://test-app:5055
```

The target must be an authorized disposable app on the server's private network. The hosted
service cannot reach a user's laptop through `localhost`. An administrator still needs to
connect that test environment and prepare its browser journeys. Arbitrary public-site testing,
automatic journey generation, self-service customer accounts, and OAuth are not included.

Mount private persistent storage at `/data` writable by the `feena` container user, and set
CPU/memory limits and a retention policy. Browser traces can contain sensitive data. Give the
container only network access to its test environment. Do not mount a Docker socket or provider
credentials. Campaign state and scenario snapshots persist in SQLite under the output directory.
Limits: 1–16 worker slots, 120 seconds per browser job, 100 jobs per campaign, and 1,000
jobs per store. Archive the complete store and use a new output directory when full. This is a pilot, not unattended
multi-tenant production infrastructure.

## Before inviting users

- Confirm HTTPS, Host allowlist, token rejection, and health checks.
- Open the onboarding page; verify a wrong key fails and the correct key enables installation.
- Connect from Cursor desktop and run an approved journey against disposable data.
- Confirm cancellation and inspect the resulting traces privately.
- Rotate the workspace key by changing the secret and restarting if a key or install link leaks.

Cursor's install-link format: https://cursor.com/docs/mcp/install-links


## Parallel campaigns

The MCP service now exposes `start_campaign(scenarios)`, `get_campaign(campaign_id)`, and
`cancel_campaign(campaign_id)`. Existing `start_run`, `get_run`, and `cancel_run` calls use
the same durable queue. Every configured scenario/profile pair becomes one browser job.
Campaigns execute configured journeys; autonomous discovery and hostile-agent scheduling
are not included in this release.

Provision independent disposable copies of your app and database, then repeat `--target`
once per worker slot (up to 16). Different URLs must not be aliases for the same backend:
Feena cannot detect shared databases. Each slot executes only one job at a time across all
campaigns. Provide a private same-origin POST reset endpoint using `--reset-path` if tests
do not isolate their own data. The reset endpoint must finish resetting and seeding data
before returning 2xx; redirects or failures prevent the browser job from running.
Reset hooks are operator configuration, never supplied through MCP.

```bash
feena-mcp --transport http --config /config/feena.yaml --out /data/campaigns \
  --target http://test-app-1:5055 --target http://test-app-2:5055 \
  --reset-path /test/reset
```

The example reset route must be implemented by your test app; the bundled checkout fixture
instead isolates order data with a fresh browser-session cookie. Do not expose reset routes
on a production app. The server still needs the HTTPS/token settings above.

Call `start_campaign` with, for example:

```json
{"scenarios": ["retry-checkout", "broken-idempotency", "offline-recovery"]}
```

Poll `get_campaign` using the returned ID. It reports per-job IDs, scenario/profile names,
status, and sanitized execution reasons. A campaign is `completed` only when all assertions
pass; `failed` means at least one definite assertion failure, and `inconclusive` means an
execution error, timeout, or interrupted job requires investigation. `queued`, `running`,
`cancelling`, and `cancelled` describe scheduling state. The legacy run API retains its
`completed` execution status and exposes individual assertion outcomes in `results`.

Raw worker results, scenario snapshots, traces, screenshots, and manifests remain under
`<out>/<job-id>/`; keep this directory private. Cancellation stops queued work and kills
active worker process groups before the slot can be reused. It does not roll back backend
writes. Configure a reset hook or use journeys that isolate their own data.

### Restart and recovery

Completed results and queued scenario snapshots survive restart. The store is bound to its
original target list and reset path; a different configuration requires a new store.
If shutdown interrupted active work, startup fails closed. First stop the previous service
and all orphan worker/browser processes (recreate its container where applicable), wait for
outstanding backend work to stop, and reset every target. Then restart once with
`--recover-interrupted` to acknowledge that cleanup. Interrupted jobs remain inconclusive;
only queued jobs resume. Remove the flag from normal startup configuration: it is an
operator acknowledgement, not automatic recovery or a substitute for process cleanup.

This is bounded parallel execution on one host, not multi-tenant or distributed hosting.


## Reviewed Cursor → browser → CI workflow (opt-in)

Enable `--enable-workflow --reset-path /test/reset` alongside the existing HTTPS/key/config
settings. This extends the service from fixed configured journeys to new explicitly reviewed
journeys. Use only a trusted team and a dedicated disposable environment. The reset endpoint
must synchronously restore each target's documented starting data before returning 2xx.

Open `/workspace` with the existing workspace key. Keys stay in page memory and are never put
in URLs. Drafts, approvals, runs and evidence downloads require authentication. The shared key
is still workspace-wide; approval is a review acknowledgement, not individual identity/audit
attribution. No OAuth or per-user roles have been added.

In Cursor:
1. Call `check_workspace_readiness` and `list_journeys`.
2. Ask the assistant to prepare a `JourneyProposal` from the goal and known app/API details,
   then call `submit_journey_proposal`. It must include setup, assumptions, and both UI and
   backend assertions. This tool saves a draft; it does not generate or execute code on the host.
3. Open the returned review link, inspect the full definition, and approve that exact version.
   Approval is a separate browser action; there is intentionally no MCP approval tool.
4. Click Run, or explicitly ask Cursor to call `run_journey` with that ID/version and a fresh
   request ID. Reuse the request ID after a transport failure to avoid duplicate campaigns.
5. Use `get_journey_run` and its authenticated results link to inspect profile statuses,
   expected outcomes, worker explanations, screenshots, action records, manifests and traces.
6. After a fix, call `rerun_journey`. It uses the original approved version and resets before
   each profile. A new proposal/revision needs separate approval. Cancellation does not undo writes.

A single service owns the SQLite store, including approvals and run provenance. Preserve the
whole output directory. Proposal definitions are immutable; revisions get new IDs. Maximum
200 proposals per store; existing campaign/worker limits still apply. Stdio clients receive
relative review URLs unless `FEENA_MCP_PUBLIC_URL` is configured; approvals require the HTTP UI.

Readiness checks executable presence and a bounded GET of each target root. It does not launch
Chromium, perform resets, or validate login credentials. A reachable login page is not proof
that a journey can authenticate. Unknown APIs and fixture assumptions still need operator review.

### PR checks using the same results page

The composite action in `feena/action.yml` accepts `workspace-url`, `workspace-journey`,
`workspace-version`, and `workspace-key`. Pass the key from GitHub Actions secrets, and pin the
Feena action to a reviewed commit. Hosted mode reuses the same approved runner and posts one
Feena comment with its authenticated results URL. `report-only` defaults to `true`; set it to
`false` once that suite has demonstrated reliable results. Request/authentication failures still
fail the job. The default idempotency ID includes the GitHub run, attempt, job, workspace and journey
version. For matrix jobs sharing those values or repeated identical invocations, set distinct
`workspace-request-id` inputs; reuse them only to retry a lost response.

**The workspace target must already be deployed to the commit under review.** This integration
does not provision or discover PR environments, bind target deployments to Git SHAs, or prevent
a deployment from changing mid-run. Use a dedicated workspace/isolated target per concurrent
PR. Do not use a shared mutable staging deployment as a merge gate. Do not expose workspace
secrets to fork PRs or use `pull_request_target` to execute untrusted checkout code.

A trusted CI job can also run:

```bash
# FEENA_WORKSPACE_KEY is supplied as a CI secret, not a command-line argument.
feena workflow-ci --endpoint https://qa.example.com --journey APPROVED_ID \
  --version APPROVED_DIGEST --request-id UNIQUE_CI_ATTEMPT --report-only --comment
```

Alternatively, download an approved config and commit it to your app repository. The existing
local Feena action can run it against a disposable app on the CI runner; that mode retains local
artifacts and does not create hosted results links. Restore the documented starting data first.

Evidence can contain credentials and page data. It is now downloadable by authorized workspace
key holders when workflow mode is enabled. The results page uses authenticated fetches; traces
remain downloads rather than an embedded third-party viewer. Apply retention and restrict the
workspace key to people authorized to see this evidence.

### First complete checkout pilot

Use the bundled `examples/workflow/checkout-proposal.json` as the proposal definition. In a
local disposable environment, start the checkout fixture with `FEENA_DEMO_RESET=1 python
examples/resilient-checkout/app.py`. Its `/test/reset` route is disabled unless this explicit
opt-in is set. Start Feena with the existing checkout config, that target, `--enable-workflow`,
and `--reset-path /test/reset`; use the previously documented HTTPS/token settings for HTTP.
Ask Cursor to submit this proposal, open its review link, approve, run, inspect the profile
results, and rerun. The proposal tests one order across normal, delayed, aborted, and lost
response profiles. This is a runnable pilot definition, not a claim that live browser tests
were executed in the implementation environment.
