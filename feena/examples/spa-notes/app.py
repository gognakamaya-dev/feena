"""spa-notes — a client-rendered single-page app, the kind httpx can't test.

The server sends a static HTML shell; ALL rendering happens in JavaScript. It carries two XSS
bugs that only exist in the rendered DOM:
  - reflected: the ?q= param is written into the page via innerHTML on load
  - stored:    notes are saved server-side and rendered via innerHTML on every load

A raw HTTP fetch sees none of this (the marker isn't in the shell). A browser does. This exists
to show why the hostile checks must read the rendered DOM. FOR TESTING ONLY.
"""
from flask import Flask, request, jsonify

app = Flask(__name__)
NOTES: list[str] = []

SHELL = """<!doctype html><html><head><title>Notes</title></head><body>
<h1>Notes SPA</h1>
<div id="out"></div>
<form id="noteform"><input name="text" id="text" placeholder="new note"><button type="submit">add</button></form>
<ul id="notes"></ul>
<script>
  // reflected: write the q param into the page unescaped (client-side)
  const q = new URLSearchParams(location.search).get('q');
  if (q) document.getElementById('out').innerHTML = 'Results for: ' + q;

  async function render() {
    const r = await fetch('/api/notes');
    const notes = await r.json();
    // stored: render each note unescaped (client-side)
    document.getElementById('notes').innerHTML =
      notes.map(n => '<li>' + n + '</li>').join('');
  }
  document.getElementById('noteform').addEventListener('submit', async (e) => {
    e.preventDefault();
    await fetch('/api/notes', {
      method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({text: document.getElementById('text').value})
    });
    render();
  });
  render();
</script>
</body></html>"""


@app.get("/api/health")
def health():
    return {"ok": True}


@app.get("/")
def home():
    return SHELL


@app.get("/api/notes")
def get_notes():
    return jsonify(NOTES)


@app.post("/api/notes")
def add_note():
    text = (request.get_json(silent=True) or {}).get("text") or request.form.get("text", "")
    if text:
        NOTES.append(text)
    return {"ok": True}


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5001)
