# TaskFlow (fixed)

`examples/taskflow` with each planted security bug actually fixed (ownership check on
`/api/tasks/<id>`, auth on `/api/projects`, parameterised login, escaped output, security
headers). It is the "after" in the before/after that proves Feena's generated regression tests:
red on `taskflow`, green here, and exactly one red if a single fix is reverted
(`tests/test_regress.py`).
