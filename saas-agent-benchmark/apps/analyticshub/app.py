import datetime as dt
from pathlib import Path

from common.framework import App, HttpError, created

SCHEMA = """
CREATE TABLE events(id INTEGER PRIMARY KEY, org_id INT, name TEXT, user_key TEXT, ts TEXT);
CREATE TABLE dashboards(id INTEGER PRIMARY KEY, org_id INT, name TEXT);
CREATE TABLE widgets(id INTEGER PRIMARY KEY, dashboard_id INT REFERENCES dashboards(id), title TEXT, kind TEXT, event_name TEXT, window_days INT);
"""


def seed(db):
    for u in range(1, 21):
        day = 1 + u % 10
        db.exec("INSERT INTO events VALUES(NULL,1,'signup',?,?)", (f"user{u}", f"2026-03-{day:02d}T09:00:00"))
        if u % 2 == 0:
            db.exec("INSERT INTO events VALUES(NULL,1,'activate',?,?)", (f"user{u}", f"2026-03-{day:02d}T10:00:00"))
        if u % 4 == 0:
            db.exec("INSERT INTO events VALUES(NULL,1,'purchase',?,?)", (f"user{u}", f"2026-03-{day:02d}T11:00:00"))
    for i in range(5):
        db.exec("INSERT INTO events VALUES(NULL,1,'pageview',NULL,?)", (f"2026-03-1{i}T12:00:00",))
    db.exec("INSERT INTO events VALUES(NULL,2,'signup','gx1','2026-03-05T09:00:00')")
    db.exec("INSERT INTO dashboards VALUES(1,1,'Growth')")
    db.exec("INSERT INTO dashboards VALUES(2,2,'Globex KPIs')")
    db.exec("INSERT INTO widgets VALUES(NULL,1,'Signups (14d)','count','signup',14)")
    db.exec("INSERT INTO widgets VALUES(NULL,1,'Active users (14d)','unique_users','activate',14)")
    db.exec("INSERT INTO widgets VALUES(NULL,2,'Globex signups','count','signup',30)")


app = App("analyticshub", "AnalyticsHub", 9119, SCHEMA, seed, static_dir=Path(__file__).parent / "static",
          description="Product analytics: event ingestion, counts, unique users, funnels and dashboards.")


def count_filter(ctx):
    where, args = "org_id=? AND name=?", [ctx.user["org_id"], ctx.query.get("event", "")]
    if ctx.query.get("from"):
        where += " AND ts>=?"
        args.append(ctx.query["from"])
    if ctx.query.get("to"):
        where += " AND ts<?"
        args.append(ctx.query["to"])
    return where, args


@app.route("POST", "/api/events", roles=["admin", "member"])
def ingest(ctx):
    name = ctx.need("name")[0]
    eid = ctx.exec("INSERT INTO events VALUES(NULL,?,?,?,?)", (ctx.user["org_id"], name, ctx.body.get("user_key"), ctx.body.get("ts", ctx.now)))
    return created({"id": eid})


@app.route("POST", "/api/events/batch", roles=["admin", "member"])
def ingest_batch(ctx):
    events = ctx.body.get("events") or []
    if not events or len(events) > 100:
        raise HttpError(400, "batch must contain 1-100 events")
    for e in events:
        if not e.get("name"):
            raise HttpError(400, "every event needs a name")
    for e in events:
        ctx.exec("INSERT INTO events VALUES(NULL,?,?,?,?)", (ctx.user["org_id"], e["name"], e.get("user_key"), e.get("ts", ctx.now)))
    return created({"ingested": len(events)})


@app.route("GET", "/api/metrics/count")
def count(ctx):
    """Event count for ?event= between ?from= and ?to= (dates, both inclusive)."""
    where, args = count_filter(ctx)
    return {"event": ctx.query.get("event"), "count": ctx.one(f"SELECT COUNT(*) AS n FROM events WHERE {where}", args)["n"]}


@app.route("GET", "/api/metrics/unique-users")
def unique_users(ctx):
    where, args = count_filter(ctx)
    return {"event": ctx.query.get("event"), "unique_users": ctx.one(f"SELECT COUNT(DISTINCT COALESCE(user_key,'anonymous')) AS n FROM events WHERE {where}", args)["n"]}


@app.route("GET", "/api/metrics/funnel")
def funnel(ctx):
    """Ordered funnel for ?steps=a,b,c: users who performed each step after the previous one."""
    steps = [s for s in ctx.query.get("steps", "").split(",") if s]
    if len(steps) < 2:
        raise HttpError(400, "need at least two steps")
    users = None
    out = []
    for s in steps:
        found = {r["user_key"] for r in ctx.q("SELECT DISTINCT user_key FROM events WHERE org_id=? AND name=? AND user_key IS NOT NULL", (ctx.user["org_id"], s))}
        users = found if users is None else users & found
        out.append({"step": s, "users": len(users)})
    return {"steps": out}


@app.route("GET", "/api/dashboards")
def dashboards(ctx):
    return ctx.page("SELECT * FROM dashboards WHERE org_id=%d ORDER BY id" % ctx.user["org_id"])


@app.route("POST", "/api/dashboards/<id>/widgets", roles=["admin", "member"])
def add_widget(ctx):
    d = ctx.get("dashboards", ctx.params["id"])
    title, kind, ev = ctx.need("title", "kind", "event_name")
    if kind not in ("count", "unique_users"):
        raise HttpError(400, "unknown widget kind")
    wid = ctx.exec("INSERT INTO widgets VALUES(NULL,?,?,?,?,?)", (d["id"], title, kind, ev, ctx.body.get("window_days", 7)))
    return created(ctx.one("SELECT * FROM widgets WHERE id=?", [wid]))


@app.route("GET", "/api/dashboards/<id>/data")
def dashboard_data(ctx):
    d = ctx.get("dashboards", ctx.params["id"], org=False)
    out = []
    for w in ctx.q("SELECT * FROM widgets WHERE dashboard_id=?", [d["id"]]):
        since = (ctx.today - dt.timedelta(days=w["window_days"])).isoformat()
        expr = "COUNT(*)" if w["kind"] == "count" else "COUNT(DISTINCT user_key)"
        v = ctx.one(f"SELECT {expr} AS n FROM events WHERE org_id=? AND name=? AND ts>=?", (d["org_id"], w["event_name"], since))["n"]
        out.append({"title": w["title"], "kind": w["kind"], "value": v})
    return {"dashboard": d["name"], "widgets": out}


@app.route("GET", "/api/metrics/summary")
def summary(ctx):
    """Event counts by name."""
    return ctx.page("SELECT name AS event, COUNT(*) AS count FROM events WHERE org_id=%d GROUP BY name ORDER BY name" % ctx.user["org_id"])
