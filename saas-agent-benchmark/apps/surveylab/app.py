import json
from pathlib import Path

from common.framework import App, HttpError, created

SCHEMA = """
CREATE TABLE surveys(id INTEGER PRIMARY KEY, org_id INT, title TEXT, status TEXT DEFAULT 'draft');
CREATE TABLE questions(id INTEGER PRIMARY KEY, survey_id INT REFERENCES surveys(id), text TEXT, type TEXT, options TEXT, required INT DEFAULT 0, position INT);
CREATE TABLE responses(id INTEGER PRIMARY KEY, survey_id INT REFERENCES surveys(id), token TEXT, submitted_at TEXT, UNIQUE(survey_id, token));
CREATE TABLE answers(response_id INT REFERENCES responses(id), question_id INT REFERENCES questions(id), value TEXT);
"""
TYPES = ("rating", "choice", "text")


def seed(db):
    for sid, org, t, st in [(1, 1, "Customer Satisfaction Q1", "live"), (2, 1, "Draft: Onboarding Pulse", "draft"), (3, 1, "Product Feedback 2025", "closed"), (4, 2, "Globex Employee Survey", "live")]:
        db.exec("INSERT INTO surveys VALUES(?,?,?,?)", (sid, org, t, st))
    db.exec("INSERT INTO questions VALUES(1,1,'How satisfied are you? (1-5)','rating',NULL,1,1)")
    db.exec("INSERT INTO questions VALUES(2,1,'Preferred contact channel','choice',?,0,2)", (json.dumps(["Email", "Phone", "Chat"]),))
    db.exec("INSERT INTO questions VALUES(3,1,'Anything else?','text',NULL,0,3)")
    db.exec("INSERT INTO questions VALUES(4,3,'Rate the product','rating',NULL,1,1)")
    db.exec("INSERT INTO questions VALUES(5,4,'Rate your manager','rating',NULL,1,1)")
    for i in range(1, 7):
        rid = db.exec("INSERT INTO responses VALUES(NULL,1,?,'2026-03-01')", (f"t{i}",))
        db.exec("INSERT INTO answers VALUES(?,1,?)", (rid, str(3 + i % 3)))
        if i <= 4:
            db.exec("INSERT INTO answers VALUES(?,2,?)", (rid, ["Email", "Email", "Phone", "Chat"][i - 1]))
    rid = db.exec("INSERT INTO responses VALUES(NULL,4,'g1','2026-03-02')")
    db.exec("INSERT INTO answers VALUES(?,5,'2')", (rid,))


app = App("surveylab", "SurveyLab", 9114, SCHEMA, seed, static_dir=Path(__file__).parent / "static",
          description="Survey builder with public response collection and analytics.")


@app.route("GET", "/api/surveys")
def surveys(ctx):
    return ctx.page("SELECT s.*, (SELECT COUNT(*) FROM responses r WHERE r.survey_id=s.id) AS responses FROM surveys s WHERE org_id=%d ORDER BY id" % ctx.user["org_id"])


@app.route("POST", "/api/surveys", roles=["admin", "member"])
def add_survey(ctx):
    return created(ctx.get("surveys", ctx.exec("INSERT INTO surveys VALUES(NULL,?,?,'draft')", (ctx.user["org_id"], ctx.need("title")[0]))))


@app.route("POST", "/api/surveys/<id>/questions", roles=["admin", "member"])
def add_question(ctx):
    s = ctx.get("surveys", ctx.params["id"])
    text, typ = ctx.need("text", "type")
    if typ not in TYPES:
        raise HttpError(400, "unknown question type")
    if typ == "choice" and not ctx.body.get("options"):
        raise HttpError(400, "choice questions need options")
    pos = ctx.one("SELECT COUNT(*) AS n FROM questions WHERE survey_id=?", [s["id"]])["n"] + 1
    qid = ctx.exec("INSERT INTO questions VALUES(NULL,?,?,?,?,?,?)", (s["id"], text, typ, json.dumps(ctx.body["options"]) if ctx.body.get("options") else None, int(bool(ctx.body.get("required"))), pos))
    return created(ctx.one("SELECT * FROM questions WHERE id=?", [qid]))


