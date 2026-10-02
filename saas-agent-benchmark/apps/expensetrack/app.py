from pathlib import Path

from common.framework import App, HttpError, created

SCHEMA = """
CREATE TABLE expenses(id INTEGER PRIMARY KEY, org_id INT, user_id INT REFERENCES users(id), category TEXT, amount_cents INT, description TEXT,
  incurred_on TEXT, receipt_url TEXT, status TEXT DEFAULT 'draft', decided_by INT, reject_reason TEXT);
CREATE TABLE budgets(org_id INT, category TEXT, monthly_limit_cents INT, PRIMARY KEY(org_id,category));
"""
CATEGORIES = ("travel", "meals", "software", "equipment")
RECEIPT_THRESHOLD = 5000


def seed(db):
    for cat, lim in [("travel", 200000), ("meals", 50000), ("software", 100000), ("equipment", 150000)]:
        db.exec("INSERT INTO budgets VALUES(1,?,?)", (cat, lim))
    for i in range(1, 16):
        st = ["draft", "submitted", "approved", "reimbursed", "rejected"][i % 5]
        db.exec("INSERT INTO expenses VALUES(NULL,1,?,?,?,?,?,?,?,NULL,NULL)", (
            2 if i % 2 else 3, CATEGORIES[i % 4], 1500 * i, f"Expense {i}", f"2026-03-{i:02d}", f"https://receipts.test/{i}", st))
    db.exec("INSERT INTO expenses VALUES(NULL,2,5,'travel',99900,'Globex offsite','2026-03-04','https://receipts.test/g','submitted',NULL,NULL)")


app = App("expensetrack", "ExpenseTrack", 9108, SCHEMA, seed, static_dir=Path(__file__).parent / "static",
          description="Expense reporting with receipts policy, approvals, reimbursements and budgets.")


@app.route("GET", "/api/expenses")
def list_expenses(ctx):
    sql, args = "SELECT * FROM expenses WHERE org_id=?", [ctx.user["org_id"]]
    if ctx.user["role"] != "admin":
        sql += " AND user_id=?"
        args.append(ctx.user["id"])
    if ctx.query.get("status"):
        sql += " AND status=?"
        args.append(ctx.query["status"])
    return ctx.page(sql + " ORDER BY id", args)


@app.route("GET", "/api/expenses/<id>")
def get_expense(ctx):
    return ctx.get("expenses", ctx.params["id"])


@app.route("POST", "/api/expenses", roles=["admin", "member"])
def add_expense(ctx):
    cat, amount, on = ctx.need("category", "amount_cents", "incurred_on")
    if cat not in CATEGORIES or not isinstance(amount, int) or amount <= 0:
        raise HttpError(400, "invalid category or amount")
    eid = ctx.exec("INSERT INTO expenses VALUES(NULL,?,?,?,?,?,?,?,'draft',NULL,NULL)", (
        ctx.user["org_id"], ctx.user["id"], cat, amount, ctx.body.get("description", ""), on, ctx.body.get("receipt_url")))
    return created(ctx.get("expenses", eid))


@app.route("POST", "/api/expenses/<id>/submit", roles=["admin", "member"])
def submit(ctx):
    e = ctx.get("expenses", ctx.params["id"])
    if e["user_id"] != ctx.user["id"]:
        raise HttpError(403, "not your expense")
    if e["status"] not in ("draft", "rejected"):
        raise HttpError(409, "expense already submitted")
    if e["amount_cents"] > RECEIPT_THRESHOLD and not e["receipt_url"]:
        raise HttpError(400, "receipt required for expenses of $50.00 or more")
    ctx.exec("UPDATE expenses SET status='submitted', reject_reason=NULL WHERE id=?", [e["id"]])
    return ctx.get("expenses", e["id"])


@app.route("POST", "/api/expenses/<id>/approve", roles=["admin"])
def approve(ctx):
    e = ctx.get("expenses", ctx.params["id"])
    if e["status"] != "submitted":
        raise HttpError(409, "only submitted expenses can be approved")
    ctx.exec("UPDATE expenses SET status='approved', decided_by=? WHERE id=?", (ctx.user["id"], e["id"]))
    return ctx.get("expenses", e["id"])


@app.route("POST", "/api/expenses/<id>/reject", roles=["admin"])
def reject(ctx):
    e = ctx.get("expenses", ctx.params["id"])
    if e["status"] != "submitted":
        raise HttpError(409, "only submitted expenses can be rejected")
    ctx.exec("UPDATE expenses SET status='rejected', decided_by=?, reject_reason=? WHERE id=?", (ctx.user["id"], ctx.need("reason")[0], e["id"]))
    return ctx.get("expenses", e["id"])


@app.route("POST", "/api/expenses/<id>/reimburse", roles=["admin"])
def reimburse(ctx):
    e = ctx.get("expenses", ctx.params["id"])
    if e["status"] != "approved":
        raise HttpError(409, "only approved expenses can be reimbursed")
    ctx.exec("UPDATE expenses SET status='reimbursed' WHERE id=?", [e["id"]])
    return ctx.get("expenses", e["id"])


@app.route("GET", "/api/reports/by-category", roles=["admin"])
def by_category(ctx):
    """Approved + reimbursed spend per category for ?month=YYYY-MM."""
    month = ctx.query.get("month", "2026-03")
    rows = ctx.q("SELECT category, SUM(amount_cents) AS total FROM expenses WHERE org_id=? AND status IN ('approved','reimbursed') "
                 "AND incurred_on>=? AND incurred_on<=? GROUP BY category", (ctx.user["org_id"], month + "-01", month + "-30"))
    return {"month": month, "categories": {r["category"]: r["total"] for r in rows}}


@app.route("GET", "/api/budgets/status", roles=["admin"])
def budgets(ctx):
    """Committed spend (submitted, approved, reimbursed) vs monthly limit."""
    month = ctx.query.get("month", "2026-03")
    out = {}
    for b in ctx.q("SELECT * FROM budgets WHERE org_id=?", [ctx.user["org_id"]]):
        spent = ctx.one("SELECT COALESCE(SUM(amount_cents),0) AS s FROM expenses WHERE org_id=? AND category=? AND status!='draft' AND incurred_on LIKE ?",
                        (ctx.user["org_id"], b["category"], month + "%"))["s"]
        out[b["category"]] = {"limit_cents": b["monthly_limit_cents"], "spent_cents": spent, "remaining_cents": b["monthly_limit_cents"] - spent}
    return out
