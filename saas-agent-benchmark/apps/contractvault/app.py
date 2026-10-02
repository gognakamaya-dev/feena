import datetime as dt
from pathlib import Path

from common.framework import App, HttpError, created

SCHEMA = """
CREATE TABLE contracts(id INTEGER PRIMARY KEY, org_id INT, title TEXT, counterparty TEXT, status TEXT DEFAULT 'draft', value_cents INT,
  start_date TEXT, end_date TEXT, auto_renew INT DEFAULT 0, owner_id INT, body TEXT, version INT DEFAULT 1);
CREATE TABLE versions(id INTEGER PRIMARY KEY, contract_id INT REFERENCES contracts(id), version INT, body TEXT, value_cents INT, edited_by INT);
CREATE TABLE approvals(contract_id INT REFERENCES contracts(id), approver_id INT REFERENCES users(id), status TEXT DEFAULT 'pending', PRIMARY KEY(contract_id,approver_id));
"""


def seed(db):
    rows = [("MSA Initech", "Initech", "signed", 1200000, "2025-04-14", "2026-04-14", 0), ("NDA Hooli", "Hooli", "signed", 0, "2025-03-01", "2027-03-01", 0),
            ("SaaS Order Form Umbrella", "Umbrella", "draft", 560000, "2026-04-01", "2027-03-31", 1), ("Lease Renewal", "Landlord LLC", "in_review", 3600000, "2026-05-01", "2029-04-30", 0),
            ("Old Vendor Agreement", "Vandelay", "expired", 90000, "2024-01-01", "2025-12-31", 0), ("Support Retainer", "Pied Piper", "signed", 240000, "2025-06-15", "2026-06-14", 1)]
    for i, (t, cp, st, v, s, e, ar) in enumerate(rows, 1):
        db.exec("INSERT INTO contracts VALUES(?,?,?,?,?,?,?,?,?,1,?,1)", (i, 1, t, cp, st, v, s, e, ar, f"Terms of {t}"))
        db.exec("INSERT INTO versions VALUES(NULL,?,1,?,?,1)", (i, f"Terms of {t}", v))
    db.exec("INSERT INTO contracts VALUES(7,2,'Globex Secret Deal','Rival Inc','draft',7777777,'2026-01-01','2026-12-31',0,4,'Confidential',1)")


app = App("contractvault", "ContractVault", 9113, SCHEMA, seed, static_dir=Path(__file__).parent / "static",
          description="Contract lifecycle management: versions, approvals, signatures, expirations and renewals.")


def d(s):
    try:
        return dt.date.fromisoformat(s)
    except (TypeError, ValueError):
        raise HttpError(400, "dates must be YYYY-MM-DD")


@app.route("GET", "/api/contracts")
def contracts(ctx):
    sql, args = "SELECT * FROM contracts WHERE org_id=?", [ctx.user["org_id"]]
    if ctx.query.get("status"):
        sql += " AND status=?"
        args.append(ctx.query["status"])
    return ctx.page(sql + " ORDER BY id", args)


@app.route("GET", "/api/contracts/<id>")
def get_contract(ctx):
    return ctx.get("contracts", ctx.params["id"], org=False)


@app.route("POST", "/api/contracts", roles=["admin", "member"])
def add_contract(ctx):
    title, cp, start, end = ctx.need("title", "counterparty", "start_date", "end_date")
    if d(end) < d(start):
        raise HttpError(400, "end_date must not precede start_date")
    cid = ctx.exec("INSERT INTO contracts VALUES(NULL,?,?,?,'draft',?,?,?,?,?,?,1)", (
        ctx.user["org_id"], title, cp, ctx.body.get("value_cents", 0), start, end, int(bool(ctx.body.get("auto_renew"))), ctx.user["id"], ctx.body.get("body", "")))
    ctx.exec("INSERT INTO versions VALUES(NULL,?,1,?,?,?)", (cid, ctx.body.get("body", ""), ctx.body.get("value_cents", 0), ctx.user["id"]))
    return created(ctx.get("contracts", cid))


