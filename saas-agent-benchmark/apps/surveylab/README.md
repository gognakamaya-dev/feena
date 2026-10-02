# SurveyLab

Survey builder with public response collection and analytics.

This is a synthetic benchmark application. It is a small, early-stage product with imperfect production code;
the intended behaviour is whatever a reasonable product of this kind should do.

- Frontend: open `http://127.0.0.1:9114/` (sign in with a demo account).
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
| GET | `/api/surveys` | any signed-in user |  |
| POST | `/api/surveys` | admin, member |  |
| POST | `/api/surveys/<id>/questions` | admin, member |  |
| POST | `/api/surveys/<id>/launch` | admin, member |  |
| POST | `/api/surveys/<id>/close` | admin, member |  |
| POST | `/api/public/surveys/<id>/responses` | public | Public submission: {token, answers: {question_id: value}}. |
| GET | `/api/surveys/<id>/analytics` | any signed-in user |  |
| GET | `/api/surveys/<id>/ratings` | any signed-in user | Raw rating answers for the survey's rating questions. |

## Reset

`POST /__benchmark/reset` with header `X-Benchmark-Key: <BENCH_KEY>` (default `benchmark-local`) restores the database and seed data.

## Run

```bash
python -m common.run surveylab            # from the repository root; port 9114
```
