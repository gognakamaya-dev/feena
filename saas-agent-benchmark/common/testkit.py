import json
import subprocess
import threading
import urllib.error
import urllib.request
from pathlib import Path

from common.framework import DEMO_PASSWORD, ROOT


class Client:
    def __init__(self, base, token=None):
        self.base, self.token = base, token

    def call(self, method, path, body=None, raw=False):
        req = urllib.request.Request(self.base + path, method=method,
                                     data=json.dumps(body).encode() if body is not None else None)
        req.add_header("Content-Type", "application/json")
        if self.token:
            req.add_header("Authorization", "Bearer " + self.token)
        try:
            with urllib.request.urlopen(req) as r:
                return r.status, json.loads(r.read() or b"{}")
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read() or b"{}")

    def get(self, p): return self.call("GET", p)
    def post(self, p, b=None): return self.call("POST", p, b if b is not None else {})
    def put(self, p, b=None): return self.call("PUT", p, b or {})
    def patch(self, p, b=None): return self.call("PATCH", p, b or {})
    def delete(self, p): return self.call("DELETE", p)

    def ok(self, method, path, body=None):
        s, j = self.call(method, path, body)
        assert s < 300, f"{method} {path} -> {s} {j}"
        return j


class Harness:
    def __init__(self, app):
        self.app = app
        app.reset()
        self.srv = app.serve(0)
        self.base = f"http://127.0.0.1:{self.srv.server_address[1]}"
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()

    def reset(self):
        self.app.reset()

    def anon(self):
        return Client(self.base)

    def login(self, who="admin@acme.test"):
        s, j = self.anon().post("/api/auth/login", {"email": who, "password": DEMO_PASSWORD})
        assert s == 200, j
        return Client(self.base, j["token"])

    def admin(self): return self.login("admin@acme.test")
    def member(self): return self.login("member@acme.test")
    def viewer(self): return self.login("viewer@acme.test")
    def other(self): return self.login("admin@globex.test")

    def fe(self, hook, *args):
        js = Path(self.app.static_dir) / "app.js"
        out = subprocess.run(["node", str(ROOT / "common" / "fe_runner.js"), str(js), hook, json.dumps(args)],
                             capture_output=True, text=True, check=True).stdout
        return json.loads(out)

    def sql(self, query, args=()):
        return self.app.db.q(query, args)
