import calendar
import datetime as dt
from pathlib import Path

from common.framework import App, HttpError, created

SCHEMA = """
CREATE TABLE plans(id INTEGER PRIMARY KEY, org_id INT, name TEXT, price_cents INT, interval TEXT, trial_days INT DEFAULT 0);
CREATE TABLE coupons(code TEXT, org_id INT, percent INT, max_redemptions INT, redeemed INT DEFAULT 0, PRIMARY KEY(org_id, code));
CREATE TABLE customers(id INTEGER PRIMARY KEY, org_id INT, email TEXT, name TEXT);
CREATE TABLE subscriptions(id INTEGER PRIMARY KEY, org_id INT, customer_id INT REFERENCES customers(id), plan_id INT REFERENCES plans(id), status TEXT,
  period_start TEXT, period_end TEXT, cancel_at_period_end INT DEFAULT 0, canceled_on TEXT, coupon_code TEXT);
CREATE TABLE invoices(id INTEGER PRIMARY KEY, subscription_id INT REFERENCES subscriptions(id), amount_cents INT, kind TEXT, created_on TEXT);
"""


def add_months(d, n):
    m = d.month - 1 + n
    y, m = d.year + m // 12, m % 12 + 1
    return d.replace(year=y, month=m, day=min(d.day, calendar.monthrange(y, m)[1]))


def advance(d, interval):
    return add_months(d, 12 if interval == "year" else 1)


def seed(db):
    for i, (n, pr, iv, tr) in enumerate([("Starter", 1000, "month", 0), ("Pro", 3000, "month", 0), ("Annual Pro", 30000, "year", 0), ("Team", 5000, "month", 14)], 1):
        db.exec("INSERT INTO plans VALUES(?,1,?,?,?,?)", (i, n, pr, iv, tr))
    db.exec("INSERT INTO plans VALUES(5,2,'Globex Plan',9900,'month',0)")
    db.exec("INSERT INTO coupons VALUES('LAUNCH20',1,20,1,0)")
    db.exec("INSERT INTO coupons VALUES('WELCOME10',1,10,100,0)")
    for i in range(1, 6):
        db.exec("INSERT INTO customers VALUES(?,1,?,?)", (i, f"cust{i}@example.test", f"Customer {i}"))
    db.exec("INSERT INTO customers VALUES(6,2,'gx@globex.test','Globex Customer')")
    for cid, pid, st, ps, pe in [(1, 1, "active", "2026-03-01", "2026-04-01"), (2, 2, "active", "2026-02-20", "2026-03-20"), (3, 3, "active", "2025-08-01", "2026-08-01"), (4, 2, "past_due", "2026-02-10", "2026-03-10")]:
        sid = db.exec("INSERT INTO subscriptions VALUES(NULL,1,?,?,?,?,?,0,NULL,NULL)", (cid, pid, st, ps, pe))
        db.exec("INSERT INTO invoices VALUES(NULL,?,?,?,?)", (sid, 3000 if pid == 2 else 1000, "renewal", ps))
    db.exec("INSERT INTO subscriptions VALUES(100,2,6,5,'active','2026-03-01','2026-04-01',0,NULL,NULL)")


app = App("subscriptionpilot", "SubscriptionPilot", 9120, SCHEMA, seed, static_dir=Path(__file__).parent / "static",
          description="Subscription billing: plans, trials, coupons, plan changes with proration, cancellations and renewals.")


def present(ctx, s):
    s = dict(s)
    s["invoices"] = ctx.q("SELECT * FROM invoices WHERE subscription_id=? ORDER BY id", [s["id"]])
    return s


def invoice(ctx, sid, amount, kind):
    ctx.exec("INSERT INTO invoices VALUES(NULL,?,?,?,?)", (sid, amount, kind, ctx.today.isoformat()))


@app.route("GET", "/api/plans")
def plans(ctx):
    return ctx.page("SELECT * FROM plans WHERE org_id=%d ORDER BY id" % ctx.user["org_id"])


@app.route("GET", "/api/subscriptions")
def subscriptions(ctx):
    sql, args = "SELECT s.*, p.price_cents, p.interval FROM subscriptions s JOIN plans p ON p.id=s.plan_id WHERE s.org_id=?", [ctx.user["org_id"]]
    if ctx.query.get("status"):
        sql += " AND s.status=?"
        args.append(ctx.query["status"])
    return ctx.page(sql + " ORDER BY s.id", args)


@app.route("GET", "/api/subscriptions/<id>")
def get_subscription(ctx):
    return present(ctx, ctx.get("subscriptions", ctx.params["id"]))


