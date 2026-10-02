from pathlib import Path

from common.framework import App, HttpError, created

SCHEMA = """
CREATE TABLE jobs(id INTEGER PRIMARY KEY, org_id INT, title TEXT, department TEXT, status TEXT DEFAULT 'open');
CREATE TABLE candidates(id INTEGER PRIMARY KEY, org_id INT, name TEXT, email TEXT, UNIQUE(org_id,email));
CREATE TABLE applications(id INTEGER PRIMARY KEY, org_id INT, job_id INT REFERENCES jobs(id), candidate_id INT REFERENCES candidates(id), stage TEXT DEFAULT 'applied', UNIQUE(job_id,candidate_id));
CREATE TABLE interviews(id INTEGER PRIMARY KEY, application_id INT REFERENCES applications(id), scheduled_at TEXT, score INT);
"""
STAGES = ["applied", "screen", "interview", "offer", "hired"]


def seed(db):
    for jid, org, t, dep, st in [(1, 1, "Senior Engineer", "Engineering", "open"), (2, 1, "Product Designer", "Design", "open"), (3, 1, "Office Manager", "Ops", "closed"), (4, 2, "Globex Analyst", "Finance", "open")]:
        db.exec("INSERT INTO jobs VALUES(?,?,?,?,?)", (jid, org, t, dep, st))
    for i in range(1, 7):
        db.exec("INSERT INTO candidates VALUES(?,?,?,?)", (i, 1, f"Candidate {i}", f"cand{i}@example.test"))
    db.exec("INSERT INTO candidates VALUES(7,2,'Globex Candidate','gcand@example.test')")
    for i, (j, st) in enumerate([(1, "applied"), (1, "screen"), (1, "interview"), (2, "applied"), (2, "rejected"), (2, "offer")], 1):
        db.exec("INSERT INTO applications VALUES(?,1,?,?,?)", (i, j, i, st))
    db.exec("INSERT INTO applications VALUES(7,2,4,7,'applied')")


app = App("recruitflow", "RecruitFlow", 9115, SCHEMA, seed, static_dir=Path(__file__).parent / "static",
          description="Applicant tracking: jobs, public applications, staged pipelines and interview feedback.")


@app.route("GET", "/api/jobs")
def jobs(ctx):
    return ctx.page("SELECT * FROM jobs WHERE org_id=%d ORDER BY id" % ctx.user["org_id"])


@app.route("POST", "/api/jobs", roles=["admin", "member"])
def add_job(ctx):
    title, dep = ctx.need("title", "department")
    return created(ctx.get("jobs", ctx.exec("INSERT INTO jobs VALUES(NULL,?,?,?,'open')", (ctx.user["org_id"], title, dep))))


@app.route("POST", "/api/jobs/<id>/close", roles=["admin", "member"])
def close_job(ctx):
    j = ctx.get("jobs", ctx.params["id"])
    ctx.exec("UPDATE jobs SET status='closed' WHERE id=?", [j["id"]])
    return ctx.get("jobs", j["id"])


@app.route("POST", "/api/public/jobs/<id>/apply", auth=False)
def apply(ctx):
    j = ctx.one("SELECT * FROM jobs WHERE id=?", [ctx.params["id"]])
    if not j:
        raise HttpError(404, "job not found")
    name, email = ctx.need("name", "email")
    c = ctx.one("SELECT * FROM candidates WHERE org_id=? AND email=?", (j["org_id"], email))
    cid = c["id"] if c else ctx.exec("INSERT INTO candidates VALUES(NULL,?,?,?)", (j["org_id"], name, email))
    if ctx.one("SELECT 1 FROM applications WHERE job_id=? AND candidate_id=?", (j["id"], cid)):
        raise HttpError(409, "already applied")
    aid = ctx.exec("INSERT INTO applications VALUES(NULL,?,?,?,'applied')", (j["org_id"], j["id"], cid))
    return created({"id": aid, "stage": "applied"})


@app.route("GET", "/api/jobs/<id>/applications", roles=["admin", "member"])
def applications(ctx):
    j = ctx.get("jobs", ctx.params["id"])
    sql, args = "SELECT a.*, c.name, c.email FROM applications a JOIN candidates c ON c.id=a.candidate_id WHERE a.job_id=?", [j["id"]]
    if ctx.query.get("stage"):
        sql += " AND a.stage=?"
        args.append(ctx.query["stage"])
    return ctx.page(sql + " ORDER BY a.id", args)


@app.route("GET", "/api/applications/<id>", roles=["admin", "member"])
def get_application(ctx):
    a = ctx.get("applications", ctx.params["id"], org=False)
    a["interviews"] = ctx.q("SELECT * FROM interviews WHERE application_id=?", [a["id"]])
    scores = [i["score"] for i in a["interviews"]]
    a["average_score"] = round(sum(s or 0 for s in scores) / len(scores), 2) if scores else None
    return a


@app.route("POST", "/api/applications/<id>/stage", roles=["admin", "member"])
def set_stage(ctx):
    a = ctx.get("applications", ctx.params["id"])
    st = ctx.need("stage")[0]
    if st not in STAGES + ["rejected"]:
        raise HttpError(400, "unknown stage")
    if a["stage"] in ("hired", "rejected"):
        raise HttpError(409, f"application already {a['stage']}")
    ctx.exec("UPDATE applications SET stage=? WHERE id=?", (st, a["id"]))
    return ctx.get("applications", a["id"])


@app.route("POST", "/api/applications/<id>/interviews", roles=["admin", "member"])
def schedule(ctx):
    a = ctx.get("applications", ctx.params["id"])
    iid = ctx.exec("INSERT INTO interviews VALUES(NULL,?,?,NULL)", (a["id"], ctx.need("scheduled_at")[0]))
    return created(ctx.one("SELECT * FROM interviews WHERE id=?", [iid]))


@app.route("POST", "/api/interviews/<id>/feedback", roles=["admin", "member"])
def feedback(ctx):
    i = ctx.one("SELECT i.* FROM interviews i JOIN applications a ON a.id=i.application_id WHERE i.id=? AND a.org_id=?", (ctx.params["id"], ctx.user["org_id"]))
    if not i:
        raise HttpError(404, "interview not found")
    score = ctx.need("score")[0]
    if not isinstance(score, int) or not 1 <= score <= 5:
        raise HttpError(400, "score must be 1-5")
    ctx.exec("UPDATE interviews SET score=? WHERE id=?", (score, i["id"]))
    return ctx.one("SELECT * FROM interviews WHERE id=?", [i["id"]])


@app.route("GET", "/api/jobs/<id>/pipeline", roles=["admin", "member"])
def pipeline(ctx):
    j = ctx.get("jobs", ctx.params["id"])
    rows = ctx.q("SELECT stage, COUNT(*) AS n FROM applications WHERE job_id=? GROUP BY stage", [j["id"]])
    return {"job": j, "stages": {r["stage"]: r["n"] for r in rows}}
