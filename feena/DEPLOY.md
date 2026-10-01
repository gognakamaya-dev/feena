# Private hosted workspace

## Deploy the first Render pilot

The root `render.yaml` provisions **one paid 1 CPU / 2 GB web service and a 1 GB disk**.
Review Render's current price before approving. No resources are created just by opening
the setup link. This is a disposable-demo pilot, not a customer-app deployment.

1. Sign in to Render and open the deployment link in the root README.
2. If asked, connect GitHub and grant Render access only to this repository.
3. Review the Blueprint, service plan, disk, and price, then approve deployment.
4. When the service is **Live**, open its `https://….onrender.com` address.
5. In the service's **Environment** page, reveal and copy `FEENA_MCP_TOKEN` privately.
   Paste it into Feena's workspace-key box, click **Check connection**, then **Add to Cursor**.
   Do not send the key or the resulting installation link in chat.
6. Ask Cursor to list the tests, then run `retry-checkout`. Its four profiles should pass.
   `broken-idempotency` deliberately demonstrates a failing journey; it is not a deployment error.

Render generates the key and provides the hostname. The pilot launcher derives the public MCP
URL and exact host allowlist from `RENDER_EXTERNAL_HOSTNAME`; no manual URL configuration is
needed. Custom domains are not supported by this pilot launcher. The demo uses a single
Gunicorn worker, listens only on loopback, simulates payments, and resets its data on restart.
Only the authenticated MCP API can invoke its prepared journeys. The onboarding and health
pages are public. The launcher stops both processes if either exits, so Render can restart them.

Evidence stays on the private disk under `/app/data/runs`, with no public download route.
Job status is in memory and disappears on restart. The operator should inspect disk usage
weekly and delete demo evidence older than seven days through Render's private service shell;
automatic retention is not included. Archive needed evidence before deleting it. The disk must
be writable by container UID 10001; startup fails immediately if it is not. Never store customer
data in this demo. Keep one instance; disk-backed deploys have downtime and interrupt active runs.

Auto-deploy is disabled. Deploy updates manually after checks pass and no run is active.
For rollback, redeploy the previous working commit with its matching settings; the disk is
preserved, but job status is not. Rotate the key in Render's Environment page and restart;
then reinstall the Cursor connection. No provider API key or Docker socket is needed.

This repository configuration does not create a live Render service by itself. The account
owner must approve billing and repository access. Validate a hosted run and cancellation before
inviting a pilot user. Each customer needs a separate service, key, disk, and prepared test target;
do not share this demo deployment across customers.

Reference: [Render Blueprints](https://render.com/docs/blueprint-spec),
[persistent disks](https://render.com/docs/disks), and
[default environment variables](https://render.com/docs/environment-variables).

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
access for Python dependencies and Chromium. Use one replica: job state is process-local.

Configure these secrets/settings at your hosting provider:

| Setting | Value |
| --- | --- |
| `FEENA_MCP_TOKEN` | Random secret, at least 32 characters; share privately with authorized users |
| `FEENA_MCP_PUBLIC_URL` | Stable HTTPS endpoint, e.g. `https://qa.example.com/mcp` |
| `FEENA_MCP_HOSTS` | Exact public hostname, e.g. `qa.example.com` |

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
credentials. Current limits: one active run, 120 seconds per run, 100 runs per process lifetime.
Restarting loses job status; it does not delete evidence. This is a pilot, not unattended
multi-tenant production infrastructure.

## Before inviting users

- Confirm HTTPS, Host allowlist, token rejection, and health checks.
- Open the onboarding page; verify a wrong key fails and the correct key enables installation.
- Connect from Cursor desktop and run an approved journey against disposable data.
- Confirm cancellation and inspect the resulting traces privately.
- Rotate the workspace key by changing the secret and restarting if a key or install link leaks.

Cursor's install-link format: https://cursor.com/docs/mcp/install-links
