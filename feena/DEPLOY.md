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
