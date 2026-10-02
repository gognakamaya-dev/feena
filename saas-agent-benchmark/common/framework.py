"""Tiny dependency-free SaaS framework shared by every benchmark application."""
import datetime
import hashlib
import json
import mimetypes
import os
import re
import secrets
import sqlite3
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

ROOT = Path(__file__).resolve().parent.parent
FIXED_NOW = datetime.datetime(2026, 3, 15, 10, 0, 0)
BENCH_KEY = os.environ.get("BENCH_KEY", "benchmark-local")
DEMO_PASSWORD = "demo123"

BASE_SCHEMA = """
CREATE TABLE orgs(id INTEGER PRIMARY KEY, name TEXT NOT NULL);
CREATE TABLE users(id INTEGER PRIMARY KEY, org_id INTEGER NOT NULL REFERENCES orgs(id),
  email TEXT NOT NULL UNIQUE, name TEXT NOT NULL, role TEXT NOT NULL,
  password_hash TEXT NOT NULL, active INTEGER NOT NULL DEFAULT 1);
CREATE TABLE sessions(token TEXT PRIMARY KEY, user_id INTEGER NOT NULL, created_at TEXT NOT NULL);
"""

BASE_USERS = [
    (1, 1, "admin@acme.test", "Ada Admin", "admin"),
    (2, 1, "member@acme.test", "Max Member", "member"),
    (3, 1, "viewer@acme.test", "Vera Viewer", "viewer"),
    (4, 2, "admin@globex.test", "Gus Globex", "admin"),
    (5, 2, "member@globex.test", "Gina Globex", "member"),
]


def hash_pw(pw):
    return hashlib.sha256(pw.encode()).hexdigest()


class HttpError(Exception):
    def __init__(self, status, message, **extra):
        super().__init__(message)
        self.status, self.message, self.extra = status, message, extra


class DB:
    def __init__(self, path):
        self.conn = sqlite3.connect(path, check_same_thread=False, isolation_level=None)
        self.conn.row_factory = lambda cur, row: {d[0]: v for d, v in zip(cur.description, row)}
        self.conn.execute("PRAGMA foreign_keys=ON")

    def q(self, sql, args=()):
        return self.conn.execute(sql, tuple(args)).fetchall()

    def one(self, sql, args=()):
        return self.conn.execute(sql, tuple(args)).fetchone()

    def exec(self, sql, args=()):
        return self.conn.execute(sql, tuple(args)).lastrowid

    def script(self, sql):
        self.conn.executescript(sql)


class Ctx:
    def __init__(self, app, user, params, query, body, headers):
        self.app, self.db, self.user = app, app.db, user
        self.params, self.query, self.body, self.headers = params, query, body, headers
        self.today = app.today
        self.now = app.now

    q = property(lambda s: s.db.q)
    one = property(lambda s: s.db.one)
    exec = property(lambda s: s.db.exec)

    def need(self, *fields):
        missing = [f for f in fields if self.body.get(f) in (None, "")]
        if missing:
            raise HttpError(400, "missing fields: " + ", ".join(missing))
        return [self.body[f] for f in fields]

    def int_arg(self, name, default, lo=1, hi=None):
        try:
            v = int(self.query.get(name, default))
        except ValueError:
            raise HttpError(400, f"{name} must be an integer")
        v = max(lo, v)
        return min(hi, v) if hi else v

    def get(self, table, id_, org=True, msg=None):
        sql, args = f"SELECT * FROM {table} WHERE id=?", [id_]
        if org:
            sql += " AND org_id=?"
            args.append(self.user["org_id"])
        row = self.one(sql, args)
        if not row:
            raise HttpError(404, msg or f"{table} not found")
        return row

    def require_role(self, *roles):
        if self.user["role"] not in roles:
            raise HttpError(403, "insufficient role")

    def page(self, sql, args=()):
        page, size = self.int_arg("page", 1), self.int_arg("page_size", 20, hi=100)
        total = self.one(f"SELECT COUNT(*) AS n FROM ({sql})", args)["n"]
        items = self.q(f"{sql} LIMIT ? OFFSET ?", (*args, size, (page - 1) * size))
        return {"items": items, "total": total, "page": page, "page_size": size}


