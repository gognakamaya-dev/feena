# Generated regression tests (sample output)

This is what `feena run` wrote for `examples/taskflow` — one executable pytest per confirmed
finding, plus the shared `_feena_support.py`. Nothing here was edited by hand.

Try the loop yourself (from the repo root, with `pip install -e . && playwright install chromium`):

```bash
# serve the VULNERABLE app, then point the tests at it  -> every test FAILS
cd examples/taskflow && TASKFLOW_DB=/tmp/a.db python -c "import app; app.init_db(); app.app.run(port=5000)" &
FEENA_BASE_URL=http://127.0.0.1:5000 FEENA_USER1_EMAIL=alice@example.com \
FEENA_USER1_PASSWORD=password123 FEENA_USER2_EMAIL=bob@example.com \
FEENA_USER2_PASSWORD=password123 pytest examples/taskflow/generated-tests

# serve examples/taskflow-fixed instead                                  -> every test PASSES
```

Or just run the integration test that does all of this, including reverting a single fix:
`pytest tests/test_regress.py`.
