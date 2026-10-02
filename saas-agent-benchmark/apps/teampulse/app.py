from pathlib import Path

from common.framework import App, HttpError, created

SCHEMA = """
CREATE TABLE teams(id INTEGER PRIMARY KEY, org_id INT, name TEXT);
CREATE TABLE employees(id INTEGER PRIMARY KEY, org_id INT, team_id INT REFERENCES teams(id), name TEXT, email TEXT, title TEXT,
  hired_on TEXT, terminated_on TEXT, status TEXT DEFAULT 'active', salary_band TEXT);
CREATE TABLE pulses(id INTEGER PRIMARY KEY, employee_id INT REFERENCES employees(id), week TEXT, score INT, comment TEXT);
"""
WEEK = "2026-W11"


def seed(db):
    for i, n in enumerate(["Platform", "Growth", "Support"], 1):
        db.exec("INSERT INTO teams VALUES(?,1,?)", (i, n))
    db.exec("INSERT INTO teams VALUES(4,2,'Globex Ops')")
    emails = ["admin@acme.test", "member@acme.test", "viewer@acme.test"] + [f"emp{i}@acme.test" for i in range(4, 19)]
    names = ["Ada Admin", "Max Member", "Vera Viewer"] + [f"Employee {i}" for i in range(4, 19)]
    for i, (e, n) in enumerate(zip(emails, names), 1):
        term = "2026-02-01" if i == 18 else None
        db.exec("INSERT INTO employees VALUES(?,1,?,?,?,?,?,?,?,?)", (i, (i % 3) + 1, n, e, "Engineer", f"2025-{(i % 12) + 1:02d}-01", term, "terminated" if term else "active", "B" + str(i % 4)))
    db.exec("INSERT INTO employees VALUES(19,2,4,'Globex Gus','admin@globex.test','Ops','2025-01-01',NULL,'active','C1')")
    for i in range(4, 15):
        db.exec("INSERT INTO pulses VALUES(NULL,?,?,?,NULL)", (i, WEEK, 3 + i % 3))


app = App("teampulse", "TeamPulse", 9109, SCHEMA, seed, static_dir=Path(__file__).parent / "static",
          description="Employee and team analytics: headcount, weekly pulse surveys, engagement and attrition.")


@app.route("GET", "/api/teams")
def teams(ctx):
    return ctx.page("SELECT t.*, (SELECT COUNT(*) FROM employees e WHERE e.team_id=t.id AND e.status='active') AS headcount FROM teams t WHERE org_id=%d" % ctx.user["org_id"])


@app.route("GET", "/api/employees")
def employees(ctx):
    sql, args = "SELECT * FROM employees WHERE org_id=?", [ctx.user["org_id"]]
    if ctx.query.get("q"):
        sql += " AND name LIKE ?"
        args.append("%" + ctx.query["q"] + "%")
    elif ctx.query.get("team_id"):
        sql += " AND team_id=?"
        args.append(ctx.query["team_id"])
    return ctx.page(sql + " ORDER BY id", args)


@app.route("POST", "/api/employees", roles=["admin"])
def add_employee(ctx):
    name, email, team = ctx.need("name", "email", "team_id")
    ctx.get("teams", team)
    eid = ctx.exec("INSERT INTO employees VALUES(NULL,?,?,?,?,?,?,NULL,'active',?)", (ctx.user["org_id"], team, name, email, ctx.body.get("title", ""), ctx.body.get("hired_on", ctx.today.isoformat()), ctx.body.get("salary_band", "B1")))
    return created(ctx.get("employees", eid))


@app.route("POST", "/api/employees/<id>/terminate", roles=["admin"])
def terminate(ctx):
    e = ctx.get("employees", ctx.params["id"])
    ctx.exec("UPDATE employees SET status='terminated', terminated_on=? WHERE id=?", (ctx.body.get("date", ctx.today.isoformat()), e["id"]))
    return ctx.get("employees", e["id"])


@app.route("POST", "/api/employees/<id>/rehire", roles=["admin"])
def rehire(ctx):
    e = ctx.get("employees", ctx.params["id"])
    if e["status"] != "terminated":
        raise HttpError(409, "employee is not terminated")
    ctx.exec("UPDATE employees SET status='active' WHERE id=?", [e["id"]])
    return ctx.get("employees", e["id"])


@app.route("POST", "/api/pulse")
def pulse(ctx):
    """Submit this week's pulse score (1-5) as the signed-in employee."""
    score = ctx.need("score")[0]
    e = ctx.one("SELECT * FROM employees WHERE org_id=? AND email=?", (ctx.user["org_id"], ctx.user["email"]))
    if not e:
        raise HttpError(404, "no employee record")
    if not isinstance(score, int):
        raise HttpError(400, "score must be an integer")
    if ctx.one("SELECT 1 FROM pulses WHERE employee_id=? AND week=?", (e["id"], WEEK)):
        raise HttpError(409, "already submitted this week")
    pid = ctx.exec("INSERT INTO pulses VALUES(NULL,?,?,?,?)", (e["id"], WEEK, score, ctx.body.get("comment")))
    return created({"id": pid})


@app.route("GET", "/api/analytics/engagement", roles=["admin"])
def engagement(ctx):
    """Average pulse and response rate for the current week, optional ?team_id=."""
    where, args = "e.org_id=?", [ctx.user["org_id"]]
    if ctx.query.get("team_id"):
        where += " AND e.team_id=?"
        args.append(ctx.query["team_id"])
    n = ctx.one(f"SELECT COUNT(*) AS n FROM employees e WHERE {where}", args)["n"]
    rows = ctx.q(f"SELECT p.score FROM pulses p JOIN employees e ON e.id=p.employee_id WHERE {where} AND p.week=?", (*args, WEEK))
    return {"week": WEEK, "responses": len(rows), "average": round(sum(r["score"] for r in rows) / len(rows), 2) if rows else None,
            "response_rate": round(len(rows) / n, 2) if n else 0}


@app.route("GET", "/api/analytics/headcount", roles=["admin"])
def headcount(ctx):
    as_of = ctx.query.get("as_of", ctx.today.isoformat())
    n = ctx.one("SELECT COUNT(*) AS n FROM employees WHERE org_id=? AND hired_on<=? AND terminated_on IS NULL", (ctx.user["org_id"], as_of))["n"]
    return {"as_of": as_of, "headcount": n}
