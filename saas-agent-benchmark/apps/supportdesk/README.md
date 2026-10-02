# SupportDesk

Customer support ticketing with internal notes and SLA tracking. Viewers act as customers.

This is a synthetic benchmark application. It is a small, early-stage product with imperfect production code;
the intended behaviour is whatever a reasonable product of this kind should do.

- Frontend: open `http://127.0.0.1:9106/` (sign in with a demo account).
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
| GET | `/api/tickets` | any signed-in user |  |
| POST | `/api/tickets` | any signed-in user |  |
| GET | `/api/tickets/<id>` | any signed-in user |  |
| POST | `/api/tickets/<id>/replies` | any signed-in user |  |
| POST | `/api/tickets/<id>/assign` | admin, member |  |
| POST | `/api/tickets/<id>/status` | admin, member |  |
| GET | `/api/reports/summary` | admin, member |  |

## Reset

`POST /__benchmark/reset` with header `X-Benchmark-Key: <BENCH_KEY>` (default `benchmark-local`) restores the database and seed data.

## Run

```bash
python -m common.run supportdesk            # from the repository root; port 9106
```