@app.route("POST", "/api/surveys/<id>/launch", roles=["admin", "member"])
def launch(ctx):
    s = ctx.get("surveys", ctx.params["id"])
    if s["status"] != "draft" or not ctx.one("SELECT 1 FROM questions WHERE survey_id=?", [s["id"]]):
        raise HttpError(409, "only drafts with questions can be launched")
    ctx.exec("UPDATE surveys SET status='live' WHERE id=?", [s["id"]])
    return ctx.get("surveys", s["id"])


@app.route("POST", "/api/surveys/<id>/close", roles=["admin", "member"])
def close(ctx):
    s = ctx.get("surveys", ctx.params["id"])
    ctx.exec("UPDATE surveys SET status='closed' WHERE id=?", [s["id"]])
    return ctx.get("surveys", s["id"])


@app.route("POST", "/api/public/surveys/<id>/responses", auth=False)
def respond(ctx):
    """Public submission: {token, answers: {question_id: value}}."""
    s = ctx.one("SELECT * FROM surveys WHERE id=?", [ctx.params["id"]])
    if not s or s["status"] == "draft":
        raise HttpError(404, "survey not found")
    token = ctx.need("token")[0]
    answers = ctx.body.get("answers", {})
    for q in ctx.q("SELECT * FROM questions WHERE survey_id=?", [s["id"]]):
        v = answers.get(str(q["id"]))
        if q["required"] and v in (None, ""):
            raise HttpError(400, f"question {q['id']} is required")
        if v is None:
            continue
        if q["type"] == "choice" and v not in json.loads(q["options"]):
            raise HttpError(400, f"invalid option for question {q['id']}")
    if ctx.one("SELECT 1 FROM responses WHERE survey_id=? AND token=?", (s["id"], token)):
        raise HttpError(409, "response already recorded")
    rid = ctx.exec("INSERT INTO responses VALUES(NULL,?,?,?)", (s["id"], token, ctx.now))
    for k, v in answers.items():
        ctx.exec("INSERT INTO answers VALUES(?,?,?)", (rid, int(k), str(v)))
    return created({"id": rid})


@app.route("GET", "/api/surveys/<id>/analytics")
def analytics(ctx):
    s = ctx.get("surveys", ctx.params["id"], org=False)
    total = ctx.one("SELECT COUNT(*) AS n FROM responses WHERE survey_id=?", [s["id"]])["n"]
    out = {"survey_id": s["id"], "responses": total, "questions": {}}
    for q in ctx.q("SELECT * FROM questions WHERE survey_id=? ORDER BY position", [s["id"]]):
        vals = [a["value"] for a in ctx.q("SELECT value FROM answers WHERE question_id=?", [q["id"]])]
        entry = {"answered": len(vals)}
        if q["type"] == "rating" and vals:
            entry["average"] = round(sum(float(v) for v in vals) / len(vals), 2)
        if q["type"] == "choice":
            counts = {o: vals.count(o) for o in json.loads(q["options"])}
            entry["percentages"] = {o: round(100 * n / total) if total else 0 for o, n in counts.items()}
        out["questions"][str(q["id"])] = entry
    return out


@app.route("GET", "/api/surveys/<id>/ratings")
def ratings(ctx):
    """Raw rating answers for the survey's rating questions."""
    s = ctx.get("surveys", ctx.params["id"])
    return ctx.page("SELECT a.response_id AS id, CAST(a.value AS REAL) AS value FROM answers a JOIN questions q ON q.id=a.question_id WHERE q.survey_id=? AND q.type='rating' ORDER BY a.response_id", [s["id"]])
