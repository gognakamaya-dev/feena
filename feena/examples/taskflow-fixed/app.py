"""TaskFlow (FIXED) — the same app as examples/taskflow with the security bugs actually fixed.

Used to prove Feena's generated regression tests go red on the vulnerable app and green here.
Original description follows.

TaskFlow — a small team task manager, written the way an AI coding tool tends to ship it.

This is NOT hardened. It is a realistic "vibe-coded" SaaS: it works for the happy path, looks
fine in a demo, and carries the security and correctness bugs these apps usually carry. It
exists so we can test Feena against ground truth we wrote down in advance (see GROUND_TRUTH.md),
not against bugs planted to be easy. Some bugs are inside Feena's current reach and some are
deliberately outside it, so the run produces an honest precision/recall scorecard.

Single-file Flask + SQLite so it boots with no build step.
"""
import sqlite3
import os
from flask import Flask, request, session, redirect, g, render_template_string
from markupsafe import escape

app = Flask(__name__)
app.secret_key = "dev-secret-change-me"  # BUG(9): hardcoded, weak secret key
DB = os.environ.get("TASKFLOW_DB", "/tmp/taskflow.db")


def db():
    if "db" not in g:
        g.db = sqlite3.connect(DB)
        g.db.row_factory = sqlite3.Row
    return g.db


@app.after_request
def security_headers(resp):
    # FIX(3): baseline security headers on every response
    resp.headers["Content-Security-Policy"] = "default-src 'self'"
    resp.headers["X-Content-Type-Options"] = "nosniff"
    resp.headers["X-Frame-Options"] = "DENY"
    resp.headers["Strict-Transport-Security"] = "max-age=63072000; includeSubDomains"
    return resp


@app.teardown_appcontext
def close_db(exc):
    d = g.pop("db", None)
    if d:
        d.close()


def init_db():
    con = sqlite3.connect(DB)
    con.executescript(
        """
        CREATE TABLE IF NOT EXISTS users(
            id INTEGER PRIMARY KEY, email TEXT UNIQUE, password TEXT, name TEXT);
        CREATE TABLE IF NOT EXISTS projects(
            id INTEGER PRIMARY KEY, owner_id INTEGER, name TEXT);
        CREATE TABLE IF NOT EXISTS tasks(
            id INTEGER PRIMARY KEY, project_id INTEGER, owner_id INTEGER,
            title TEXT, done INTEGER DEFAULT 0);
        """
    )
    # seed two accounts so IDOR-style checks have an attacker and a victim
    cur = con.execute("SELECT COUNT(*) FROM users")
    if cur.fetchone()[0] == 0:
        con.execute("INSERT INTO users(email,password,name) VALUES(?,?,?)",
                    ("alice@example.com", "password123", "Alice"))  # BUG(7): plaintext password
        con.execute("INSERT INTO users(email,password,name) VALUES(?,?,?)",
                    ("bob@example.com", "password123", "Bob"))
        con.execute("INSERT INTO projects(owner_id,name) VALUES(1,'Alice Secret Project')")
        con.execute("INSERT INTO projects(owner_id,name) VALUES(2,'Bob Secret Project')")
        con.execute("INSERT INTO tasks(project_id,owner_id,title) VALUES(1,1,'Alice private task')")
        con.execute("INSERT INTO tasks(project_id,owner_id,title) VALUES(2,2,'Bob private task')")
    con.commit()
    con.close()


def current_user():
    uid = session.get("uid")
    if not uid:
        return None
    return db().execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone()


PAGE = """
<!doctype html><title>TaskFlow</title>
<h1>TaskFlow</h1>
{% if user %}<p>Hello {{ user['name'] }} · <a href="/logout">logout</a></p>{% endif %}
{{ body|safe }}
"""


@app.get("/api/health")
def health():
    return {"ok": True}


@app.get("/")
def home():
    u = current_user()
    if not u:
        body = '<a href="/login">login</a> · <a href="/signup">signup</a>'
    else:
        body = '<a href="/tasks">my tasks</a> · <a href="/search?q=">search</a>'
    return render_template_string(PAGE, user=u, body=body)


