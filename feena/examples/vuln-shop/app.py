"""Intentionally-vulnerable demo app. FOR TESTING FEENA ONLY — do not deploy.

Ships with the exact bugs Feena's hostile agent should catch, so you can see a green->red
run on day one:
  - no security headers
  - /api/orders served without auth (missing auth)
  - /api/orders returns the SAME data for every user (IDOR-by-observation)
  - /search reflects the q param unescaped (XSS surface)
"""
from flask import Flask, request

app = Flask(__name__)


@app.get("/api/health")
def health():
    return {"ok": True}


@app.get("/")
def home():
    return "<html><body><h1>Vuln Shop</h1><a href='/search?q=hi'>search</a></body></html>"


@app.get("/search")
def search():
    q = request.args.get("q", "")
    # BUG: reflects user input straight into HTML, unescaped.
    return f"<html><body>Results for: {q}</body></html>"


@app.get("/api/orders")
def orders():
    # BUG: no auth check, and the same rows for everyone (no per-user scoping).
    return {"orders": [{"id": 1, "item": "Secret Widget", "user": "someone_else"}]}


@app.post("/api/login")
def login():
    # Accepts anything; sets a cookie so the IDOR check can log in as two "users".
    resp = app.make_response({"ok": True})
    resp.set_cookie("session", request.json.get("email", "anon"))
    return resp


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=3000)
