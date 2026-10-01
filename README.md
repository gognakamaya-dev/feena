# Feena — realistic browser QA

Feena tests browser journeys under real-world conditions: retries, interrupted connections,
lost responses, offline recovery, and multiple tabs. It pairs visible outcomes with backend
assertions, records evidence, and exposes configured tests to coding assistants through MCP.

The application lives in [`feena/`](feena/).

- [Features, local setup, and examples](feena/README.md)
- [Hosted deployment and simple Cursor onboarding](feena/DEPLOY.md)
- [Retry-safe checkout demo](feena/examples/resilient-checkout/)

## Hosted demo on Render

[Deploy Feena to Render](https://render.com/deploy?repo=https%3A%2F%2Fgithub.com%2Fgognakamaya-dev%2Ffeena%2Ftree%2Fhoplite%2Fmassalia-94815731--render-pilot)

This creates a **paid** single-workspace pilot with a disposable checkout demo and private
evidence disk. Review the price in Render before approving. See the
[setup and access-key instructions](feena/DEPLOY.md#deploy-the-first-render-pilot).

```bash
cd feena
pip install -e '.[dev,mcp]'
playwright install --with-deps chromium
pytest -q
```

This is a single-workspace prototype, not yet autonomous user simulation or multi-tenant
production hosting. Hosted installation requires an operator-configured HTTPS service and
disposable test environment. Never commit access keys, traces, recordings, or production data.

The bundled vulnerable applications are deliberately insecure local testing fixtures.

## Upgrading from Mallory

The project is now Feena. Reinstall from `feena/` using the commands above; the Python package
and CLI commands are now `feena` and `feena-mcp`. Rename `mallory.yaml` to `feena.yaml` and
change your `MALLORY_*` environment variables to `FEENA_*` (including the MCP token, public
URL, and host allowlist). Update imports and scripts to the new names, and reinstall the
Cursor connection as Feena. Old command names and environment variables are not aliases.

New evidence is written under `.feena/`; existing `.mallory/` evidence is left untouched.
Keep both directories private and out of version control.
