# Test commands

Run Python commands from the repository root after installing `./shared`,
`./ai[test]`, and `./backend[test]`. On Windows, use
`.venv\Scripts\python.exe` in place of `python`.

| Group | Command | Purpose |
| --- | --- | --- |
| Smoke | `python -m pytest -q -m smoke` | Fast API, access control, and contract checks. |
| Focused | `python -m pytest -q -m "not postgres"` | Offline Backend and AI behavior; used in CI. |
| Full regression | `python -m pytest -q` | All Python tests, including local PostgreSQL tests when `TEST_DATABASE_URL` is set. |

The PostgreSQL suite only accepts a dedicated, empty, local test database.
Without `TEST_DATABASE_URL`, those tests skip. The frontend gate is
`npm --prefix frontend run build`.
