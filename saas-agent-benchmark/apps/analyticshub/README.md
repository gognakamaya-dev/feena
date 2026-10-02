# AnalyticsHub

Product analytics: event ingestion, counts, unique users, funnels and dashboards.

This is a synthetic benchmark application. It is a small, early-stage product with imperfect production code;
the intended behaviour is whatever a reasonable product of this kind should do.

- Frontend: open `http://127.0.0.1:9119/` (sign in with a demo account).
- API docs: `GET /api/docs`. Health: `GET /health`.
- Data: SQLite, deterministic seed data, fixed application clock (2026-03-15 10:00 UTC, a Sunday).
- Multi-tenant: two organisations. Users only ever belong to one.
- Money is in integer cents, dates are ISO-8601.

## Demo credentials

| Email | Password | Role | Organisation |
|---|---|---|---|
| admin@acme.test | `demo123` | admin | Acme Corp |
| member@acme.test | `demo123` | member | Acme Corp |
| viewer@acme.test | `demo123` | viewer | Acme Corp |
| admin@globex.test | `demo123` | admin | Globex Inc |
| member@globex.test | `demo123` | member | Globex Inc |

Log in with `POST /api/auth/login {"email","password"}`, then send `Authorization: Bearer <token>`.

## API

| Method | Path | Roles | Notes |
|---|---|---|---|
| POST | `/api/events` | admin, member |  |
| POST | `/api/events/batch` | admin, member |  |
| GET | `/api/metrics/count` | any signed-in user | Event count for ?event= between ?from= and ?to= (dates, both inclusive). |
| GET | `/api/metrics/unique-users` | any signed-in user |  |
| GET | `/api/metrics/funnel` | any signed-in user | Ordered funnel for ?steps=a,b,c: users who performed each step after the previous one. |
| GET | `/api/dashboards` | any signed-in user |  |
| POST | `/api/dashboards/<id>/widgets` | admin, member |  |
| GET | `/api/dashboards/<id>/data` | any signed-in user |  |
| GET | `/api/metrics/summary` | any signed-in user | Event counts by name. |

## Reset

`POST /__benchmark/reset` with header `X-Benchmark-Key: <BENCH_KEY>` (default `benchmark-local`) restores the database and seed data.

## Run

```bash
python -m common.run analyticshub            # from the repository root; port 9119
```
