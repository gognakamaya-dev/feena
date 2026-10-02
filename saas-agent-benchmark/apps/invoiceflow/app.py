import calendar
from pathlib import Path

from common.framework import App, HttpError, created

SCHEMA = """
CREATE TABLE customers(id INTEGER PRIMARY KEY, org_id INT, name TEXT, email TEXT, deleted_at TEXT);
CREATE TABLE invoices(id INTEGER PRIMARY KEY, org_id INT, customer_id INT REFERENCES customers(id),
  number TEXT, status TEXT, discount_pct REAL DEFAULT 0, tax_pct REAL DEFAULT 0, due_date TEXT, created_at TEXT);
CREATE TABLE invoice_items(id INTEGER PRIMARY KEY, invoice_id INT REFERENCES invoices(id), description TEXT, qty INT, unit_cents INT);
CREATE TABLE payments(id INTEGER PRIMARY KEY, invoice_id INT REFERENCES invoices(id), amount_cents INT, method TEXT,
  paid_on TEXT, refunded INT DEFAULT 0);
"""


def seed(db):
    for i, n in enumerate(["Northwind Traders", "Initech", "Umbrella Labs", "Hooli"], 1):
        db.exec("INSERT INTO customers VALUES(?,?,?,?,NULL)", (i, 1, n, n.split()[0].lower() + "@example.test"))
    db.exec("INSERT INTO customers VALUES(5,2,'Globex Client','gc@example.test',NULL)")
    for i in range(1, 24):
        status = ["draft", "sent", "paid", "sent"][i % 4]
        iid = db.exec("INSERT INTO invoices VALUES(?,?,?,?,?,?,?,?,?)",
                      (i, 1, (i % 4) + 1, f"INV-{1000 + i}", status, 10 if i % 5 == 0 else 0, 8, f"2026-03-{(i % 28) + 1:02d}", "2026-02-20"))
        db.exec("INSERT INTO invoice_items VALUES(NULL,?,?,?,?)", (iid, "Consulting hours", 2 + i % 3, 15000))
        db.exec("INSERT INTO invoice_items VALUES(NULL,?,?,?,?)", (iid, "Hosting", 1, 4900))
        if status == "paid":
            db.exec("INSERT INTO payments VALUES(NULL,?,?,?,?,0)", (iid, totals(db, iid)["total_cents"], "card", "2026-03-01"))
    db.exec("INSERT INTO invoices VALUES(100,2,5,'INV-2001','sent',0,0,'2026-03-30','2026-03-01')")
    db.exec("INSERT INTO invoice_items VALUES(NULL,100,'Secret project',1,990000)")


def totals(db, invoice_id):
    inv = db.one("SELECT * FROM invoices WHERE id=?", [invoice_id])
    subtotal = sum(i["qty"] * i["unit_cents"] for i in db.q("SELECT * FROM invoice_items WHERE invoice_id=?", [invoice_id]))
    discount = round(subtotal * inv["discount_pct"] / 100)
    tax = round(subtotal * inv["tax_pct"] / 100)
    total = subtotal - discount + tax
    paid = sum(p["amount_cents"] for p in db.q("SELECT * FROM payments WHERE invoice_id=? AND refunded=0", [invoice_id]))
    return {"subtotal_cents": subtotal, "discount_cents": discount, "tax_cents": tax, "total_cents": total,
            "paid_cents": paid, "balance_cents": total - paid}


def present(db, inv):
    out = dict(inv)
    out.update(totals(db, inv["id"]))
    out["items"] = db.q("SELECT * FROM invoice_items WHERE invoice_id=?", [inv["id"]])
    return out


app = App("invoiceflow", "InvoiceFlow", 9101, SCHEMA, seed, static_dir=Path(__file__).parent / "static",
          description="Invoicing and payment tracking for small agencies.")


@app.route("GET", "/api/customers")
def customers(ctx):
    """List active customers."""
    return ctx.page("SELECT * FROM customers WHERE org_id=%d AND deleted_at IS NULL ORDER BY name" % ctx.user["org_id"])


@app.route("POST", "/api/customers", roles=["admin", "member"])
def add_customer(ctx):
    name, email = ctx.need("name", "email")
    return created(ctx.get("customers", ctx.exec("INSERT INTO customers VALUES(NULL,?,?,?,NULL)", (ctx.user["org_id"], name, email))))


@app.route("DELETE", "/api/customers/<id>", roles=["admin"])
def del_customer(ctx):
    """Soft-delete a customer."""
    ctx.get("customers", ctx.params["id"])
    ctx.exec("UPDATE customers SET deleted_at=? WHERE id=?", (ctx.now, ctx.params["id"]))
    return {"ok": True}


