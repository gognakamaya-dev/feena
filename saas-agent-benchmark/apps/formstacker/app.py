import json
from pathlib import Path

from common.framework import App, HttpError, created

SCHEMA = """
CREATE TABLE forms(id INTEGER PRIMARY KEY, org_id INT, title TEXT, slug TEXT UNIQUE, status TEXT DEFAULT 'draft',
  max_responses INT, closes_at TEXT);
CREATE TABLE fields(id INTEGER PRIMARY KEY, form_id INT REFERENCES forms(id), label TEXT, type TEXT, required INT DEFAULT 0, options TEXT, position INT);
CREATE TABLE responses(id INTEGER PRIMARY KEY, form_id INT REFERENCES forms(id), email TEXT, submitted_at TEXT, deleted_at TEXT);
CREATE TABLE answers(response_id INT REFERENCES responses(id), field_id INT REFERENCES fields(id), value TEXT);
"""
TYPES = ("text", "number", "email", "choice")


def seed(db):
    db.exec("INSERT INTO forms VALUES(1,1,'Customer Feedback','feedback','published',NULL,'2026-12-31')")
    db.exec("INSERT INTO forms VALUES(2,1,'Event Signup','signup','published',3,'2026-06-30')")
    db.exec("INSERT INTO forms VALUES(3,1,'Draft Survey','draft-survey','draft',NULL,NULL)")
    db.exec("INSERT INTO forms VALUES(4,2,'Globex HR Form','globex-hr','published',NULL,NULL)")
    for fid, label, typ, req, opts, pos in [(1, "Rating (1-5)", "number", 1, None, 1), (1, "Comments", "text", 0, None, 2),
                                           (2, "Name", "text", 1, None, 1), (2, "Meal", "choice", 1, '["veg","meat"]', 2), (4, "Employee ID", "text", 1, None, 1)]:
        db.exec("INSERT INTO fields VALUES(NULL,?,?,?,?,?,?)", (fid, label, typ, req, opts, pos))
    for i in range(12):
        rid = db.exec("INSERT INTO responses VALUES(NULL,1,?,?,NULL)", (f"user{i}@example.test", "2026-03-01"))
        db.exec("INSERT INTO answers VALUES(?,1,?)", (rid, str(1 + i % 5)))
    db.exec("INSERT INTO responses VALUES(NULL,4,'hr@globex.test','2026-03-02',NULL)")


app = App("formstacker", "FormStacker", 9103, SCHEMA, seed, static_dir=Path(__file__).parent / "static",
          description="Form builder with public submission links and response collection.")


@app.route("GET", "/api/forms")
def forms(ctx):
    return ctx.page("SELECT * FROM forms WHERE org_id=%d ORDER BY id" % ctx.user["org_id"])


@app.route("POST", "/api/forms", roles=["admin", "member"])
def add_form(ctx):
    title, slug = ctx.need("title", "slug")
    if ctx.one("SELECT 1 FROM forms WHERE slug=?", [slug]):
        raise HttpError(409, "slug taken")
    fid = ctx.exec("INSERT INTO forms VALUES(NULL,?,?,?, 'draft',?,?)", (ctx.user["org_id"], title, slug, ctx.body.get("max_responses"), ctx.body.get("closes_at")))
    return created(ctx.get("forms", fid))


@app.route("POST", "/api/forms/<id>/fields", roles=["admin", "member"])
def add_field(ctx):
    f = ctx.get("forms", ctx.params["id"])
    label, typ = ctx.need("label", "type")
    if typ not in TYPES:
        raise HttpError(400, "unknown field type")
    pos = ctx.one("SELECT COUNT(*) AS n FROM fields WHERE form_id=?", [f["id"]])["n"] + 1
    opts = json.dumps(ctx.body["options"]) if ctx.body.get("options") else None
    fid = ctx.exec("INSERT INTO fields VALUES(NULL,?,?,?,?,?,?)", (f["id"], label, typ, int(bool(ctx.body.get("required"))), opts, pos))
    return created(ctx.one("SELECT * FROM fields WHERE id=?", [fid]))


