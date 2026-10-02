from pathlib import Path

from common.framework import App, HttpError, created

SCHEMA = """
CREATE TABLE companies(id INTEGER PRIMARY KEY, org_id INT, name TEXT);
CREATE TABLE contacts(id INTEGER PRIMARY KEY, org_id INT, name TEXT, email TEXT, company_id INT REFERENCES companies(id), lifecycle TEXT DEFAULT 'lead', deleted_at TEXT);
CREATE TABLE deals(id INTEGER PRIMARY KEY, org_id INT, contact_id INT REFERENCES contacts(id), title TEXT, amount_cents INT, stage TEXT DEFAULT 'prospect', closed_on TEXT);
"""
STAGES = ("prospect", "qualified", "proposal", "won", "lost")
WEIGHTS = {"prospect": 0.1, "qualified": 0.3, "proposal": 0.6}


def seed(db):
    for i, n in enumerate(["Acme Rockets", "Pied Piper", "Soylent"], 1):
        db.exec("INSERT INTO companies VALUES(?,?,?)", (i, 1, n))
    names = ["Wile Coyote", "Richard Hendricks", "Monica Hall", "Jared Dunn", "Bertram Gilfoyle", "Dinesh Chugtai", "Erlich Bachman", "Gavin Belson"]
    for i, n in enumerate(names, 1):
        db.exec("INSERT INTO contacts VALUES(?,?,?,?,?,?,NULL)", (i, 1, n, n.split()[0].lower() + "@example.test", (i % 3) + 1, "customer" if i % 3 == 0 else "lead"))
    db.exec("UPDATE contacts SET deleted_at='2026-02-01' WHERE id=8")
    db.exec("INSERT INTO contacts VALUES(9,2,'Globex Contact','gc@globex.test',NULL,'lead',NULL)")
    for i in range(1, 11):
        st = STAGES[i % 5]
        db.exec("INSERT INTO deals VALUES(NULL,1,?,?,?,?,?)", ((i % 7) + 1, f"Deal {i}", 100000 * i, st, "2026-03-05" if st == "won" else None))
    db.exec("INSERT INTO deals VALUES(100,2,9,'Globex mega deal',9000000,'proposal',NULL)")


app = App("clienthub", "ClientHub", 9110, SCHEMA, seed, static_dir=Path(__file__).parent / "static",
          description="Lightweight CRM: contacts, companies, deals and pipeline forecasting.")


@app.route("GET", "/api/contacts")
def contacts(ctx):
    sql, args = "SELECT * FROM contacts WHERE org_id=?", [ctx.user["org_id"]]
    if ctx.query.get("q"):
        sql += " AND (name LIKE ? OR email LIKE ?)"
        args += ["%" + ctx.query["q"] + "%"] * 2
    else:
        sql += " AND deleted_at IS NULL"
    return ctx.page(sql + " ORDER BY id", args)


@app.route("POST", "/api/contacts", roles=["admin", "member"])
def add_contact(ctx):
    name, email = ctx.need("name", "email")
    cid = ctx.exec("INSERT INTO contacts VALUES(NULL,?,?,?,?,'lead',NULL)", (ctx.user["org_id"], name, email, ctx.body.get("company_id")))
    return created(ctx.get("contacts", cid))


@app.route("GET", "/api/contacts/<id>")
def get_contact(ctx):
    c = ctx.get("contacts", ctx.params["id"])
    c["deals"] = ctx.q("SELECT * FROM deals WHERE contact_id=?", [c["id"]])
    c["lifetime_value_cents"] = sum(d["amount_cents"] for d in c["deals"] if d["stage"] == "won")
    return c


@app.route("DELETE", "/api/contacts/<id>", roles=["admin", "member"])
def del_contact(ctx):
    c = ctx.get("contacts", ctx.params["id"])
    ctx.exec("UPDATE contacts SET deleted_at=? WHERE id=?", (ctx.now, c["id"]))
    return {"ok": True}


@app.route("POST", "/api/contacts/merge", roles=["admin", "member"])
def merge(ctx):
    """Merge duplicate contact `merge_id` into `keep_id`."""
    keep_id, merge_id = ctx.need("keep_id", "merge_id")
    if keep_id == merge_id:
        raise HttpError(400, "cannot merge a contact into itself")
    ctx.get("contacts", keep_id)
    ctx.get("contacts", merge_id)
    ctx.exec("UPDATE contacts SET deleted_at=? WHERE id=?", (ctx.now, merge_id))
    return get_contact(type("C", (), {"get": ctx.get, "q": ctx.q, "params": {"id": keep_id}})())


@app.route("GET", "/api/deals")
def deals(ctx):
    sql, args = "SELECT d.*, c.name AS contact_name FROM deals d LEFT JOIN contacts c ON c.id=d.contact_id WHERE d.org_id=?", [ctx.user["org_id"]]
    if ctx.query.get("stage"):
        sql += " AND d.stage=?"
        args.append(ctx.query["stage"])
    return ctx.page(sql + " ORDER BY d.id", args)


@app.route("GET", "/api/deals/<id>")
def get_deal(ctx):
    return ctx.get("deals", ctx.params["id"], org=False)


@app.route("POST", "/api/deals", roles=["admin", "member"])
def add_deal(ctx):
    cid, title, amount = ctx.need("contact_id", "title", "amount_cents")
    ctx.get("contacts", cid)
    did = ctx.exec("INSERT INTO deals VALUES(NULL,?,?,?,?,'prospect',NULL)", (ctx.user["org_id"], cid, title, amount))
    return created(ctx.get("deals", did))


@app.route("POST", "/api/deals/<id>/stage", roles=["admin", "member"])
def set_stage(ctx):
    d = ctx.get("deals", ctx.params["id"])
    st = ctx.need("stage")[0]
    if st not in STAGES:
        raise HttpError(400, "invalid stage")
    closed = ctx.today.isoformat() if st == "won" else d["closed_on"]
    ctx.exec("UPDATE deals SET stage=?, closed_on=? WHERE id=?", (st, closed, d["id"]))
    return ctx.get("deals", d["id"])


@app.route("GET", "/api/reports/pipeline", roles=["admin", "member"])
def pipeline(ctx):
    """Open pipeline by stage, weighted forecast and revenue won in ?month=YYYY-MM."""
    month = ctx.query.get("month", ctx.today.strftime("%Y-%m"))
    rows = ctx.q("SELECT * FROM deals WHERE org_id=?", [ctx.user["org_id"]])
    open_rows = [r for r in rows if r["stage"] in WEIGHTS]
    return {"open_cents": sum(r["amount_cents"] for r in open_rows),
            "forecast_cents": round(sum(r["amount_cents"] * WEIGHTS[r["stage"]] for r in open_rows)),
            "won_cents": sum(r["amount_cents"] for r in rows if (r["closed_on"] or "").startswith(month))}