@app.route("POST", "/api/subscriptions", roles=["admin", "member"])
def subscribe(ctx):
    cust, plan_id = ctx.need("customer_id", "plan_id")
    ctx.get("customers", cust)
    plan = ctx.get("plans", plan_id)
    price, code = plan["price_cents"], ctx.body.get("coupon_code")
    if code:
        c = ctx.one("SELECT * FROM coupons WHERE org_id=? AND code=?", (ctx.user["org_id"], code))
        if not c:
            raise HttpError(400, "unknown coupon")
        price = round(price * (100 - c["percent"]) / 100)
        ctx.exec("UPDATE coupons SET redeemed=redeemed+1 WHERE org_id=? AND code=?", (ctx.user["org_id"], code))
    today = ctx.today
    trial = plan["trial_days"] > 0
    end = today + dt.timedelta(days=plan["trial_days"]) if trial else advance(today, plan["interval"])
    sid = ctx.exec("INSERT INTO subscriptions VALUES(NULL,?,?,?,?,?,?,0,NULL,?)", (ctx.user["org_id"], cust, plan["id"], "trialing" if trial else "active", today.isoformat(), end.isoformat(), code))
    invoice(ctx, sid, price, "initial")
    return created(present(ctx, ctx.get("subscriptions", sid)))


@app.route("POST", "/api/subscriptions/<id>/cancel", roles=["admin", "member"])
def cancel(ctx):
    s = ctx.get("subscriptions", ctx.params["id"])
    if s["status"] == "canceled":
        raise HttpError(409, "already canceled")
    if ctx.body.get("at_period_end", True):
        ctx.exec("UPDATE subscriptions SET cancel_at_period_end=1 WHERE id=?", [s["id"]])
    else:
        ctx.exec("UPDATE subscriptions SET status='canceled', canceled_on=? WHERE id=?", (ctx.today.isoformat(), s["id"]))
    return present(ctx, ctx.get("subscriptions", s["id"]))


@app.route("POST", "/api/subscriptions/<id>/change-plan", roles=["admin", "member"])
def change_plan(ctx):
    """Switch plan ({plan_id, effective_on?}); upgrades are charged pro rata for the rest of the period."""
    s = ctx.get("subscriptions", ctx.params["id"])
    new = ctx.get("plans", ctx.need("plan_id")[0])
    old = ctx.get("plans", s["plan_id"])
    if s["status"] != "active" or new["interval"] != old["interval"]:
        raise HttpError(409, "only active subscriptions can change to a plan with the same interval")
    diff = new["price_cents"] - old["price_cents"]
    if diff > 0:
        invoice(ctx, s["id"], diff, "proration")
    ctx.exec("UPDATE subscriptions SET plan_id=? WHERE id=?", (new["id"], s["id"]))
    return present(ctx, ctx.get("subscriptions", s["id"]))


@app.route("POST", "/api/jobs/renew", roles=["admin"])
def renew(ctx):
    """Billing run: renew or cancel subscriptions whose period ended on or before ?as_of (default today)."""
    as_of = ctx.body.get("as_of", ctx.today.isoformat())
    out = {"renewed": [], "canceled": [], "converted": []}
    for s in ctx.q("SELECT * FROM subscriptions WHERE org_id=? AND status IN ('active','trialing') AND period_end<=?", (ctx.user["org_id"], as_of)):
        plan = ctx.get("plans", s["plan_id"])
        end = dt.date.fromisoformat(s["period_end"])
        if s["cancel_at_period_end"]:
            invoice(ctx, s["id"], plan["price_cents"], "renewal")
            ctx.exec("UPDATE subscriptions SET status='canceled', canceled_on=? WHERE id=?", (s["period_end"], s["id"]))
            out["canceled"].append(s["id"])
        else:
            invoice(ctx, s["id"], plan["price_cents"], "renewal")
            ctx.exec("UPDATE subscriptions SET status='active', period_start=?, period_end=? WHERE id=?", (s["period_end"], advance(end, plan["interval"]).isoformat(), s["id"]))
            out["converted" if s["status"] == "trialing" else "renewed"].append(s["id"])
    return out


@app.route("GET", "/api/reports/mrr", roles=["admin"])
def mrr(ctx):
    rows = ctx.q("SELECT p.price_cents, p.interval FROM subscriptions s JOIN plans p ON p.id=s.plan_id WHERE s.org_id=? AND s.status='active'", [ctx.user["org_id"]])
    return {"mrr_cents": sum(round(r["price_cents"] / 12) if r["interval"] == "year" else r["price_cents"] for r in rows)}
