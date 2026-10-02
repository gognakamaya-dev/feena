# ContractVault

Contract lifecycle management: versions, approvals, signatures, expirations and renewals.

This is a synthetic benchmark application. It is a small, early-stage product with imperfect production code;
the intended behaviour is whatever a reasonable product of this kind should do.

- Frontend: open `http://127.0.0.1:9113/` (sign in with a demo account).
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
| GET | `/api/contracts` | any signed-in user |  |
| GET | `/api/contracts/<id>` | any signed-in user |  |
| POST | `/api/contracts` | admin, member |  |
| PUT | `/api/contracts/<id>` | admin, member |  |
| GET | `/api/contracts/<id>/versions` | any signed-in user |  |
| POST | `/api/contracts/<id>/request-approval` | admin, member |  |
| POST | `/api/contracts/<id>/approve` | admin, member |  |
| POST | `/api/contracts/<id>/sign` | admin |  |
| GET | `/api/reports/expiring` | admin, member | Signed contracts ending within ?days= (default 30), inclusive. |
| POST | `/api/jobs/expire` | admin | Expire signed contracts past end_date; auto-renew ones are extended by 12 months. |

## Reset

`POST /__benchmark/reset` with header `X-Benchmark-Key: <BENCH_KEY>` (default `benchmark-local`) restores the database and seed data.

## Run

```bash
python -m common.run contractvault            # from the repository root; port 9113
```
