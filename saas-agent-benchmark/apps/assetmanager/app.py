import datetime as dt
import secrets
from pathlib import Path

from common.framework import App, HttpError, created

SCHEMA = """
CREATE TABLE folders(id INTEGER PRIMARY KEY, org_id INT, name TEXT);
CREATE TABLE assets(id INTEGER PRIMARY KEY, org_id INT, folder_id INT REFERENCES folders(id), name TEXT, mime TEXT, size_bytes INT, owner_id INT, created_at TEXT, deleted_at TEXT);
CREATE TABLE tags(asset_id INT REFERENCES assets(id), tag TEXT, PRIMARY KEY(asset_id,tag));
CREATE TABLE shares(id INTEGER PRIMARY KEY, asset_id INT REFERENCES assets(id), token TEXT UNIQUE, expires_at TEXT, revoked INT DEFAULT 0);
"""
MAX_SIZE = 50 * 1024 * 1024
MIME = {"png": "image/png", "jpg": "image/jpeg", "pdf": "application/pdf", "mp4": "video/mp4", "svg": "image/svg+xml"}


def seed(db):
    for i, n in enumerate(["Brand", "Campaigns", "Product shots"], 1):
        db.exec("INSERT INTO folders VALUES(?,1,?)", (i, n))
    db.exec("INSERT INTO folders VALUES(4,2,'Globex Private')")
    files = [("logo.svg", 12_000, 1), ("hero.png", 2_400_000, 2), ("brand-guide.pdf", 8_000_000, 1), ("promo.mp4", 40_000_000, 2), ("shot-01.jpg", 3_100_000, 3), ("shot-02.jpg", 3_300_000, 3)]
    for i, (n, sz, f) in enumerate(files, 1):
        db.exec("INSERT INTO assets VALUES(?,?,?,?,?,?,1,'2026-03-01',NULL)", (i, 1, f, n, MIME[n.rsplit(".", 1)[1]], sz))
    db.exec("INSERT INTO tags VALUES(1,'brand')")
    db.exec("INSERT INTO tags VALUES(2,'campaign')")
    db.exec("INSERT INTO assets VALUES(7,2,4,'secret-plan.pdf','application/pdf',500000,4,'2026-03-01',NULL)")


app = App("assetmanager", "AssetManager", 9116, SCHEMA, seed, static_dir=Path(__file__).parent / "static",
          description="Digital asset management: folders, tags, soft-delete/restore, storage quota and expiring share links.")


@app.route("GET", "/api/assets")
def assets(ctx):
    sql, args = "SELECT * FROM assets a WHERE org_id=? AND deleted_at IS NULL", [ctx.user["org_id"]]
    if ctx.query.get("folder_id"):
        sql += " AND folder_id=?"
        args.append(ctx.query["folder_id"])
    if ctx.query.get("tag"):
        sql += " AND EXISTS(SELECT 1 FROM tags t WHERE t.asset_id=a.id AND t.tag=?)"
        args.append(ctx.query["tag"])
    if ctx.query.get("q"):
        sql += " AND name LIKE ?"
        args.append("%" + ctx.query["q"] + "%")
    return ctx.page(sql + " ORDER BY id", args)


@app.route("POST", "/api/assets", roles=["admin", "member"])
def add_asset(ctx):
    """Register an uploaded asset's metadata."""
    name, size, folder = ctx.need("name", "size_bytes", "folder_id")
    ctx.get("folders", folder)
    ext = name.rsplit(".", 1)[-1].lower()
    if ext not in MIME:
        raise HttpError(400, "unsupported file type")
    if ctx.one("SELECT 1 FROM assets WHERE folder_id=? AND name=? AND deleted_at IS NULL", (folder, name)):
        raise HttpError(409, "an asset with this name already exists in the folder")
    aid = ctx.exec("INSERT INTO assets VALUES(NULL,?,?,?,?,?,?,?,NULL)", (ctx.user["org_id"], folder, name, MIME[ext], size, ctx.user["id"], ctx.now))
    return created(ctx.get("assets", aid))


