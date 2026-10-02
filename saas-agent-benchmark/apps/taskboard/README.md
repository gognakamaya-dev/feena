# TaskBoard

Team project and task management with owners, members and subtasks.

This is a synthetic benchmark application. It is a small, early-stage product with imperfect production code;
the intended behaviour is whatever a reasonable product of this kind should do.

- Frontend: open `http://127.0.0.1:9102/` (sign in with a demo account).
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
| GET | `/api/projects` | any signed-in user |  |
| POST | `/api/projects` | admin, member |  |
| POST | `/api/projects/<id>/members` | admin, member |  |
| POST | `/api/projects/<id>/transfer` | admin, member | Transfer project ownership to an existing member. |
| POST | `/api/projects/<id>/archive` | admin, member |  |
| GET | `/api/projects/<id>/tasks` | any signed-in user |  |
| POST | `/api/projects/<id>/tasks` | admin, member |  |
| PATCH | `/api/tasks/<id>` | any signed-in user |  |
| DELETE | `/api/tasks/<id>` | admin, member |  |
| POST | `/api/tasks/<id>/comments` | admin, member |  |
| GET | `/api/projects/<id>/stats` | any signed-in user |  |

## Reset

`POST /__benchmark/reset` with header `X-Benchmark-Key: <BENCH_KEY>` (default `benchmark-local`) restores the database and seed data.

## Run

```bash
python -m common.run taskboard            # from the repository root; port 9102
```
