import secrets
from pathlib import Path

from common.framework import App, HttpError, created

SCHEMA = """
CREATE TABLE catalog(id INTEGER PRIMARY KEY, org_id INT, name TEXT, price_cents INT);
CREATE TABLE quotes(id INTEGER PRIMARY KEY, org_id INT, number TEXT, customer_name TEXT, status TEXT DEFAULT 'draft', valid_until TEXT,
  discount_pct REAL DEFAULT 0, token TEXT UNIQUE, created_by INT);
CREATE TABLE quote_items(id INTEGER PRIMARY KEY, quote_id INT REFERENCES quotes(id), name TEXT, qty INT, unit_cents INT, optional INT DEFAULT 0, selected INT DEFAULT 0);
"""
TIERS = [(500000, 10), (100000, 5)]
MEMBER_MAX_DISCOUNT = 20
ADMIN_MAX_DISCOUNT = 50


def seed(db):
    for i, (n, pr) in enumerate([("Implementation workshop", 150000), ("Annual license", 120000), ("Priority support", 30000), ("Training day", 80000)], 1):
        db.exec("INSERT INTO catalog VALUES(?,1,?,?)", (i, n, pr))
    db.exec("INSERT INTO catalog VALUES(5,2,'Globex service',100)")
    for i, (cust, st) in enumerate([("Initech", "sent"), ("Hooli", "draft"), ("Umbrella", "accepted"), ("Vandelay", "declined")], 1):
        db.exec("INSERT INTO quotes VALUES(?,1,?,?,?,?,0,?,1)", (i, f"Q-{1000 + i}", cust, st, "2026-04-30", f"seedtoken{i}"))
        db.exec("INSERT INTO quote_items VALUES(NULL,?,'Annual license',?,120000,0,0)", (i, i))
    db.exec("INSERT INTO quotes VALUES(9,2,'Q-2001','Globex Customer','sent','2026-04-30',0,'globextoken',4)")
    db.exec("INSERT INTO quote_items VALUES(NULL,9,'Secret service',1,555555,0,0)")


app = App("quotepro", "QuotePro", 9118, SCHEMA, seed, static_dir=Path(__file__).parent / "static",
          description="Quotation and proposal generation with catalog items, optional add-ons, tiered discounts and public acceptance links.")


def totals(ctx, q):
    items = ctx.q("SELECT * FROM quote_items WHERE quote_id=?", [q["id"]])
    subtotal = sum(i["qty"] * i["unit_cents"] for i in items if not i["optional"] or i["selected"])
    everything = sum(i["qty"] * i["unit_cents"] for i in items)
    tier = next((pct for floor, pct in TIERS if everything > floor), 0)
    discount = round(subtotal * (tier + q["discount_pct"]) / 100)
    return {"items": items, "subtotal_cents": subtotal, "tier_discount_pct": tier, "discount_cents": discount, "total_cents": subtotal - discount}


def present(ctx, q):
    return {**q, **totals(ctx, q)}


@app.route("GET", "/api/catalog")
def catalog(ctx):
    return ctx.page("SELECT * FROM catalog WHERE org_id=%d ORDER BY id" % ctx.user["org_id"])


@app.route("GET", "/api/quotes")
def quotes(ctx):
    sql, args = "SELECT * FROM quotes WHERE org_id=?", [ctx.user["org_id"]]
    if ctx.query.get("status"):
        sql += " AND status=?"
        args.append(ctx.query["status"])
    res = ctx.page(sql + " ORDER BY id", args)
    res["items"] = [present(ctx, q) for q in res["items"]]
    return res


@app.route("GET", "/api/quotes/<id>")
def get_quote(ctx):
    return present(ctx, ctx.get("quotes", ctx.params["id"]))


