# InvoiceFlow

Invoicing and payment tracking for small agencies.

This is a synthetic benchmark application. It is a small, early-stage product with imperfect production code;
the intended behaviour is whatever a reasonable product of this kind should do.

- Frontend: open `http://127.0.0.1:9101/` (sign in with a demo account).
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
| GET | `/api/customers` | any signed-in user | List active customers. |
| POST | `/api/customers` | admin, member |  |
| DELETE | `/api/customers/<id>` | admin | Soft-delete a customer. |
| GET | `/api/invoices` | any signed-in user | List invoices, optional ?status= filter, paginated. |
| POST | `/api/invoices` | admin, member |  |
| GET | `/api/invoices/<id>` | any signed-in user |  |
| POST | `/api/invoices/<id>/send` | admin, member |  |
| POST | `/api/invoices/<id>/payments` | admin, member | Record a payment (optional paid_on date). |
| POST | `/api/invoices/<id>/payments/<pid>/refund` | admin |  |
| POST | `/api/invoices/<id>/void` | admin |  |
| GET | `/api/reports/revenue` | admin | Collected revenue for ?month=YYYY-MM (net of refunds). |

## Reset

`POST /__benchmark/reset` with header `X-Benchmark-Key: <BENCH_KEY>` (default `benchmark-local`) restores the database and seed data.

## Run

```bash
python -m common.run invoiceflow            # from the repository root; port 9101
```
