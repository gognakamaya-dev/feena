from pathlib import Path

from common.framework import App, HttpError, created

SCHEMA = """
CREATE TABLE lists(id INTEGER PRIMARY KEY, org_id INT, name TEXT);
CREATE TABLE subscribers(id INTEGER PRIMARY KEY, org_id INT, email TEXT, status TEXT DEFAULT 'subscribed', UNIQUE(org_id,email));
CREATE TABLE list_members(list_id INT REFERENCES lists(id), subscriber_id INT REFERENCES subscribers(id), PRIMARY KEY(list_id,subscriber_id));
CREATE TABLE campaigns(id INTEGER PRIMARY KEY, org_id INT, list_id INT REFERENCES lists(id), subject TEXT, body TEXT, status TEXT DEFAULT 'draft',
  scheduled_at TEXT, sent_at TEXT, recipient_count INT DEFAULT 0);
CREATE TABLE deliveries(id INTEGER PRIMARY KEY, campaign_id INT REFERENCES campaigns(id), subscriber_id INT, opened_at TEXT);
"""


def seed(db):
    db.exec("INSERT INTO lists VALUES(1,1,'Newsletter')")
    db.exec("INSERT INTO lists VALUES(2,2,'Globex Updates')")
    statuses = ["subscribed"] * 6 + ["unsubscribed", "bounced"]
    for i, st in enumerate(statuses, 1):
        db.exec("INSERT INTO subscribers VALUES(?,?,?,?)", (i, 1, f"reader{i}@example.test", st))
        db.exec("INSERT INTO list_members VALUES(1,?)", (i,))
    db.exec("INSERT INTO subscribers VALUES(9,2,'fan@globex.test','subscribed')")
    db.exec("INSERT INTO list_members VALUES(2,9)")
    db.exec("INSERT INTO campaigns VALUES(1,1,1,'February digest','Hello!','sent',NULL,'2026-02-20T09:00:00',6)")
    for sid in range(1, 7):
        db.exec("INSERT INTO deliveries VALUES(NULL,1,?,?)", (sid, "2026-02-20T10:00:00" if sid <= 3 else None))
    db.exec("INSERT INTO campaigns VALUES(2,1,1,'March launch','Big news','draft',NULL,NULL,0)")
    db.exec("INSERT INTO campaigns VALUES(3,2,2,'Globex secret roadmap','Confidential','sent',NULL,'2026-03-01T09:00:00',1)")
    db.exec("INSERT INTO deliveries VALUES(NULL,3,9,'2026-03-01T10:00:00')")


app = App("mailforge", "MailForge", 9107, SCHEMA, seed, static_dir=Path(__file__).parent / "static",
          description="Email campaign management: lists, subscribers, scheduling and engagement stats.")


@app.route("GET", "/api/lists")
def lists(ctx):
    return ctx.page("SELECT l.*, (SELECT COUNT(*) FROM list_members m WHERE m.list_id=l.id) AS members FROM lists l WHERE org_id=%d" % ctx.user["org_id"])


@app.route("GET", "/api/lists/<id>/subscribers")
def list_subscribers(ctx):
    ctx.get("lists", ctx.params["id"])
    return ctx.page("SELECT s.* FROM subscribers s JOIN list_members m ON m.subscriber_id=s.id WHERE m.list_id=? ORDER BY s.id", [ctx.params["id"]])


@app.route("POST", "/api/lists/<id>/subscribers", roles=["admin", "member"])
def add_subscriber(ctx):
    lst = ctx.get("lists", ctx.params["id"])
    email = ctx.need("email")[0].strip().lower()
    s = ctx.one("SELECT * FROM subscribers WHERE org_id=? AND email=?", (ctx.user["org_id"], email))
    if s:
        ctx.exec("UPDATE subscribers SET status='subscribed' WHERE id=?", [s["id"]])
        sid = s["id"]
    else:
        sid = ctx.exec("INSERT INTO subscribers VALUES(NULL,?,?,'subscribed')", (ctx.user["org_id"], email))
    ctx.exec("INSERT OR IGNORE INTO list_members VALUES(?,?)", (lst["id"], sid))
    return created(ctx.get("subscribers", sid))