@app.route("GET", "/api/assets/<id>")
def get_asset(ctx):
    a = ctx.get("assets", ctx.params["id"])
    a["tags"] = [t["tag"] for t in ctx.q("SELECT tag FROM tags WHERE asset_id=?", [a["id"]])]
    return a


@app.route("PATCH", "/api/assets/<id>", roles=["admin", "member"])
def move_asset(ctx):
    """Move an asset to another folder ({folder_id}) or rename it ({name})."""
    a = ctx.get("assets", ctx.params["id"])
    if "folder_id" in ctx.body:
        ctx.get("folders", ctx.body["folder_id"])
        ctx.exec("UPDATE assets SET folder_id=? WHERE id=?", (ctx.body["folder_id"], a["id"]))
    if "name" in ctx.body:
        ctx.exec("UPDATE assets SET name=? WHERE id=?", (ctx.body["name"], a["id"]))
    return ctx.get("assets", a["id"])


@app.route("DELETE", "/api/assets/<id>", roles=["admin", "member"])
def delete_asset(ctx):
    a = ctx.get("assets", ctx.params["id"])
    ctx.exec("UPDATE assets SET deleted_at=? WHERE id=?", (ctx.now, a["id"]))
    return {"ok": True}


@app.route("POST", "/api/assets/<id>/restore", roles=["admin", "member"])
def restore(ctx):
    a = ctx.get("assets", ctx.params["id"])
    ctx.exec("UPDATE assets SET deleted_at=NULL WHERE id=?", [a["id"]])
    return ctx.get("assets", a["id"])


@app.route("POST", "/api/assets/<id>/tags", roles=["admin", "member"])
def tag(ctx):
    a = ctx.get("assets", ctx.params["id"])
    ctx.exec("INSERT OR IGNORE INTO tags VALUES(?,?)", (a["id"], ctx.need("tag")[0].strip().lower()))
    return created({"ok": True})


@app.route("POST", "/api/assets/<id>/share", roles=["admin", "member"])
def share(ctx):
    a = ctx.get("assets", ctx.params["id"])
    days = int(ctx.body.get("expires_in_days", 7))
    exp = (dt.datetime.fromisoformat(ctx.now) + dt.timedelta(days=days)).isoformat(timespec="seconds")
    tok = secrets.token_urlsafe(12)
    sid = ctx.exec("INSERT INTO shares VALUES(NULL,?,?,?,0)", (a["id"], tok, exp))
    return created({"id": sid, "token": tok, "expires_at": exp})


@app.route("POST", "/api/shares/<id>/revoke", roles=["admin", "member"])
def revoke(ctx):
    s = ctx.one("SELECT s.* FROM shares s JOIN assets a ON a.id=s.asset_id WHERE s.id=? AND a.org_id=?", (ctx.params["id"], ctx.user["org_id"]))
    if not s:
        raise HttpError(404, "share not found")
    ctx.exec("UPDATE shares SET revoked=1 WHERE id=?", [s["id"]])
    return {"ok": True}


@app.route("GET", "/api/public/share/<token>", auth=False)
def public_share(ctx):
    s = ctx.one("SELECT * FROM shares WHERE token=?", [ctx.params["token"]])
    if not s or s["expires_at"] <= ctx.now:
        raise HttpError(404, "link not found or expired")
    return ctx.one("SELECT name, mime, size_bytes FROM assets WHERE id=?", [s["asset_id"]])


@app.route("GET", "/api/storage")
def storage(ctx):
    used = ctx.one("SELECT COALESCE(SUM(size_bytes),0) AS n FROM assets WHERE org_id=?", [ctx.user["org_id"]])["n"]
    return {"used_bytes": used, "quota_bytes": 1024 ** 3}
