from pathlib import Path

from common.framework import App, HttpError, created

SCHEMA = """
CREATE TABLE projects(id INTEGER PRIMARY KEY, org_id INT, name TEXT, archived INT DEFAULT 0);
CREATE TABLE members(project_id INT REFERENCES projects(id), user_id INT, role TEXT, PRIMARY KEY(project_id,user_id));
CREATE TABLE tasks(id INTEGER PRIMARY KEY, project_id INT REFERENCES projects(id), parent_id INT, title TEXT,
  status TEXT DEFAULT 'todo', assignee_id INT, priority TEXT DEFAULT 'normal', due_date TEXT, deleted_at TEXT);
CREATE TABLE comments(id INTEGER PRIMARY KEY, task_id INT REFERENCES tasks(id), user_id INT, body TEXT);
"""
STATUSES = ("todo", "doing", "done")


def seed(db):
    db.exec("INSERT INTO projects VALUES(1,1,'Website Relaunch',0)")
    db.exec("INSERT INTO projects VALUES(2,1,'Mobile App',0)")
    db.exec("INSERT INTO projects VALUES(3,2,'Globex Rollout',0)")
    for p, u, r in [(1, 1, "owner"), (1, 2, "member"), (1, 3, "member"), (2, 1, "owner"), (3, 4, "owner")]:
        db.exec("INSERT INTO members VALUES(?,?,?)", (p, u, r))
    titles = ["Fix Login bug", "Design hero banner", "Write launch copy", "Set up CI", "Audit accessibility", "Migrate DNS"]
    for i in range(12):
        due = f"2026-03-{10 + i:02d}"
        db.exec("INSERT INTO tasks VALUES(NULL,1,NULL,?,?,?,?,?,NULL)",
                (f"{titles[i % 6]} #{i}", STATUSES[i % 3], 2 if i % 2 else 1, "high" if i % 4 == 0 else "normal", due))
    db.exec("INSERT INTO tasks VALUES(NULL,3,NULL,'Globex private task','todo',4,'normal','2026-03-20',NULL)")


app = App("taskboard", "TaskBoard", 9102, SCHEMA, seed, static_dir=Path(__file__).parent / "static",
          description="Team project and task management with owners, members and subtasks.")


def is_owner(ctx, pid):
    return bool(ctx.one("SELECT 1 FROM members WHERE project_id=? AND user_id=? AND role='owner'", (pid, ctx.user["id"])))


@app.route("GET", "/api/projects")
def projects(ctx):
    return ctx.page("SELECT * FROM projects WHERE org_id=%d ORDER BY id" % ctx.user["org_id"])


@app.route("POST", "/api/projects", roles=["admin", "member"])
def add_project(ctx):
    name = ctx.need("name")[0]
    pid = ctx.exec("INSERT INTO projects VALUES(NULL,?,?,0)", (ctx.user["org_id"], name))
    ctx.exec("INSERT INTO members VALUES(?,?,'owner')", (pid, ctx.user["id"]))
    return created(ctx.get("projects", pid))


@app.route("POST", "/api/projects/<id>/members", roles=["admin", "member"])
def add_member(ctx):
    ctx.get("projects", ctx.params["id"])
    if not is_owner(ctx, ctx.params["id"]):
        raise HttpError(403, "only the project owner can add members")
    uid = ctx.need("user_id")[0]
    ctx.get("users", uid)
    ctx.exec("INSERT OR REPLACE INTO members VALUES(?,?,'member')", (ctx.params["id"], uid))
    return created({"project_id": ctx.params["id"], "user_id": uid, "role": "member"})


@app.route("POST", "/api/projects/<id>/transfer", roles=["admin", "member"])
def transfer(ctx):
    """Transfer project ownership to an existing member."""
    ctx.get("projects", ctx.params["id"])
    if not is_owner(ctx, ctx.params["id"]):
        raise HttpError(403, "only the owner can transfer ownership")
    uid = ctx.need("user_id")[0]
    if not ctx.one("SELECT 1 FROM members WHERE project_id=? AND user_id=?", (ctx.params["id"], uid)):
        raise HttpError(400, "target must be a project member")
    ctx.exec("UPDATE members SET role='owner' WHERE project_id=? AND user_id=?", (ctx.params["id"], uid))
    return {"ok": True, "owner_id": uid}


