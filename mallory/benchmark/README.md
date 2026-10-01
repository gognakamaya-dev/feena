# Mallory benchmark

Run the hostile agent across many apps at once and get one aggregated report. This is the
month-one milestone: point Mallory at real open-source apps and see what it finds.

## The one rule

Every target is **cloned or pulled and run locally** inside a Mallory sandbox — a throwaway,
no-egress container. The harness never accepts a URL to a hosted instance. Test code you run
yourself, or apps you are authorised to test. Running a security tool against someone else's
live service without permission is unauthorised scanning; don't.

## Run it

```bash
# the bundled examples run with no Docker (kind: process)
mallory bench --only taskflow-example
mallory bench                      # runs everything in benchmark/targets.yaml

# one target
mallory bench --only owasp-juice-shop
```

Output: a table of every app with finding counts by severity, per-app detail, and a list of any
targets that could not be brought up. Written to `.mallory/benchmark.md`.

## The default targets

The default set is **intentionally-vulnerable apps published for security testing**, so they
have documented ground-truth bugs and are safe and legal to run locally:

- **OWASP Juice Shop** — the standard modern vulnerable app, broad OWASP Top 10 coverage.
- **OWASP NodeGoat** — Node/Express Top 10 demonstrator.
- **DVWA** — classic PHP training target.

Plus the bundled `taskflow-example` and `vuln-shop-example`, which run without Docker.

## Requirements

- `process` targets: none beyond Mallory itself.
- `image` and `repo` targets: a running Docker daemon, and network access to pull the image or
  clone the repo. In restricted environments (no daemon, or a registry allowlist) these targets
  report "could not be brought up" and the rest of the run continues.

## Adding your own apps

Append to `targets.yaml` (own-or-authorised only):

```yaml
  - name: my-nextjs-saas
    kind: repo
    repo: https://github.com/you/your-app.git
    ref: main
    port: 3000
    healthcheck: /api/health
    users:
      - {label: alice, email: alice@example.com, password: password123}
      - {label: bob,   email: bob@example.com,   password: password123}
```

## Interpreting results

For the OWASP apps, findings map to their documented vulnerability classes — that's your recall
signal against a set neither you nor we wrote. For your own apps, treat every confirmed finding
as reproducible (that's the guarantee) and start with the criticals.
