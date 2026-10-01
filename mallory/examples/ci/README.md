# CI examples

- `mallory-docker-compose.yml`: app started with `docker compose up --wait`.
- `mallory-node.yml`: app started directly (Node shown; any stack works).

Replace `OWNER/mallory@v0` with wherever you host the action, or use `uses: ./` if you vendor this
repo. See the "GitHub Action" section of the main README for the adoption steps.

Mallory's own `.github/workflows/selftest.yml` runs the local action against `examples/taskflow-fixed`
and expects a green check. It has been validated structurally and against a simulated GitHub API
(`tests/test_ci.py`), but not yet run on GitHub itself.