@app.route("POST", "/api/projects/<id>/archive", roles=["admin", "member"])
def archive(ctx):
    ctx.get("projects", ctx.params["id"])
    if not is_owner(ctx, ctx.params["id"]):
        raise HttpError(403, "only the owner can archive")
    ctx.exec("UPDATE projects SET archived=1 WHERE id=?", [ctx.params["id"]])
    return {"ok": True}


@app.route("GET", "/api/projects/<id>/tasks")
def tasks(ctx):
    ctx.get("projects", ctx.params["id"])
    sql, args = "SELECT * FROM tasks WHERE project_id=? AND deleted_at IS NULL", [ctx.params["id"]]
    for col in ("status", "assignee_id", "priority"):
        if ctx.query.get(col):
            sql += f" AND {col}=?"
            args.append(ctx.query[col])
    return ctx.page(sql + " ORDER BY id", args)


@app.route("POST", "/api/projects/<id>/tasks", roles=["admin", "member"])
def add_task(ctx):
    ctx.get("projects", ctx.params["id"])
    title = ctx.need("title")[0].strip()
    if not title:
        raise HttpError(400, "title required")
    tid = ctx.exec("INSERT INTO tasks VALUES(NULL,?,?,?,'todo',?,?,?,NULL)", (
        ctx.params["id"], ctx.body.get("parent_id"), title, ctx.body.get("assignee_id"), ctx.body.get("priority", "normal"), ctx.body.get("due_date")))
    return created(ctx.one("SELECT * FROM tasks WHERE id=?", [tid]))


def load_task(ctx, tid):
    t = ctx.one("SELECT t.* FROM tasks t JOIN projects p ON p.id=t.project_id WHERE t.id=? AND p.org_id=? AND t.deleted_at IS NULL", (tid, ctx.user["org_id"]))
    if not t:
        raise HttpError(404, "task not found")
    return t


@app.route("PATCH", "/api/tasks/<id>")
def update_task(ctx):
    t = load_task(ctx, ctx.params["id"])
    new_status = ctx.body.get("status", t["status"])
    if new_status == "done" and t["status"] != "done":
        first = ctx.one("SELECT status FROM tasks WHERE parent_id=? AND deleted_at IS NULL ORDER BY id LIMIT 1", [t["id"]])
        if first and first["status"] != "done":
            raise HttpError(409, "complete all subtasks first")
    for col in ("title", "assignee_id", "priority", "due_date"):
        if col in ctx.body:
            ctx.exec(f"UPDATE tasks SET {col}=? WHERE id=?", (ctx.body[col], t["id"]))
    ctx.exec("UPDATE tasks SET status=? WHERE id=?", (new_status, t["id"]))
    return ctx.one("SELECT * FROM tasks WHERE id=?", [t["id"]])


@app.route("DELETE", "/api/tasks/<id>", roles=["admin", "member"])
def delete_task(ctx):
    t = load_task(ctx, ctx.params["id"])
    ctx.exec("UPDATE tasks SET deleted_at=? WHERE id=?", (ctx.now, t["id"]))
    return {"ok": True}


@app.route("POST", "/api/tasks/<id>/comments", roles=["admin", "member"])
def comment(ctx):
    t = load_task(ctx, ctx.params["id"])
    cid = ctx.exec("INSERT INTO comments VALUES(NULL,?,?,?)", (t["id"], ctx.user["id"], ctx.need("body")[0]))
    return created({"id": cid})


@app.route("GET", "/api/projects/<id>/stats")
def stats(ctx):
    ctx.get("projects", ctx.params["id"])
    out = {s: ctx.one("SELECT COUNT(*) AS n FROM tasks WHERE project_id=? AND status=?", (ctx.params["id"], s))["n"] for s in STATUSES}
    out["overdue"] = ctx.one("SELECT COUNT(*) AS n FROM tasks WHERE project_id=? AND deleted_at IS NULL AND status!='done' AND due_date<?",
                             (ctx.params["id"], ctx.today.isoformat()))["n"]
    return out
