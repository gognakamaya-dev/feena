# TaskFlow run results

Scored against GROUND_TRUTH.md, written before running Mallory.

## Confirmed findings (current)

| Severity | Finding | Ground-truth bug |
|----------|---------|------------------|
| CRITICAL | IDOR: `/api/tasks/<id>` returns another user's object | #1 |
| CRITICAL | SQL injection auth bypass at `/login` | #6 |
| HIGH | `/api/projects` served with no auth | #2 |
| HIGH | Stored XSS: input persists unescaped at `/tasks` | #5 |
| MEDIUM | Reflected input at `/search` | #4 |
| MEDIUM | Missing `content-security-policy` | #3 |
| LOW | Missing `x-content-type-options`, `strict-transport-security`, `x-frame-options` | #3 |

## Scorecard

- **In-reach recall: 6/6** (#1, #2, #3, #4, #5, #6).
- **False positives: 0** — `/api/me` (scoped) and parameterised `/api/login` not flagged;
  `/search` flagged as reflected XSS but not SQLi.
- **Honest misses (roadmap):** plaintext passwords (#7, black-box), no signup validation (#8),
  weak secret key (#9, black-box), double-submit duplicate (#10, needs the LLM clumsy agent),
  debug server exposure (#11).

## What these runs changed in the product

Every check but headers was hardened by testing against ground truth, and several real defects
in Mallory were found and fixed this way:

1. **Access control** was too naive (fixed path list, no object ids) — missed the IDOR and the
   no-auth endpoint. Rewrote with a content-discovery wordlist + object-level IDOR by owner
   mismatch. Both now caught.
2. **SQLi** first false-positived on `/search` (reflection mistaken for SQL logic) and missed
   the real `/login` SQLi (one brittle probe). Fixed with reflection-normalised comparison and
   an auth-bypass probe battery.
3. **Stored XSS** first missed everything because the form used unquoted HTML attributes the
   parser ignored, and because the crawler logged itself out by following `/logout`. Fixed with
   quote-tolerant attribute parsing, a logout/destructive-link skip, and a defensive re-login.

This is the month-one loop: a realistic app exposes gaps in the checks, and closing them is the
work. All security checks are detection-only by design — they prove a weakness and reproduce it;
they do not extract data, dump schema, run script, or exploit anything.

## Regression loop (executable tests)

The generated tests are now real, not stubs. Against TaskFlow: 9 confirmed findings -> 9
executable tests. All 9 fail on the vulnerable app, all 9 pass on `examples/taskflow-fixed`, and
reverting only the IDOR fix turns exactly one test red. A Mallory re-scan of the fixed app: 0
findings. Building it exposed one more defect in Mallory: the reflected-XSS check used an
alphanumeric marker that comes back identically whether or not the app escapes it, so it could
never recognise a *fixed* page. It now uses the same inert `<b>` probe as the stored-XSS check.