@app.route("GET", "/api/invoices")
def list_invoices(ctx):
    """List invoices, optional ?status= filter, paginated."""
    sql, args = "SELECT i.*, c.name AS customer_name FROM invoices i JOIN customers c ON c.id=i.customer_id WHERE i.org_id=?", [ctx.user["org_id"]]
    if ctx.query.get("status"):
        sql += " AND i.status=?"
        args.append(ctx.query["status"])
    res = ctx.page(sql + " ORDER BY i.id", args)
    for r in res["items"]:
        r.update(totals(ctx.db, r["id"]))
    return res


@app.route("POST", "/api/invoices", roles=["admin", "member"])
def create_invoice(ctx):
    cust, items = ctx.need("customer_id", "due_date")[0], ctx.body.get("items")
    ctx.get("customers", cust)
    n = ctx.one("SELECT COUNT(*) AS n FROM invoices")["n"]
    iid = ctx.exec("INSERT INTO invoices VALUES(NULL,?,?,?,?,?,?,?,?)", (
        ctx.user["org_id"], cust, f"INV-{1001 + n}", "draft", ctx.body.get("discount_pct", 0), ctx.body.get("tax_pct", 0),
        ctx.body["due_date"], ctx.today.isoformat()))
    for it in items or []:
        ctx.exec("INSERT INTO invoice_items VALUES(NULL,?,?,?,?)", (iid, it["description"], it["qty"], it["unit_cents"]))
    return created(present(ctx.db, ctx.get("invoices", iid)))


@app.route("GET", "/api/invoices/<id>")
def get_invoice(ctx):
    inv = ctx.get("invoices", ctx.params["id"], org=False)
    return present(ctx.db, inv)


@app.route("POST", "/api/invoices/<id>/send", roles=["admin", "member"])
def send_invoice(ctx):
    inv = ctx.get("invoices", ctx.params["id"])
    if inv["status"] != "draft":
        raise HttpError(409, "only draft invoices can be sent")
    ctx.exec("UPDATE invoices SET status='sent' WHERE id=?", [inv["id"]])
    return present(ctx.db, ctx.get("invoices", inv["id"]))


def settle(ctx, inv_id):
    t = totals(ctx.db, inv_id)
    status = "paid" if t["balance_cents"] <= 0 else ("partially_paid" if t["paid_cents"] > 0 else "sent")
    ctx.exec("UPDATE invoices SET status=? WHERE id=?", (status, inv_id))


@app.route("POST", "/api/invoices/<id>/payments", roles=["admin", "member"])
def pay(ctx):
    """Record a payment (optional paid_on date)."""
    inv = ctx.get("invoices", ctx.params["id"])
    amount = ctx.need("amount_cents")[0]
    if inv["status"] in ("draft", "void", "paid"):
        raise HttpError(409, f"cannot pay a {inv['status']} invoice")
    if not isinstance(amount, int) or amount <= 0 or amount > totals(ctx.db, inv["id"])["balance_cents"]:
        raise HttpError(400, "invalid amount")
    ctx.exec("INSERT INTO payments VALUES(NULL,?,?,?,?,0)", (inv["id"], amount, ctx.body.get("method", "card"), ctx.body.get("paid_on", ctx.today.isoformat())))
    settle(ctx, inv["id"])
    return created(present(ctx.db, ctx.get("invoices", inv["id"])))


@app.route("POST", "/api/invoices/<id>/payments/<pid>/refund", roles=["admin"])
def refund(ctx):
    inv = ctx.get("invoices", ctx.params["id"])
    p = ctx.one("SELECT * FROM payments WHERE id=? AND invoice_id=?", (ctx.params["pid"], inv["id"]))
    if not p or p["refunded"]:
        raise HttpError(404, "payment not found")
    ctx.exec("UPDATE payments SET refunded=1 WHERE id=?", [p["id"]])
    return present(ctx.db, ctx.get("invoices", inv["id"]))


@app.route("POST", "/api/invoices/<id>/void", roles=["admin"])
def void(ctx):
    inv = ctx.get("invoices", ctx.params["id"])
    if inv["status"] == "paid":
        raise HttpError(409, "paid invoices cannot be voided")
    ctx.exec("UPDATE invoices SET status='void' WHERE id=?", [inv["id"]])
    return present(ctx.db, ctx.get("invoices", inv["id"]))


@app.route("GET", "/api/reports/revenue", roles=["admin"])
def revenue(ctx):
    """Collected revenue for ?month=YYYY-MM (net of refunds)."""
    month = ctx.query.get("month", ctx.today.strftime("%Y-%m"))
    y, m = map(int, month.split("-"))
    start, end = f"{month}-01", f"{month}-{calendar.monthrange(y, m)[1]:02d}"
    rows = ctx.q("SELECT p.amount_cents FROM payments p JOIN invoices i ON i.id=p.invoice_id "
                 "WHERE i.org_id=? AND p.refunded=0 AND p.paid_on>=? AND p.paid_on<?", (ctx.user["org_id"], start, end))
    return {"month": month, "revenue_cents": sum(r["amount_cents"] for r in rows), "payments": len(rows)}
