# Notes for agents working on track3-ehds

- Python standard library only (no pip installs). Supported: Python >= 3.9.
- Run from `track3-ehds/`:
  - App: `python3 -m desk` (http://127.0.0.1:8000)
  - Evaluation: `python3 -m desk evaluate` (must stay 10/10, 6/6, 0 leaks, 10/10 consistent)
  - Tests: `python3 -m unittest discover -s tests -t .`
  - Browser E2E (server must be running): `node tests/e2e/browser_flow.mjs http://127.0.0.1:8000`
- Never edit `data/`, `requests/` or `CHALLENGE.md` (checksums in `challenge.sha256` are tested).
- `requests/expected.json` may only be read by `desk/evaluate.py` and tests, never by runtime code.
- Do not add per-request logic keyed on request IDs or applicant names.
