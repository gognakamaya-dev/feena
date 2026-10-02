# AssetManager

Digital asset management: folders, tags, soft-delete/restore, storage quota and expiring share links.

This is a synthetic benchmark application. It is a small, early-stage product with imperfect production code;
the intended behaviour is whatever a reasonable product of this kind should do.

- Frontend: open `http://127.0.0.1:9116/` (sign in with a demo account).
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
| GET | `/api/assets` | any signed-in user |  |
| POST | `/api/assets` | admin, member | Register an uploaded asset's metadata. |
| GET | `/api/assets/<id>` | any signed-in user |  |
| PATCH | `/api/assets/<id>` | admin, member | Move an asset to another folder ({folder_id}) or rename it ({name}). |
| DELETE | `/api/assets/<id>` | admin, member |  |
| POST | `/api/assets/<id>/restore` | admin, member |  |
| POST | `/api/assets/<id>/tags` | admin, member |  |
| POST | `/api/assets/<id>/share` | admin, member |  |
| POST | `/api/shares/<id>/revoke` | admin, member |  |
| GET | `/api/public/share/<token>` | public |  |
| GET | `/api/storage` | any signed-in user |  |

## Reset

`POST /__benchmark/reset` with header `X-Benchmark-Key: <BENCH_KEY>` (default `benchmark-local`) restores the database and seed data.

## Run

```bash
python -m common.run assetmanager            # from the repository root; port 9116
```
