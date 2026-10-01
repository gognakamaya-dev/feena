# TaskFlow — ground truth (written before running Feena)

Every planted bug, its severity, and whether Feena's **current** hostile checks should catch
it. This is the honest scorecard: recall = of the bugs Feena *should* catch, how many did it;
misses in the "out of reach" set are the product roadmap, not failures.

| # | Bug | Severity | In Feena's current reach? | Why |
|---|-----|----------|------------------------------|-----|
| 1 | IDOR on `/api/tasks/<id>` — any user reads any task | CRITICAL | **Partial / likely miss** | access_control does IDOR by comparing a fixed path across two users; it does not enumerate per-object ids like `/api/tasks/5`. Expected to miss until we add object-id enumeration. |
| 2 | Missing auth on `/api/projects` — all projects to anyone | HIGH | **Miss** | missing-auth only probes a fixed list (`/api/me`, `/api/orders`, `/dashboard`, `/account`, `/api/users`). `/api/projects` isn't on it. |
| 3 | Missing security headers (CSP, nosniff, HSTS, frame-options) | MEDIUM/LOW | **Catch** | headers check is generic. |
| 4 | Reflected XSS in `/search?q=` | MEDIUM | **Catch** | input_reflection probes `/search`. |
| 5 | Stored XSS in task title | HIGH | **Catch** | stored_xss check: submits inert marker via form, re-fetches, detects unescaped persistence. |
| 6 | SQL injection in `/login` | CRITICAL | **Catch** | sqli check: auth-bypass probe battery flips reject->accept. |
| 7 | Plaintext passwords in DB | HIGH | **Miss (out of scope)** | Black-box; Feena can't see the DB. |
| 8 | No signup validation (empty creds accepted) | LOW | **Miss** | No input-validation check. |
| 9 | Hardcoded weak secret key | MEDIUM | **Miss (out of scope)** | Not observable black-box. |
| 10 | Double-submit creates duplicate tasks | MEDIUM | **Miss this run** | clumsy agent territory, needs ANTHROPIC_API_KEY (not set here). |
| 11 | Debug server / interactive debugger on error | HIGH | **Miss** | No debug-exposure check; also off in test harness. |

## Correct behaviour Feena must NOT flag (precision test)
- `/api/me` is properly scoped to the caller.
- `/api/tasks/<id>` and `/api/me` correctly return 401 without a session.

## Expected result
- **Should-catch set:** #1, #2, #3, #4, #5, #6  → recall 6/6 (after the access-control, SQLi and stored-XSS work these runs prompted).
- **Everything else:** expected misses, most of which map directly to the check roadmap
  (object-id IDOR, broader auth probing, SQLi, stored XSS, debug exposure).
- **False positives:** target 0. Any flag on `/api/me` scoping would be a precision failure.