@app.route("POST", "/api/subscribers/<id>/unsubscribe")
def unsubscribe(ctx):
    s = ctx.get("subscribers", ctx.params["id"])
    ctx.exec("UPDATE subscribers SET status='unsubscribed' WHERE id=?", [s["id"]])
    return ctx.get("subscribers", s["id"])


@app.route("GET", "/api/campaigns")
def campaigns(ctx):
    return ctx.page("SELECT * FROM campaigns WHERE org_id=%d ORDER BY id" % ctx.user["org_id"])


@app.route("POST", "/api/campaigns", roles=["admin", "member"])
def add_campaign(ctx):
    list_id, subject, body = ctx.need("list_id", "subject", "body")
    ctx.get("lists", list_id)
    cid = ctx.exec("INSERT INTO campaigns VALUES(NULL,?,?,?,?,'draft',NULL,NULL,0)", (ctx.user["org_id"], list_id, subject, body))
    return created(ctx.get("campaigns", cid))


@app.route("POST", "/api/campaigns/<id>/schedule", roles=["admin", "member"])
def schedule(ctx):
    c = ctx.get("campaigns", ctx.params["id"])
    if c["status"] != "draft":
        raise HttpError(409, "only drafts can be scheduled")
    at = ctx.need("scheduled_at")[0]
    ctx.exec("UPDATE campaigns SET status='scheduled', scheduled_at=? WHERE id=?", (at, c["id"]))
    return ctx.get("campaigns", c["id"])


def deliver(ctx, c):
    rows = ctx.q("SELECT s.id FROM subscribers s JOIN list_members m ON m.subscriber_id=s.id WHERE m.list_id=? AND s.status!='bounced'", [c["list_id"]])
    for r in rows:
        ctx.exec("INSERT INTO deliveries VALUES(NULL,?,?,NULL)", (c["id"], r["id"]))
    ctx.exec("UPDATE campaigns SET status='sent', sent_at=?, recipient_count=? WHERE id=?", (ctx.now, len(rows), c["id"]))


@app.route("POST", "/api/campaigns/<id>/send", roles=["admin", "member"])
def send(ctx):
    c = ctx.get("campaigns", ctx.params["id"])
    if c["status"] not in ("draft", "scheduled"):
        raise HttpError(409, "campaign already sent")
    deliver(ctx, c)
    return ctx.get("campaigns", c["id"])


@app.route("POST", "/api/scheduler/run", roles=["admin"])
def run_scheduler(ctx):
    """Send every scheduled campaign whose scheduled_at is due."""
    sent = []
    for c in ctx.q("SELECT * FROM campaigns WHERE org_id=? AND status='scheduled'", [ctx.user["org_id"]]):
        if c["scheduled_at"] <= ctx.now:
            deliver(ctx, c)
            sent.append(c["id"])
    return {"sent": sent}


@app.route("GET", "/api/campaigns/<id>/stats")
def stats(ctx):
    c = ctx.get("campaigns", ctx.params["id"], org=False)
    opens = ctx.one("SELECT COUNT(*) AS n FROM deliveries WHERE campaign_id=? AND opened_at IS NOT NULL", [c["id"]])["n"]
    n = c["recipient_count"]
    return {"campaign_id": c["id"], "recipients": n, "opens": opens, "open_rate": round(opens / n, 2) if n else 0}


@app.route("POST", "/api/track/open/<cid>/<sid>", auth=False)
def track(ctx):
    ctx.exec("UPDATE deliveries SET opened_at=COALESCE(opened_at,?) WHERE campaign_id=? AND subscriber_id=?", (ctx.now, ctx.params["cid"], ctx.params["sid"]))
    return {"ok": True}
