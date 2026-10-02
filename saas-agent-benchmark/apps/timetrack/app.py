import datetime as dt
from pathlib import Path

from common.framework import App, HttpError, created

SCHEMA = """
CREATE TABLE entries(id INTEGER PRIMARY KEY, org_id INT, user_id INT REFERENCES users(id), project TEXT, start_at TEXT, end_at TEXT, note TEXT);
CREATE TABLE timesheets(user_id INT REFERENCES users(id), week_start TEXT, status TEXT, PRIMARY KEY(user_id, week_start));
"""
FMT = "%Y-%m-%dT%H:%M"
MAX_HOURS = 16


def seed(db):
    for day in range(9, 14):  # Mon-Fri of week 2026-03-09: 8h/day for Max (user 2)
        db.exec("INSERT INTO entries VALUES(NULL,1,2,'Apollo',?,?,'')", (f"2026-03-{day:02d}T09:00", f"2026-03-{day:02d}T17:00"))
    db.exec("INSERT INTO entries VALUES(NULL,1,1,'Admin',?,?,'planning')", ("2026-03-10T10:00", "2026-03-10T12:00"))
    db.exec("INSERT INTO entries VALUES(NULL,2,5,'Globex',?,?,'')", ("2026-03-10T10:00", "2026-03-10T18:00"))


app = App("timetrack", "TimeTrack", 9117, SCHEMA, seed, static_dir=Path(__file__).parent / "static",
          description="Employee time tracking: clock in/out, manual entries, weekly timesheets, approvals and overtime.")


def p(s):
    try:
        return dt.datetime.strptime(s, FMT)
    except (TypeError, ValueError):
        raise HttpError(400, "timestamps must be YYYY-MM-DDTHH:MM")


def present(e):
    e = dict(e)
    e["minutes"] = int((p(e["end_at"]) - p(e["start_at"])).total_seconds() // 60) if e["end_at"] else None
    return e


def week_of(ts):
    d = p(ts)
    return (d - dt.timedelta(days=d.weekday())).date().isoformat()


@app.route("GET", "/api/entries")
def entries(ctx):
    sql, args = "SELECT * FROM entries WHERE org_id=?", [ctx.user["org_id"]]
    if ctx.user["role"] != "admin":
        sql += " AND user_id=?"
        args.append(ctx.user["id"])
    if ctx.query.get("from"):
        sql += " AND start_at>=?"
        args.append(ctx.query["from"])
    if ctx.query.get("to"):
        sql += " AND start_at<?"
        args.append(ctx.query["to"])
    res = ctx.page(sql + " ORDER BY start_at", args)
    res["items"] = [present(e) for e in res["items"]]
    return res


@app.route("POST", "/api/entries", roles=["admin", "member"])
def add_entry(ctx):
    project, start, end = ctx.need("project", "start_at", "end_at")
    s, e = p(start), p(end)
    if (e - s) > dt.timedelta(hours=MAX_HOURS):
        raise HttpError(400, f"entries are limited to {MAX_HOURS} hours")
    for o in ctx.q("SELECT * FROM entries WHERE user_id=? AND end_at IS NULL", [ctx.user["id"]]):
        if p(o["start_at"]) < e:
            raise HttpError(409, "overlaps a running timer")
    eid = ctx.exec("INSERT INTO entries VALUES(NULL,?,?,?,?,?,?)", (ctx.user["org_id"], ctx.user["id"], project, start, end, ctx.body.get("note", "")))
    return created(present(ctx.one("SELECT * FROM entries WHERE id=?", [eid])))


@app.route("PUT", "/api/entries/<id>", roles=["admin", "member"])
def edit_entry(ctx):
    e = ctx.one("SELECT * FROM entries WHERE id=? AND user_id=?", (ctx.params["id"], ctx.user["id"]))
    if not e:
        raise HttpError(404, "entry not found")
    ctx.exec("UPDATE entries SET project=?, start_at=?, end_at=?, note=? WHERE id=?", (
        ctx.body.get("project", e["project"]), ctx.body.get("start_at", e["start_at"]), ctx.body.get("end_at", e["end_at"]), ctx.body.get("note", e["note"]), e["id"]))
    return present(ctx.one("SELECT * FROM entries WHERE id=?", [e["id"]]))


@app.route("POST", "/api/clock-in", roles=["admin", "member"])
def clock_in(ctx):
    if ctx.one("SELECT 1 FROM entries WHERE user_id=? AND end_at IS NULL", [ctx.user["id"]]):
        raise HttpError(409, "already clocked in")
    eid = ctx.exec("INSERT INTO entries VALUES(NULL,?,?,?,?,NULL,'')", (ctx.user["org_id"], ctx.user["id"], ctx.body.get("project", "General"), ctx.now[:16]))
    return created(ctx.one("SELECT * FROM entries WHERE id=?", [eid]))


@app.route("POST", "/api/clock-out", roles=["admin", "member"])
def clock_out(ctx):
    e = ctx.one("SELECT * FROM entries WHERE user_id=? AND end_at IS NULL", [ctx.user["id"]])
    if not e:
        raise HttpError(409, "not clocked in")
    ctx.exec("UPDATE entries SET end_at=? WHERE id=?", (ctx.now[:16], e["id"]))
    return present(ctx.one("SELECT * FROM entries WHERE id=?", [e["id"]]))


@app.route("POST", "/api/timesheets/submit", roles=["admin", "member"])
def submit(ctx):
    ws = ctx.need("week_start")[0]
    ctx.exec("INSERT OR REPLACE INTO timesheets VALUES(?,?,'submitted')", (ctx.user["id"], ws))
    return created({"user_id": ctx.user["id"], "week_start": ws, "status": "submitted"})


@app.route("POST", "/api/timesheets/approve")
def approve(ctx):
    uid, ws = ctx.need("user_id", "week_start")
    t = ctx.one("SELECT * FROM timesheets WHERE user_id=? AND week_start=?", (uid, ws))
    if not t or t["status"] != "submitted":
        raise HttpError(409, "timesheet is not awaiting approval")
    ctx.exec("UPDATE timesheets SET status='approved' WHERE user_id=? AND week_start=?", (uid, ws))
    return {"user_id": uid, "week_start": ws, "status": "approved"}


@app.route("GET", "/api/reports/weekly", roles=["admin"])
def weekly(ctx):
    """Hours and overtime (>40h) per user for the Monday-starting ?week_start=."""
    ws = p(ctx.query.get("week_start", "") + "T00:00")
    we = ws + dt.timedelta(days=7)
    out = {}
    for e in ctx.q("SELECT * FROM entries WHERE org_id=? AND end_at IS NOT NULL AND start_at>=? AND start_at<?", (ctx.user["org_id"], ws.strftime(FMT), we.strftime(FMT))):
        out[e["user_id"]] = out.get(e["user_id"], 0) + (p(e["end_at"]) - p(e["start_at"])).total_seconds() / 3600
    return {"week_start": ctx.query["week_start"], "users": {str(u): {"hours": round(h, 2), "overtime": round(max(0, h - 40), 2)} for u, h in out.items()}}
