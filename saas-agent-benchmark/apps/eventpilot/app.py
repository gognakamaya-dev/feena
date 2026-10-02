from pathlib import Path

from common.framework import App, HttpError, created

SCHEMA = """
CREATE TABLE events(id INTEGER PRIMARY KEY, org_id INT, title TEXT, starts_on TEXT, capacity INT, price_cents INT, status TEXT DEFAULT 'draft');
CREATE TABLE registrations(id INTEGER PRIMARY KEY, event_id INT REFERENCES events(id), name TEXT, email TEXT, status TEXT, promo_code TEXT, paid_cents INT, created_at TEXT);
CREATE TABLE promos(id INTEGER PRIMARY KEY, event_id INT REFERENCES events(id), code TEXT, percent INT, max_uses INT, used INT DEFAULT 0);
"""


def seed(db):
    db.exec("INSERT INTO events VALUES(1,1,'DevSummit 2026','2026-05-10',100,19999,'published')")
    db.exec("INSERT INTO events VALUES(2,1,'Intimate Workshop','2026-04-02',2,4900,'published')")
    db.exec("INSERT INTO events VALUES(3,1,'Draft Meetup','2026-06-01',50,0,'draft')")
    db.exec("INSERT INTO events VALUES(4,2,'Globex Offsite','2026-07-01',20,0,'published')")
    db.exec("INSERT INTO promos VALUES(1,1,'SAVE10',10,5,0)")
    db.exec("INSERT INTO promos VALUES(2,2,'HALF',50,1,0)")
    for i in range(1, 9):
        db.exec("INSERT INTO registrations VALUES(NULL,1,?,?,'confirmed',NULL,19999,'2026-03-01')", (f"Guest {i}", f"guest{i}@example.test"))


app = App("eventpilot", "EventPilot", 9111, SCHEMA, seed, static_dir=Path(__file__).parent / "static",
          description="Event registration with capacity, waitlists and promo codes.")


@app.route("GET", "/api/public/events", auth=False)
def public_events(ctx):
    return ctx.page("SELECT id,title,starts_on,capacity,price_cents FROM events WHERE status='published' ORDER BY starts_on")


@app.route("GET", "/api/events")
def events(ctx):
    return ctx.page("SELECT * FROM events WHERE org_id=%d ORDER BY id" % ctx.user["org_id"])


@app.route("POST", "/api/events", roles=["admin", "member"])
def add_event(ctx):
    title, starts, cap = ctx.need("title", "starts_on", "capacity")
    eid = ctx.exec("INSERT INTO events VALUES(NULL,?,?,?,?,?,'published')", (ctx.user["org_id"], title, starts, cap, ctx.body.get("price_cents", 0)))
    return created(ctx.get("events", eid))


@app.route("POST", "/api/events/<id>/promos", roles=["admin"])
def add_promo(ctx):
    ev = ctx.get("events", ctx.params["id"])
    code, pct = ctx.need("code", "percent")
    pid = ctx.exec("INSERT INTO promos VALUES(NULL,?,?,?,?,0)", (ev["id"], code, pct, ctx.body.get("max_uses", 100)))
    return created(ctx.one("SELECT * FROM promos WHERE id=?", [pid]))


def confirmed(ctx, eid):
    return ctx.one("SELECT COUNT(*) AS n FROM registrations WHERE event_id=? AND status='confirmed'", [eid])["n"]


@app.route("POST", "/api/public/events/<id>/register", auth=False)
def register(ctx):
    ev = ctx.one("SELECT * FROM events WHERE id=? AND status='published'", [ctx.params["id"]])
    if not ev:
        raise HttpError(404, "event not found")
    name, email = ctx.need("name", "email")
    if ctx.one("SELECT 1 FROM registrations WHERE event_id=? AND email=? AND status!='cancelled'", (ev["id"], email)):
        raise HttpError(409, "already registered")
    price, code = ev["price_cents"], ctx.body.get("promo_code")
    if code:
        p = ctx.one("SELECT * FROM promos WHERE event_id=? AND code=? AND used<max_uses", (ev["id"], code))
        if p:
            price = price * (100 - p["percent"]) // 100
            ctx.exec("UPDATE promos SET used=used+1 WHERE id=?", [p["id"]])
    status = "confirmed" if confirmed(ctx, ev["id"]) <= ev["capacity"] else "waitlisted"
    rid = ctx.exec("INSERT INTO registrations VALUES(NULL,?,?,?,?,?,?,?)", (ev["id"], name, email, status, code, price if status == "confirmed" else 0, ctx.now))
    return created(ctx.one("SELECT * FROM registrations WHERE id=?", [rid]))


@app.route("POST", "/api/registrations/<id>/cancel", roles=["admin", "member"])
def cancel(ctx):
    r = ctx.one("SELECT r.* FROM registrations r JOIN events e ON e.id=r.event_id WHERE r.id=? AND e.org_id=?", (ctx.params["id"], ctx.user["org_id"]))
    if not r:
        raise HttpError(404, "registration not found")
    ctx.exec("UPDATE registrations SET status='cancelled' WHERE id=?", [r["id"]])
    if r["status"] in ("confirmed", "cancelled"):
        nxt = ctx.one("SELECT * FROM registrations WHERE event_id=? AND status='waitlisted' ORDER BY id DESC LIMIT 1", [r["event_id"]])
        if nxt:
            ev = ctx.get("events", r["event_id"])
            ctx.exec("UPDATE registrations SET status='confirmed', paid_cents=? WHERE id=?", (ev["price_cents"], nxt["id"]))
    return ctx.one("SELECT * FROM registrations WHERE id=?", [r["id"]])


@app.route("GET", "/api/events/<id>/registrations", roles=["admin", "member"])
def registrations(ctx):
    ctx.get("events", ctx.params["id"])
    return ctx.page("SELECT * FROM registrations WHERE event_id=? ORDER BY id", [ctx.params["id"]])


@app.route("GET", "/api/events/<id>/stats", roles=["admin", "member"])
def stats(ctx):
    ev = ctx.get("events", ctx.params["id"])
    rows = ctx.q("SELECT status, paid_cents FROM registrations WHERE event_id=?", [ev["id"]])
    n = sum(r["status"] == "confirmed" for r in rows)
    return {"confirmed": n, "waitlisted": sum(r["status"] == "waitlisted" for r in rows), "capacity_left": ev["capacity"] - n,
            "revenue_cents": sum(r["paid_cents"] for r in rows if r["status"] == "confirmed")}
