# SaaS Agent Benchmark

Twenty small, realistic multi-tenant SaaS products with deliberately planted bugs, for evaluating autonomous
testing agents. Each app has a vanilla-JS frontend, a JSON API, SQLite persistence, session auth, seed data, and a
deterministic clock (2026-03-15 10:00 UTC), so a reset always gives an identical starting state. Only the Python
standard library (plus Node for frontend-hook tests, and pytest for development) is needed.

## Applications and planted bugs

| Application | id | Port | Bugs |
|---|---|---|---|
| InvoiceFlow | `invoiceflow` | 9101 | 6 |
| TaskBoard | `taskboard` | 9102 | 6 |
| FormStacker | `formstacker` | 9103 | 6 |
| Bookly | `bookly` | 9104 | 6 |
| StockPilot | `stockpilot` | 9105 | 6 |
| SupportDesk | `supportdesk` | 9106 | 6 |
| MailForge | `mailforge` | 9107 | 6 |
| ExpenseTrack | `expensetrack` | 9108 | 6 |
| TeamPulse | `teampulse` | 9109 | 6 |
| ClientHub | `clienthub` | 9110 | 6 |
| EventPilot | `eventpilot` | 9111 | 6 |
| CourseCloud | `coursecloud` | 9112 | 6 |
| ContractVault | `contractvault` | 9113 | 6 |
| SurveyLab | `surveylab` | 9114 | 6 |
| RecruitFlow | `recruitflow` | 9115 | 6 |
| AssetManager | `assetmanager` | 9116 | 6 |
| TimeTrack | `timetrack` | 9117 | 6 |
| QuotePro | `quotepro` | 9118 | 6 |
| AnalyticsHub | `analyticshub` | 9119 | 6 |
| SubscriptionPilot | `subscriptionpilot` | 9120 | 6 |

**120 bugs** — difficulty 36 easy / 48 medium / 24 hard / 12 very hard (30/40/20/10 %). Categories:
backend 29, business_logic 46, database 6, frontend 20, security 19. All 36 hard and very-hard bugs need multi-step, stateful workflows
(create → modify → change permissions/state → observe); many other bugs depend on boundary values, empty values, repeated
actions, different roles, ordering, time/date boundaries or cross-tenant access. Security bugs are local-only logic flaws.

## Start everything

```bash
./scripts/start_all.sh          # python3 -m common.run <id> for all 20 apps on ports 9101-9120 (logs/pids in .run/)
./scripts/stop_all.sh
# or: docker compose up --build   (images hold only common/ and apps/ — no tests, no manifests)
```

## Reset

- One app: `POST /__benchmark/reset` with header `X-Benchmark-Key: $BENCH_KEY` (default `benchmark-local`).
- All apps: `./scripts/reset_all.sh [app_id ...]`. The reset recreates the SQLite file and re-seeds it.

Reproducible loop: `reset → run agent → save report → reset → run next agent → scripts/evaluate.py`.

## How an agent connects

`benchmark/apps.json` is the registry: for each app it lists `id`, `base_url`, `health_url`, `docs_url` (`GET /api/docs`),
`login_url`, demo credentials (admin/member/viewer in org "Acme", admin/member in org "Globex"; password `demo123`), the
reset call, and the app README. Log in with `POST /api/auth/login` and send `Authorization: Bearer <token>`; the
frontend is served at `/`. Give agents `benchmark/apps.json` and the running URLs only — **do not expose
`benchmark/manifests/`, `apps/*/tests` (test names contain bug ids) or the source** if you want a black-box evaluation.

## Agent report format and evaluator

Agents write one JSON per app (`benchmark/schemas/agent_report.schema.json`):

```json
{"application": "invoiceflow", "bugs_found": [{"title": "...", "severity": "high", "category": "business_logic",
  "description": "...", "reproduction_steps": ["..."], "expected": "...", "actual": "...", "evidence": ["..."],
  "discovered_at_seconds": 123}]}
```

`discovered_at_seconds` is optional and drives the time-to-discovery metrics.

```bash
python scripts/evaluate.py --reports reports/ --output results.json
```

`reports/` may be one file, a directory of per-app reports, or `reports/<agent>/<app>.json` for several agents (compared side by
side). Output: bugs discovered/missed, false positives, duplicates, precision, recall, severity-weighted recall, time to
first and per-bug discovery, coverage by category and difficulty, and reproduction accuracy. Reports are matched to
manifest bugs one-to-one with IDF-weighted lexical overlap (threshold `--threshold`, default 0.25); for rigorous grading
supply your own adjudication with `--matches matches.json` (`{agent: {app_id: {report_index: bug_id}}}`).
Treat automatic matching as a first pass.

## Validate the benchmark itself

```bash
python scripts/check_apps.py     # rebuilds manifests; asserts failing correct-behaviour tests == manifest bugs
python -m pytest benchmark       # evaluator tests
```

Each `apps/<id>/tests/` file contains happy-path tests (pass) and one `test_<PREFIX>_<NNN>_...` test per planted bug,
asserting the *correct* behaviour (fails on the shipped app, passes once fixed).

## Add an application or bug

1. Create `apps/<id>/` with `app.py` (`app = App(id, name, port, SCHEMA, seed, static_dir=...)` and `@app.route` handlers),
   `static/app.js` (`window.APP_CONFIG` with tabs and `hooks`), and `tests/test_<id>.py`.
2. Add `benchmark/manifest_src/<id>.py` (`APP`, `PREFIX`, `BUGS=[B(...)]`, 5–10 bugs).
3. Add the id to `IDS` in `scripts/generate.py`; run `python scripts/generate.py` (apps.json, docker-compose, READMEs) and
   `python scripts/check_apps.py`.
4. New bug in an existing app: change the behaviour, add a `test_<PREFIX>_<NNN>_*` test for the correct behaviour and a `B(...)`
   manifest entry, then rerun the check.
