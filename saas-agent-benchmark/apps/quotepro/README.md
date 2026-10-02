# QuotePro

Quotation and proposal generation with catalog items, optional add-ons, tiered discounts and public acceptance links.

This is a synthetic benchmark application. It is a small, early-stage product with imperfect production code;
the intended behaviour is whatever a reasonable product of this kind should do.

- Frontend: open `http://127.0.0.1:9118/` (sign in with a demo account).
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
| GET | `/api/catalog` | any signed-in user |  |
| GET | `/api/quotes` | any signed-in user |  |
| GET | `/api/quotes/<id>` | any signed-in user |  |
| POST | `/api/quotes` | admin, member |  |
| POST | `/api/quotes/<id>/select` | admin, member |  |
| POST | `/api/quotes/<id>/send` | admin, member |  |
| POST | `/api/quotes/<id>/revise` | admin, member | Create a new draft revision of a sent quote; the old one is superseded. |
| POST | `/api/public/quotes/<token>/accept` | public |  |

## Reset

`POST /__benchmark/reset` with header `X-Benchmark-Key: <BENCH_KEY>` (default `benchmark-local`) restores the database and seed data.

## Run

```bash
python -m common.run quotepro            # from the repository root; port 9118
```
