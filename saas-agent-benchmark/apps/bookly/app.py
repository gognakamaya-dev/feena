import datetime as dt
from pathlib import Path

from common.framework import App, HttpError, created

SCHEMA = """
CREATE TABLE services(id INTEGER PRIMARY KEY, org_id INT, name TEXT, duration_min INT, price_cents INT);
CREATE TABLE staff(id INTEGER PRIMARY KEY, org_id INT, name TEXT);
CREATE TABLE appointments(id INTEGER PRIMARY KEY, org_id INT, service_id INT REFERENCES services(id), staff_id INT REFERENCES staff(id),
  customer_name TEXT, customer_email TEXT, start TEXT, end TEXT, status TEXT DEFAULT 'booked', price_cents INT);
"""
OPEN_H, CLOSE_H, FMT = 9, 17, "%Y-%m-%dT%H:%M"


def seed(db):
    for sid, n, d, p in [(1, "Haircut", 30, 4500), (2, "Colour", 90, 12000), (3, "Consultation", 60, 6000)]:
        db.exec("INSERT INTO services VALUES(?,?,?,?,?)", (sid, 1, n, d, p))
    db.exec("INSERT INTO services VALUES(4,2,'Globex Service',30,1000)")
    for sid, n, org in [(1, "Alice", 1), (2, "Bob", 1), (3, "Globex Gina", 2)]:
        db.exec("INSERT INTO staff VALUES(?,?,?)", (sid, org, n))
    for i, (day, hr, st) in enumerate([("2026-03-16", 9, 1), ("2026-03-16", 11, 1), ("2026-03-17", 10, 2), ("2026-03-18", 14, 1)]):
        s = dt.datetime.fromisoformat(f"{day}T{hr:02d}:00")
        db.exec("INSERT INTO appointments VALUES(NULL,1,3,?,?,?,?,?,'booked',6000)", (st, f"Client {i}", f"c{i}@example.test", s.strftime(FMT), (s + dt.timedelta(minutes=60)).strftime(FMT)))
    db.exec("INSERT INTO appointments VALUES(NULL,2,4,3,'G Client','g@example.test','2026-03-16T09:00','2026-03-16T09:30','booked',1000)")


app = App("bookly", "Bookly", 9104, SCHEMA, seed, static_dir=Path(__file__).parent / "static",
          description="Appointment scheduling for salons and clinics.")


def parse(s):
    try:
        return dt.datetime.strptime(s, FMT)
    except (TypeError, ValueError):
        raise HttpError(400, "start must be YYYY-MM-DDTHH:MM")


def overlaps(a_start, a_end, b_start, b_end):
    return a_start <= b_end and a_end >= b_start


def conflicts(ctx, staff_id, start, end):
    for a in ctx.q("SELECT * FROM appointments WHERE staff_id=? AND status='booked'", [staff_id]):
        if overlaps(start, end, parse(a["start"]), parse(a["end"])):
            return a
    return None


def window_check(start, end):
    if start.hour < OPEN_H or end > start.replace(hour=CLOSE_H, minute=0):
        raise HttpError(400, "outside working hours (09:00-17:00)")


@app.route("GET", "/api/services")
def services(ctx):
    return ctx.page("SELECT * FROM services WHERE org_id=%d" % ctx.user["org_id"])


@app.route("GET", "/api/availability")
def availability(ctx):
    """Free slots for ?staff_id=&service_id=&date=YYYY-MM-DD on a 30 minute grid."""
    staff = ctx.get("staff", ctx.query.get("staff_id"))
    svc = ctx.get("services", ctx.query.get("service_id"))
    day = dt.datetime.strptime(ctx.query["date"], "%Y-%m-%d")
    booked = ctx.q("SELECT * FROM appointments WHERE staff_id=? AND start LIKE ?", (staff["id"], ctx.query["date"] + "%"))
    slots, t = [], day.replace(hour=OPEN_H)
    while t + dt.timedelta(minutes=svc["duration_min"]) <= day.replace(hour=CLOSE_H):
        e = t + dt.timedelta(minutes=svc["duration_min"])
        if not any(t < parse(a["end"]) and e > parse(a["start"]) for a in booked):
            slots.append(t.strftime("%H:%M"))
        t += dt.timedelta(minutes=30)
    return {"date": ctx.query["date"], "slots": slots}


@app.route("GET", "/api/appointments")
def list_appts(ctx):
    sql, args = "SELECT * FROM appointments WHERE org_id=?", [ctx.user["org_id"]]
    for col in ("status", "staff_id"):
        if ctx.query.get(col):
            sql += f" AND {col}=?"
            args.append(ctx.query[col])
    if ctx.query.get("date"):
        sql += " AND start LIKE ?"
        args.append(ctx.query["date"] + "%")
    return ctx.page(sql + " ORDER BY start", args)


@app.route("POST", "/api/appointments", roles=["admin", "member"])
def book(ctx):
    sid, staff_id, start_s, name, email = ctx.need("service_id", "staff_id", "start", "customer_name", "customer_email")
    svc, staff = ctx.get("services", sid), ctx.get("staff", staff_id)
    start = parse(start_s)
    end = start + dt.timedelta(minutes=svc["duration_min"])
    window_check(start, end)
    if conflicts(ctx, staff["id"], start, end):
        raise HttpError(409, "time slot unavailable")
    aid = ctx.exec("INSERT INTO appointments VALUES(NULL,?,?,?,?,?,?,?,'booked',?)", (
        ctx.user["org_id"], sid, staff["id"], name, email, start.strftime(FMT), end.strftime(FMT), svc["price_cents"]))
    return created(ctx.one("SELECT * FROM appointments WHERE id=?", [aid]))


@app.route("POST", "/api/appointments/<id>/cancel", roles=["admin", "member"])
def cancel(ctx):
    a = ctx.get("appointments", ctx.params["id"], org=False)
    ctx.exec("UPDATE appointments SET status='cancelled' WHERE id=?", [a["id"]])
    return ctx.get("appointments", a["id"], org=False)


@app.route("POST", "/api/appointments/<id>/reschedule", roles=["admin", "member"])
def reschedule(ctx):
    a = ctx.get("appointments", ctx.params["id"])
    if a["status"] != "booked":
        raise HttpError(409, "only booked appointments can be moved")
    start = parse(ctx.need("start")[0])
    end = start + (parse(a["end"]) - parse(a["start"]))
    window_check(start, end)
    ctx.exec("UPDATE appointments SET start=?, end=? WHERE id=?", (start.strftime(FMT), end.strftime(FMT), a["id"]))
    return ctx.get("appointments", a["id"])