@app.route("/signup", methods=["GET", "POST"])
def signup():
    if request.method == "POST":
        email = request.form.get("email", "")
        pw = request.form.get("password", "")
        # BUG(8): no validation — empty email/password accepted, no dup handling beyond DB error
        db().execute("INSERT INTO users(email,password,name) VALUES(?,?,?)",
                     (email, pw, email.split("@")[0]))
        db().commit()
        return redirect("/login")
    form = ('<form method=post><input name=email placeholder=email>'
            '<input name=password type=password placeholder=password>'
            '<button>sign up</button></form>')
    return render_template_string(PAGE, user=None, body=form)


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email", "")
        pw = request.form.get("password", "")
        # BUG(6): SQL injection — user input formatted straight into the query
        # FIX(6): parameterised query
        row = db().execute("SELECT * FROM users WHERE email=? AND password=?", (email, pw)).fetchone()
        if row:
            session["uid"] = row["id"]
            return redirect("/tasks")
        return render_template_string(PAGE, user=None, body="bad login")
    form = ('<form method=post><input name=email placeholder=email>'
            '<input name=password type=password placeholder=password>'
            '<button>log in</button></form>')
    return render_template_string(PAGE, user=None, body=form)


@app.post("/api/login")
def api_login():
    """JSON login that sets the session cookie (used by API clients and by test agents)."""
    data = request.get_json(silent=True) or {}
    email, pw = data.get("email", ""), data.get("password", "")
    row = db().execute("SELECT * FROM users WHERE email=? AND password=?", (email, pw)).fetchone()
    if row:
        session["uid"] = row["id"]
        return {"ok": True, "id": row["id"]}
    return {"ok": False}, 401


@app.get("/logout")
def logout():
    session.clear()
    return redirect("/")


@app.get("/tasks")
def tasks():
    u = current_user()
    if not u:
        return redirect("/login")
    rows = db().execute("SELECT * FROM tasks WHERE owner_id=?", (u["id"],)).fetchall()
    # BUG(5): stored XSS — task title rendered without escaping
    items = "".join(f"<li>{escape(r['title'])}</li>" for r in rows)  # FIX(5): escape
    form = ('<form method=post action=/tasks/new><input name=title placeholder="new task">'
            '<button>add</button></form>')
    return render_template_string(PAGE, user=u, body=f"<ul>{items}</ul>{form}")


@app.post("/tasks/new")
def new_task():
    u = current_user()
    if not u:
        return redirect("/login")
    title = request.form.get("title", "")
    # BUG(10): no idempotency — a double-submit inserts the task twice
    db().execute("INSERT INTO tasks(project_id,owner_id,title) VALUES(?,?,?)", (1, u["id"], title))
    db().commit()
    return redirect("/tasks")


@app.get("/api/tasks/<int:task_id>")
def get_task(task_id):
    u = current_user()
    if not u:
        return {"error": "auth required"}, 401
    # BUG(1): IDOR — returns the task by id with NO ownership check
    # FIX(1): scope to the caller
    row = db().execute("SELECT * FROM tasks WHERE id=? AND owner_id=?", (task_id, u["id"])).fetchone()
    if not row:
        return {"error": "not found"}, 404
    return {"id": row["id"], "title": row["title"], "owner_id": row["owner_id"]}


@app.get("/api/projects")
def api_projects():
    # BUG(2): missing auth — returns EVERY project to anyone, no session required
    # FIX(2): require a session and scope to the caller
    u = current_user()
    if not u:
        return {"error": "auth required"}, 401
    rows = db().execute("SELECT * FROM projects WHERE owner_id=?", (u["id"],)).fetchall()
    return {"projects": [{"id": r["id"], "name": r["name"], "owner_id": r["owner_id"]} for r in rows]}


@app.get("/api/me")
def api_me():
    # CORRECT: properly scoped to the caller. Feena should NOT flag this.
    u = current_user()
    if not u:
        return {"error": "auth required"}, 401
    return {"id": u["id"], "email": u["email"], "name": u["name"]}


@app.get("/search")
def search():
    q = request.args.get("q", "")
    # BUG(4): reflected XSS — query echoed into HTML unescaped
    return render_template_string(PAGE, user=current_user(),
                                  body=f"<p>Results for: {escape(q)}</p>")  # FIX(4)


if __name__ == "__main__":
    init_db()
    # BUG(11): debug server exposes the interactive debugger on errors
    app.run(host="0.0.0.0", port=5000, debug=True)
