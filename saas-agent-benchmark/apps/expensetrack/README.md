# ExpenseTrack

Expense reporting with receipts policy, approvals, reimbursements and budgets.

This is a synthetic benchmark application. It is a small, early-stage product with imperfect production code;
the intended behaviour is whatever a reasonable product of this kind should do.

- Frontend: open `http://127.0.0.1:9108/` (sign in with a demo account).
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
| GET | `/api/expenses` | any signed-in user |  |
| GET | `/api/expenses/<id>` | any signed-in user |  |
| POST | `/api/expenses` | admin, member |  |
| POST | `/api/expenses/<id>/submit` | admin, member |  |
| POST | `/api/expenses/<id>/approve` | admin |  |
| POST | `/api/expenses/<id>/reject` | admin |  |
| POST | `/api/expenses/<id>/reimburse` | admin |  |
| GET | `/api/reports/by-category` | admin | Approved + reimbursed spend per category for ?month=YYYY-MM. |
| GET | `/api/budgets/status` | admin | Committed spend (submitted, approved, reimbursed) vs monthly limit. |

## Reset

`POST /__benchmark/reset` with header `X-Benchmark-Key: <BENCH_KEY>` (default `benchmark-local`) restores the database and seed data.

## Run

```bash
python -m common.run expensetrack            # from the repository root; port 9108
```