class App:
    def __init__(self, id_, name, port, schema, seed, description="", static_dir=None):
        self.id, self.name, self.port, self.schema, self.seed = id_, name, port, schema, seed
        self.description = description
        self.static_dir = static_dir
        self.routes, self.lock, self.db = [], threading.RLock(), None
        self.today = FIXED_NOW.date()
        self.now = FIXED_NOW.isoformat(timespec="seconds")
        self._defaults_added = False

    def route(self, method, pattern, auth=True, roles=None):
        regex = re.compile("^" + re.sub(r"<(\w+)>", r"(?P<\1>[^/]+)", pattern) + "$")

        def deco(fn):
            self.routes.append((method, regex, pattern, auth, roles, fn))
            return fn
        return deco

    def data_path(self):
        d = Path(os.environ.get("BENCH_DATA_DIR", ROOT / ".data"))
        d.mkdir(parents=True, exist_ok=True)
        return d / f"{self.id}.sqlite"

    def reset(self):
        with self.lock:
            if self.db:
                self.db.conn.close()
            p = self.data_path()
            for suffix in ("", "-wal", "-shm"):
                Path(str(p) + suffix).unlink(missing_ok=True)
            self.db = DB(str(p))
            self.db.script(BASE_SCHEMA + self.schema)
            self.db.exec("INSERT INTO orgs VALUES(1,'Acme Corp')")
            self.db.exec("INSERT INTO orgs VALUES(2,'Globex Inc')")
            for uid, org, email, name, role in BASE_USERS:
                self.db.exec("INSERT INTO users VALUES(?,?,?,?,?,?,1)",
                             (uid, org, email, name, role, hash_pw(DEMO_PASSWORD)))
            self.seed(self.db)

    # ---- request handling -------------------------------------------------
    def _add_defaults(self):
        if self._defaults_added:
            return
        self._defaults_added = True

        @self.route("GET", "/health", auth=False)
        def health(ctx):
            return {"status": "ok", "application": self.id}

        @self.route("POST", "/api/auth/login", auth=False)
        def login(ctx):
            email, pw = ctx.need("email", "password")
            u = ctx.one("SELECT * FROM users WHERE email=?", [email])
            if not u or u["password_hash"] != hash_pw(pw):
                raise HttpError(401, "invalid credentials")
            if not u["active"]:
                raise HttpError(403, "account disabled")
            tok = secrets.token_hex(16)
            ctx.exec("INSERT INTO sessions VALUES(?,?,?)", (tok, u["id"], ctx.now))
            return {"token": tok, "user": {k: u[k] for k in ("id", "org_id", "email", "name", "role")}}

        @self.route("POST", "/api/auth/logout")
        def logout(ctx):
            ctx.exec("DELETE FROM sessions WHERE token=?", [ctx.headers.get("Authorization", "")[7:]])
            return {"ok": True}

        @self.route("GET", "/api/auth/me")
        def me(ctx):
            return ctx.user

        @self.route("GET", "/api/docs", auth=False)
        def docs(ctx):
            return {"application": self.name, "description": self.description, "endpoints": [
                {"method": m, "path": p, "auth": a, "roles": r, "summary": (f.__doc__ or "").strip()}
                for m, _, p, a, r, f in self.routes]}

        @self.route("POST", "/__benchmark/reset", auth=False)
        def reset(ctx):
            if ctx.headers.get("X-Benchmark-Key") != BENCH_KEY:
                raise HttpError(403, "bad benchmark key")
            self.reset()
            return {"ok": True, "application": self.id}

    def dispatch(self, method, path, query, body, headers):
        self._add_defaults()
        path_matched = False
        for m, regex, pattern, auth, roles, fn in self.routes:
            mt = regex.match(path)
            if not mt:
                continue
            path_matched = True
            if m != method:
                continue
            params = {k: int(v) if v.isdigit() else v for k, v in mt.groupdict().items()}
            user = None
            if auth:
                tok = headers.get("Authorization", "")[7:]
                user = self.db.one("SELECT u.* FROM sessions s JOIN users u ON u.id=s.user_id "
                                   "WHERE s.token=? AND u.active=1", [tok]) if tok else None
                if not user:
                    raise HttpError(401, "authentication required")
                if roles and user["role"] not in roles:
                    raise HttpError(403, "insufficient role")
            return fn(Ctx(self, user, params, query, body, headers))
        raise HttpError(405 if path_matched else 404, "method not allowed" if path_matched else "not found")

    def static_file(self, rel):
        for base in filter(None, [self.static_dir, ROOT / "common" / "static"]):
            f = (Path(base) / rel).resolve()
            if Path(base).resolve() in f.parents and f.is_file():
                return f
        return None

    def make_handler(self):
        app = self

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def _send(self, status, payload, ctype="application/json"):
                data = payload if isinstance(payload, bytes) else json.dumps(payload).encode()
                self.send_response(status)
                self.send_header("Content-Type", ctype)
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def _handle(self, method):
                u = urlparse(self.path)
                if method == "GET" and not u.path.startswith(("/api", "/health", "/__")):
                    rel = "index.html" if u.path == "/" else u.path.lstrip("/").removeprefix("static/")
                    f = app.static_file(rel)
                    if not f:
                        return self._send(404, {"error": "not found"})
                    data = f.read_bytes()
                    if rel == "index.html":
                        data = data.replace(b"{{NAME}}", app.name.encode())
                    return self._send(200, data, mimetypes.guess_type(f.name)[0] or "text/plain")
                body = {}
                n = int(self.headers.get("Content-Length") or 0)
                if n:
                    try:
                        body = json.loads(self.rfile.read(n))
                    except ValueError:
                        return self._send(400, {"error": "invalid JSON"})
                query = {k: v[0] for k, v in parse_qs(u.query).items()}
                with app.lock:
                    try:
                        res = app.dispatch(method, u.path, query, body, self.headers)
                        status = 201 if method == "POST" and isinstance(res, dict) and res.pop("_created", False) else 200
                        self._send(status, res)
                    except HttpError as e:
                        self._send(e.status, {"error": e.message, **e.extra})
                    except Exception as e:  # noqa: BLE001
                        self._send(500, {"error": "internal error", "detail": type(e).__name__})

            do_GET = lambda s: s._handle("GET")
            do_POST = lambda s: s._handle("POST")
            do_PUT = lambda s: s._handle("PUT")
            do_PATCH = lambda s: s._handle("PATCH")
            do_DELETE = lambda s: s._handle("DELETE")
        return H

    def serve(self, port=None, host="127.0.0.1"):
        if not self.db:
            self.reset()
        srv = ThreadingHTTPServer((host, port if port is not None else self.port), self.make_handler())
        srv.daemon_threads = True
        return srv


def created(d):
    d["_created"] = True
    return d