@app.route("PUT", "/api/contracts/<id>", roles=["admin", "member"])
def edit(ctx):
    c = ctx.get("contracts", ctx.params["id"])
    if c["status"] not in ("draft", "in_review"):
        raise HttpError(409, "only draft or in-review contracts can be edited")
    body, value = ctx.body.get("body", c["body"]), ctx.body.get("value_cents", c["value_cents"])
    if body != c["body"]:
        ctx.exec("INSERT INTO versions VALUES(NULL,?,?,?,?,?)", (c["id"], c["version"] + 1, body, value, ctx.user["id"]))
        ctx.exec("UPDATE contracts SET version=version+1 WHERE id=?", [c["id"]])
    ctx.exec("UPDATE contracts SET body=?, value_cents=? WHERE id=?", (body, value, c["id"]))
    return ctx.get("contracts", c["id"])


@app.route("GET", "/api/contracts/<id>/versions")
def versions(ctx):
    c = ctx.get("contracts", ctx.params["id"])
    return {"items": ctx.q("SELECT * FROM versions WHERE contract_id=? ORDER BY version", [c["id"]])}


@app.route("POST", "/api/contracts/<id>/request-approval", roles=["admin", "member"])
def request_approval(ctx):
    c = ctx.get("contracts", ctx.params["id"])
    if c["status"] != "draft":
        raise HttpError(409, "only drafts can enter review")
    for uid in ctx.need("approver_ids")[0]:
        ctx.get("users", uid)
        ctx.exec("INSERT OR REPLACE INTO approvals VALUES(?,?,'pending')", (c["id"], uid))
    ctx.exec("UPDATE contracts SET status='in_review' WHERE id=?", [c["id"]])
    return ctx.get("contracts", c["id"])


@app.route("POST", "/api/contracts/<id>/approve", roles=["admin", "member"])
def approve(ctx):
    c = ctx.get("contracts", ctx.params["id"])
    if not ctx.one("SELECT 1 FROM approvals WHERE contract_id=? AND approver_id=?", (c["id"], ctx.user["id"])):
        raise HttpError(403, "you are not an approver")
    ctx.exec("UPDATE approvals SET status='approved' WHERE contract_id=? AND approver_id=?", (c["id"], ctx.user["id"]))
    return {"ok": True}


@app.route("POST", "/api/contracts/<id>/sign", roles=["admin"])
def sign(ctx):
    c = ctx.get("contracts", ctx.params["id"])
    if c["status"] != "in_review":
        raise HttpError(409, "contract must be in review")
    if ctx.one("SELECT 1 FROM approvals WHERE contract_id=? AND status!='approved'", [c["id"]]):
        raise HttpError(409, "all approvals required")
    ctx.exec("UPDATE contracts SET status='signed' WHERE id=?", [c["id"]])
    return ctx.get("contracts", c["id"])


@app.route("GET", "/api/reports/expiring", roles=["admin", "member"])
def expiring(ctx):
    """Signed contracts ending within ?days= (default 30), inclusive."""
    days = ctx.int_arg("days", 30, lo=0)
    limit = (ctx.today + dt.timedelta(days=days)).isoformat()
    rows = ctx.q("SELECT * FROM contracts WHERE org_id=? AND status='signed' AND end_date>=? AND end_date<? ORDER BY end_date", (ctx.user["org_id"], ctx.today.isoformat(), limit))
    return {"items": rows, "total": len(rows)}


@app.route("POST", "/api/jobs/expire", roles=["admin"])
def expire_job(ctx):
    """Expire signed contracts past end_date; auto-renew ones are extended by 12 months."""
    out = {"expired": [], "renewed": []}
    for c in ctx.q("SELECT * FROM contracts WHERE org_id=? AND status='signed' AND end_date<?", (ctx.user["org_id"], ctx.today.isoformat())):
        if c["auto_renew"]:
            t = ctx.today
            ctx.exec("UPDATE contracts SET end_date=? WHERE id=?", (t.replace(year=t.year + 1).isoformat(), c["id"]))
            out["renewed"].append(c["id"])
        else:
            ctx.exec("UPDATE contracts SET status='expired' WHERE id=?", [c["id"]])
            out["expired"].append(c["id"])
    return out
