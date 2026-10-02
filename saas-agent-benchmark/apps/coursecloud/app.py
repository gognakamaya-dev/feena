from pathlib import Path

from common.framework import App, HttpError, created

SCHEMA = """
CREATE TABLE courses(id INTEGER PRIMARY KEY, org_id INT, title TEXT, status TEXT DEFAULT 'draft', price_cents INT DEFAULT 0);
CREATE TABLE lessons(id INTEGER PRIMARY KEY, course_id INT REFERENCES courses(id), title TEXT, position INT, required INT DEFAULT 1);
CREATE TABLE enrollments(id INTEGER PRIMARY KEY, course_id INT REFERENCES courses(id), user_id INT REFERENCES users(id), status TEXT DEFAULT 'active', certificate TEXT);
CREATE TABLE completions(id INTEGER PRIMARY KEY, enrollment_id INT REFERENCES enrollments(id), lesson_id INT REFERENCES lessons(id));
CREATE TABLE grades(id INTEGER PRIMARY KEY, course_id INT REFERENCES courses(id), user_id INT, score REAL, max_score REAL);
"""
PASS_PCT = 70


def seed(db):
    db.exec("INSERT INTO courses VALUES(1,1,'Intro to Python','published',4900)")
    db.exec("INSERT INTO courses VALUES(2,1,'Advanced SQL','published',9900)")
    db.exec("INSERT INTO courses VALUES(3,1,'Draft: Rust Basics','draft',0)")
    db.exec("INSERT INTO courses VALUES(4,2,'Globex Onboarding','published',0)")
    for cid, n in [(1, 4), (2, 3), (3, 2), (4, 2)]:
        for p in range(1, n + 1):
            db.exec("INSERT INTO lessons VALUES(NULL,?,?,?,?)", (cid, f"Lesson {p}", p, 0 if (cid == 1 and p == 4) else 1))
    db.exec("INSERT INTO enrollments VALUES(1,1,3,'active',NULL)")
    db.exec("INSERT INTO grades VALUES(NULL,1,3,80,100)")


app = App("coursecloud", "CourseCloud", 9112, SCHEMA, seed, static_dir=Path(__file__).parent / "static",
          description="Course management: lessons, enrollment, progress tracking, grades and certificates. Viewers are students.")


@app.route("GET", "/api/courses")
def courses(ctx):
    sql = "SELECT * FROM courses WHERE org_id=%d" % ctx.user["org_id"]
    if ctx.user["role"] == "viewer":
        sql += " AND status='published'"
    return ctx.page(sql + " ORDER BY id")


@app.route("POST", "/api/courses", roles=["admin", "member"])
def add_course(ctx):
    title = ctx.need("title")[0]
    return created(ctx.get("courses", ctx.exec("INSERT INTO courses VALUES(NULL,?,?,'draft',?)", (ctx.user["org_id"], title, ctx.body.get("price_cents", 0)))))


@app.route("POST", "/api/courses/<id>/lessons", roles=["admin", "member"])
def add_lesson(ctx):
    c = ctx.get("courses", ctx.params["id"])
    n = ctx.one("SELECT COUNT(*) AS n FROM lessons WHERE course_id=?", [c["id"]])["n"]
    lid = ctx.exec("INSERT INTO lessons VALUES(NULL,?,?,?,?)", (c["id"], ctx.need("title")[0], n + 1, int(ctx.body.get("required", True))))
    return created(ctx.one("SELECT * FROM lessons WHERE id=?", [lid]))


@app.route("POST", "/api/courses/<id>/publish", roles=["admin", "member"])
def publish(ctx):
    c = ctx.get("courses", ctx.params["id"])
    if not ctx.one("SELECT 1 FROM lessons WHERE course_id=?", [c["id"]]):
        raise HttpError(409, "course needs at least one lesson")
    ctx.exec("UPDATE courses SET status='published' WHERE id=?", [c["id"]])
    return ctx.get("courses", c["id"])


@app.route("POST", "/api/courses/<id>/enroll")
def enroll(ctx):
    c = ctx.get("courses", ctx.params["id"])
    if ctx.one("SELECT 1 FROM enrollments WHERE course_id=? AND user_id=? AND status!='dropped'", (c["id"], ctx.user["id"])):
        raise HttpError(409, "already enrolled")
    eid = ctx.exec("INSERT INTO enrollments VALUES(NULL,?,?,'active',NULL)", (c["id"], ctx.user["id"]))
    return created(ctx.one("SELECT * FROM enrollments WHERE id=?", [eid]))


def own_enrollment(ctx, eid):
    e = ctx.one("SELECT * FROM enrollments WHERE id=? AND user_id=?", (eid, ctx.user["id"]))
    if not e:
        raise HttpError(404, "enrollment not found")
    return e


def progress(ctx, e):
    required = ctx.one("SELECT COUNT(*) AS n FROM lessons WHERE course_id=? AND required=1", [e["course_id"]])["n"]
    done = ctx.one("SELECT COUNT(*) AS n FROM completions WHERE enrollment_id=?", [e["id"]])["n"]
    return {"completed": done, "required": required, "percent": round(100 * done / required) if required else 0}


@app.route("POST", "/api/lessons/<id>/complete")
def complete(ctx):
    lesson = ctx.one("SELECT l.* FROM lessons l JOIN courses c ON c.id=l.course_id WHERE l.id=? AND c.org_id=?", (ctx.params["id"], ctx.user["org_id"]))
    e = lesson and ctx.one("SELECT * FROM enrollments WHERE course_id=? AND user_id=? AND status='active'", (lesson["course_id"], ctx.user["id"]))
    if not e:
        raise HttpError(404, "not enrolled in this lesson's course")
    ctx.exec("INSERT INTO completions VALUES(NULL,?,?)", (e["id"], lesson["id"]))
    return {"enrollment_id": e["id"], **progress(ctx, e)}


@app.route("GET", "/api/enrollments/<id>/progress")
def get_progress(ctx):
    return progress(ctx, own_enrollment(ctx, ctx.params["id"]))


@app.route("POST", "/api/courses/<id>/grades", roles=["admin", "member"])
def add_grade(ctx):
    c = ctx.get("courses", ctx.params["id"])
    uid, score, mx = ctx.need("user_id", "score", "max_score")
    ctx.exec("INSERT INTO grades VALUES(NULL,?,?,?,?)", (c["id"], uid, score, mx))
    return created({"ok": True})


@app.route("GET", "/api/courses/<id>/gradebook")
def gradebook(ctx):
    c = ctx.get("courses", ctx.params["id"])
    return {"items": ctx.q("SELECT user_id, SUM(score) AS score, SUM(max_score) AS max_score FROM grades WHERE course_id=? GROUP BY user_id", [c["id"]])}


@app.route("POST", "/api/enrollments/<id>/certificate")
def certificate(ctx):
    e = own_enrollment(ctx, ctx.params["id"])
    p = progress(ctx, e)
    if p["completed"] < p["required"]:
        raise HttpError(409, "complete all required lessons first")
    g = ctx.one("SELECT SUM(score) AS s, SUM(max_score) AS m FROM grades WHERE course_id=? AND user_id=?", (e["course_id"], ctx.user["id"]))
    if not g["m"] or round(100 * g["s"] / g["m"]) < PASS_PCT:
        raise HttpError(409, f"final grade below {PASS_PCT}%")
    ctx.exec("UPDATE enrollments SET status='completed', certificate=? WHERE id=?", (f"CERT-{e['id']:05d}", e["id"]))
    return ctx.one("SELECT * FROM enrollments WHERE id=?", [e["id"]])