@app.route("POST", "/api/forms/<id>/publish", roles=["admin", "member"])
def publish(ctx):
    f = ctx.get("forms", ctx.params["id"])
    if not ctx.one("SELECT 1 FROM fields WHERE form_id=?", [f["id"]]):
        raise HttpError(409, "add at least one field before publishing")
    ctx.exec("UPDATE forms SET status='published' WHERE id=?", [f["id"]])
    return ctx.get("forms", f["id"])


def live_count(ctx, fid):
    return ctx.one("SELECT COUNT(*) AS n FROM responses WHERE form_id=?", [fid])["n"]


@app.route("POST", "/api/public/<slug>/submit", auth=False)
def submit(ctx):
    """Public form submission: {email, answers: {field_id: value}}."""
    f = ctx.one("SELECT * FROM forms WHERE slug=?", [ctx.params["slug"]])
    if not f or f["status"] != "published":
        raise HttpError(404, "form not found")
    if f["closes_at"] and ctx.today.isoformat() >= f["closes_at"]:
        raise HttpError(410, "form closed")
    email = ctx.need("email")[0]
    if f["max_responses"] and live_count(ctx, f["id"]) >= f["max_responses"]:
        raise HttpError(409, "response limit reached")
    if ctx.one("SELECT 1 FROM responses WHERE form_id=? AND email=? AND deleted_at IS NULL", (f["id"], email)):
        raise HttpError(409, "already submitted")
    answers = ctx.body.get("answers", {})
    for fld in ctx.q("SELECT * FROM fields WHERE form_id=?", [f["id"]]):
        v = answers.get(str(fld["id"]))
        if fld["required"] and not v:
            raise HttpError(400, f"'{fld['label']}' is required")
        if v is not None and fld["type"] == "choice" and v not in json.loads(fld["options"]):
            raise HttpError(400, f"invalid choice for '{fld['label']}'")
    rid = ctx.exec("INSERT INTO responses VALUES(NULL,?,?,?,NULL)", (f["id"], email, ctx.now))
    for k, v in answers.items():
        ctx.exec("INSERT INTO answers VALUES(?,?,?)", (rid, int(k), str(v)))
    return created({"id": rid})


@app.route("GET", "/api/forms/<id>/responses", roles=["admin", "member"])
def responses(ctx):
    ctx.get("forms", ctx.params["id"], org=False)
    return ctx.page("SELECT * FROM responses WHERE form_id=? AND deleted_at IS NULL ORDER BY id", [ctx.params["id"]])


@app.route("DELETE", "/api/responses/<id>", roles=["admin"])
def delete_response(ctx):
    r = ctx.one("SELECT r.* FROM responses r JOIN forms f ON f.id=r.form_id WHERE r.id=? AND f.org_id=?", (ctx.params["id"], ctx.user["org_id"]))
    if not r:
        raise HttpError(404, "response not found")
    ctx.exec("UPDATE responses SET deleted_at=? WHERE id=?", (ctx.now, r["id"]))
    return {"ok": True}


@app.route("GET", "/api/forms/<id>/summary")
def summary(ctx):
    f = ctx.get("forms", ctx.params["id"])
    out = {"responses": ctx.one("SELECT COUNT(*) AS n FROM responses WHERE form_id=? AND deleted_at IS NULL", [f["id"]])["n"], "fields": {}}
    for fld in ctx.q("SELECT * FROM fields WHERE form_id=? AND type='number'", [f["id"]]):
        vals = [float(a["value"]) for a in ctx.q("SELECT a.value FROM answers a JOIN responses r ON r.id=a.response_id WHERE a.field_id=? AND r.deleted_at IS NULL", [fld["id"]])]
        out["fields"][fld["label"]] = {"average": round(sum(vals) / len(vals), 2) if vals else None}
    return out