def add_items(ctx, qid, items):
    for it in items:
        if it.get("product_id"):
            prod = ctx.get("catalog", it["product_id"])
            name, unit = prod["name"], prod["price_cents"]
        else:
            name, unit = it["name"], it["unit_cents"]
        ctx.exec("INSERT INTO quote_items VALUES(NULL,?,?,?,?,?,0)", (qid, name, it.get("qty", 1), unit, int(bool(it.get("optional")))))


@app.route("POST", "/api/quotes", roles=["admin", "member"])
def add_quote(ctx):
    cust, valid = ctx.need("customer_name", "valid_until")
    items = ctx.body.get("items") or []
    if not items:
        raise HttpError(400, "a quote needs at least one item")
    disc = ctx.body.get("discount_pct", 0)
    if not 0 <= disc <= ADMIN_MAX_DISCOUNT:
        raise HttpError(400, "invalid discount")
    n = ctx.one("SELECT COUNT(*) AS n FROM quotes")["n"]
    qid = ctx.exec("INSERT INTO quotes VALUES(NULL,?,?,?,'draft',?,?,?,?)", (ctx.user["org_id"], f"Q-{1001 + n}", cust, valid, disc, secrets.token_urlsafe(10), ctx.user["id"]))
    add_items(ctx, qid, items)
    return created(present(ctx, ctx.get("quotes", qid)))


@app.route("POST", "/api/quotes/<id>/select", roles=["admin", "member"])
def select_optional(ctx):
    q = ctx.get("quotes", ctx.params["id"])
    ids = ctx.body.get("item_ids", [])
    ctx.exec("UPDATE quote_items SET selected=0 WHERE quote_id=?", [q["id"]])
    for i in ids:
        ctx.exec("UPDATE quote_items SET selected=1 WHERE id=? AND quote_id=? AND optional=1", (i, q["id"]))
    return present(ctx, q)


@app.route("POST", "/api/quotes/<id>/send", roles=["admin", "member"])
def send(ctx):
    q = ctx.get("quotes", ctx.params["id"])
    if q["status"] != "draft":
        raise HttpError(409, "only drafts can be sent")
    ctx.exec("UPDATE quotes SET status='sent' WHERE id=?", [q["id"]])
    return present(ctx, ctx.get("quotes", q["id"]))


@app.route("POST", "/api/quotes/<id>/revise", roles=["admin", "member"])
def revise(ctx):
    """Create a new draft revision of a sent quote; the old one is superseded."""
    q = ctx.get("quotes", ctx.params["id"])
    if q["status"] != "sent":
        raise HttpError(409, "only sent quotes can be revised")
    n = ctx.one("SELECT COUNT(*) AS n FROM quotes")["n"]
    nid = ctx.exec("INSERT INTO quotes VALUES(NULL,?,?,?,'draft',?,?,?,?)", (q["org_id"], f"Q-{1001 + n}", q["customer_name"], q["valid_until"], q["discount_pct"], secrets.token_urlsafe(10), ctx.user["id"]))
    for i in ctx.q("SELECT * FROM quote_items WHERE quote_id=?", [q["id"]]):
        ctx.exec("INSERT INTO quote_items VALUES(NULL,?,?,?,?,?,?)", (nid, i["name"], i["qty"], i["unit_cents"], i["optional"], i["selected"]))
    return created(present(ctx, ctx.get("quotes", nid)))


@app.route("POST", "/api/public/quotes/<token>/accept", auth=False)
def accept(ctx):
    q = ctx.one("SELECT * FROM quotes WHERE token=?", [ctx.params["token"]])
    if not q:
        raise HttpError(404, "quote not found")
    if q["status"] != "sent":
        raise HttpError(409, f"quote is {q['status']}")
    if q["valid_until"] < ctx.today.isoformat():
        raise HttpError(410, "quote has expired")
    ctx.exec("UPDATE quotes SET status='accepted' WHERE id=?", [q["id"]])
    return {"number": q["number"], "status": "accepted", **{k: v for k, v in totals(ctx, q).items() if k != "items"}}
