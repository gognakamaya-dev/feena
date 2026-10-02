from pathlib import Path

from common.framework import App, HttpError, created

SCHEMA = """
CREATE TABLE tickets(id INTEGER PRIMARY KEY, org_id INT, subject TEXT, body TEXT, status TEXT DEFAULT 'open', priority TEXT DEFAULT 'normal',
  requester_email TEXT, assignee_id INT, created_at TEXT, first_response_at TEXT, resolved_at TEXT);
CREATE TABLE replies(id INTEGER PRIMARY KEY, ticket_id INT REFERENCES tickets(id), author_id INT REFERENCES users(id), body TEXT, internal INT DEFAULT 0, created_at TEXT);
"""
PRIORITIES = ("low", "normal", "high", "urgent")
STATUSES = ("open", "pending", "resolved", "closed")


def seed(db):
    subjects = ["Cannot log in", "Invoice looks wrong", "Export fails", "Feature request: dark mode", "Billing address change", "App is slow"]
    for i in range(14):
        status = STATUSES[i % 4]
        db.exec("INSERT INTO tickets VALUES(NULL,1,?,?,?,?,?,?,?,?,?)", (
            subjects[i % 6], "Details about: " + subjects[i % 6].lower(), status, PRIORITIES[i % 4],
            "viewer@acme.test" if i % 3 == 0 else f"cust{i}@example.test", 2 if i % 2 else None, "2026-03-01", None,
            "2026-03-05" if status in ("resolved", "closed") else None))
    db.exec("INSERT INTO tickets VALUES(NULL,2,'Globex outage','Everything down','open','urgent','ops@globex.test',NULL,'2026-03-02',NULL,NULL)")
    db.exec("INSERT INTO replies VALUES(NULL,1,2,'Internal: check logs',1,'2026-03-02')")
    db.exec("INSERT INTO replies VALUES(NULL,1,2,'We are looking into it',0,'2026-03-02')")


app = App("supportdesk", "SupportDesk", 9106, SCHEMA, seed, static_dir=Path(__file__).parent / "static",
          description="Customer support ticketing with internal notes and SLA tracking. Viewers act as customers.")


def load(ctx, tid):
    t = ctx.get("tickets", tid)
    if ctx.user["role"] == "viewer" and t["requester_email"] != ctx.user["email"]:
        raise HttpError(404, "ticket not found")
    return t


@app.route("GET", "/api/tickets")
def list_tickets(ctx):
    sql, args = "SELECT * FROM tickets WHERE org_id=?", [ctx.user["org_id"]]
    if ctx.user["role"] == "viewer":
        sql += " AND requester_email=?"
        args.append(ctx.user["email"])
    for col in ("status", "priority", "assignee_id"):
        if ctx.query.get(col):
            sql += f" AND {col}=?"
            args.append(ctx.query[col])
    if ctx.query.get("q"):
        sql += " AND subject LIKE ?"
        args.append("%" + ctx.query["q"] + "%")
    return ctx.page(sql + " ORDER BY id", args)


@app.route("POST", "/api/tickets")
def open_ticket(ctx):
    subject, body = ctx.need("subject", "body")
    tid = ctx.exec("INSERT INTO tickets VALUES(NULL,?,?,?,'open',?,?,NULL,?,NULL,NULL)", (
        ctx.user["org_id"], subject, body, ctx.body.get("priority", "normal"), ctx.user["email"], ctx.now))
    return created(ctx.get("tickets", tid))


@app.route("GET", "/api/tickets/<id>")
def get_ticket(ctx):
    t = load(ctx, ctx.params["id"])
    t["replies"] = ctx.q("SELECT * FROM replies WHERE ticket_id=? ORDER BY id", [t["id"]])
    return t


@app.route("POST", "/api/tickets/<id>/replies")
def reply(ctx):
    t = load(ctx, ctx.params["id"])
    body = ctx.need("body")[0]
    customer = ctx.user["role"] == "viewer"
    internal = 0 if customer else int(bool(ctx.body.get("internal")))
    ctx.exec("INSERT INTO replies VALUES(NULL,?,?,?,?,?)", (t["id"], ctx.user["id"], body, internal, ctx.now))
    if not t["first_response_at"]:
        ctx.exec("UPDATE tickets SET first_response_at=? WHERE id=?", (ctx.now, t["id"]))
    if customer and t["status"] in ("resolved", "closed", "pending"):
        ctx.exec("UPDATE tickets SET status='open' WHERE id=?", [t["id"]])
    return created(ctx.get("tickets", t["id"]))


@app.route("POST", "/api/tickets/<id>/assign", roles=["admin", "member"])
def assign(ctx):
    t = ctx.get("tickets", ctx.params["id"])
    ctx.get("users", ctx.need("assignee_id")[0])
    ctx.exec("UPDATE tickets SET assignee_id=? WHERE id=?", (ctx.body["assignee_id"], t["id"]))
    return ctx.get("tickets", t["id"])


@app.route("POST", "/api/tickets/<id>/status", roles=["admin", "member"])
def set_status(ctx):
    t = ctx.get("tickets", ctx.params["id"])
    st = ctx.need("status")[0]
    if st not in STATUSES:
        raise HttpError(400, "invalid status")
    ctx.exec("UPDATE tickets SET status=?, resolved_at=? WHERE id=?", (st, ctx.today.isoformat() if st in ("resolved", "closed") else None, t["id"]))
    return ctx.get("tickets", t["id"])


@app.route("GET", "/api/reports/summary", roles=["admin", "member"])
def summary(ctx):
    rows = ctx.q("SELECT status, resolved_at FROM tickets WHERE org_id=?", [ctx.user["org_id"]])
    return {"total": len(rows), "open": sum(r["status"] == "open" for r in rows), "resolved": sum(r["resolved_at"] is not None for r in rows)}
