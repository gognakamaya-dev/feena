# Generated regression tests (sample output)

This is what `mallory run` wrote for `examples/taskflow` — one executable pytest per confirmed
finding, plus the shared `_mallory_support.py`. Nothing here was edited by hand.

Try the loop yourself (from the repo root, with `pip install -e . && playwright install chromium`):

```bash
# serve the VULNERABLE app, then point the tests at it  -> every test FAILS
cd examples/taskflow && TASKFLOW_DB=/tmp/a.db python -c "import app; app.init_db(); app.app.run(port=5000)" &
MALLORY_BASE_URL=http://127.0.0.1:5000 MALLORY_USER1_EMAIL=alice@example.com \
MALLORY_USER1_PASSWORD=password123 MALLORY_USER2_EMAIL=bob@example.com \
MALLORY_USER2_PASSWORD=password123 pytest examples/taskflow/generated-tests

# serve examples/taskflow-fixed instead                                  -> every test PASSES
```

Or just run the integration test that does all of this, including reverting a single fix:
`pytest tests/test_regress.py`.
