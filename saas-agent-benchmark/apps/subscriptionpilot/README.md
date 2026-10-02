# SubscriptionPilot

Subscription billing: plans, trials, coupons, plan changes with proration, cancellations and renewals.

This is a synthetic benchmark application. It is a small, early-stage product with imperfect production code;
the intended behaviour is whatever a reasonable product of this kind should do.

- Frontend: open `http://127.0.0.1:9120/` (sign in with a demo account).
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
| GET | `/api/plans` | any signed-in user |  |
| GET | `/api/subscriptions` | any signed-in user |  |
| GET | `/api/subscriptions/<id>` | any signed-in user |  |
| POST | `/api/subscriptions` | admin, member |  |
| POST | `/api/subscriptions/<id>/cancel` | admin, member |  |
| POST | `/api/subscriptions/<id>/change-plan` | admin, member | Switch plan ({plan_id, effective_on?}); upgrades are charged pro rata for the rest of the period. |
| POST | `/api/jobs/renew` | admin | Billing run: renew or cancel subscriptions whose period ended on or before ?as_of (default today). |
| GET | `/api/reports/mrr` | admin |  |

## Reset

`POST /__benchmark/reset` with header `X-Benchmark-Key: <BENCH_KEY>` (default `benchmark-local`) restores the database and seed data.

## Run

```bash
python -m common.run subscriptionpilot            # from the repository root; port 9120
```
