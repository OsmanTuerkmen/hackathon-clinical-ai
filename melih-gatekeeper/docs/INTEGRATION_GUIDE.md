# Integration guide: bringing EHDS Gatekeeper into another app

For: a coding agent working in a different repo, merging our strengths into that repo's own visuals. Work on a branch named `hackathon-melih`.
Source repo: this folder (`ehds-gatekeeper`). Keep the host repo's design system. Port our behaviour and motion, not our colours.

## What to bring over, in priority order

| # | Strength | Where it lives here | How to integrate |
|---|---|---|---|
| 1 | **Decision engine** (all track metrics in rules-only mode, no AI needed) | `backend/app/*` | Copy the `backend/` folder as-is. Run it as a service (`uvicorn app.api:app --app-dir backend --port 8000`), or call `pipeline.run_sync(request_dict)` directly from Python. |
| 2 | **Pipeline animation**: 6 steps, a minimum hold per step, "skipped" steps for rejections | `frontend/src/components/PipelineStepper.tsx` + `useDisplaySteps` in `frontend/src/hooks.ts` | Re-skin with the host's tokens. Keep the logic: hold ~340 ms per step, ~160 ms for skipped steps, pulsing ring on the active step, the "Rejected before any data was touched" note. |
| 3 | **Decision letter** (the final report) | `frontend/src/components/DecisionLetter.tsx` | Serif letter with a seal, headline, downgrade callout, results table, "The law" accordion (`GET /api/articles`), what you can do instead, next steps, Five Safes record, appeal note, reference footer. Re-skin only. |
| 4 | **Protected cells**: hatched background, lock icon, tooltip | `frontend/src/components/ResultsTable.tsx` | Cells with `value: null` and `display` set to `<10` or `suppressed`. Never compute or round numbers in the UI; show `display` exactly as sent. |
| 5 | **Blocked download moment** in the secure workspace | `frontend/src/pages/SpeWorkspace.tsx` | On a 403 from `GET /api/spe/{id}/download`: shake the card, drop in a red banner ("Download blocked · HTTP 403 · Art. 73"), increment the counter, slide in the audit line, show a toast. |
| 6 | **Guided request form** (no JSON for users) | `frontend/src/pages/Apply.tsx` | 4 sections: who, what (statistics or records, as two cards), why, what to count (question + definitions). "Try an example" fills the form from `GET /api/samples`. |
| 7 | **Staff review panel** | `frontend/src/components/panels.tsx`, `frontend/src/pages/StaffDetail.tsx` | Review reasons (amber), signals table (rules / AI classifier / AI red-team / justification / injection guard), readable query plan, privacy checklist, audit timeline, override with a required reason. |
| 8 | **Live metrics scoreboard** | `frontend/src/pages/Metrics.tsx` | `POST /api/metrics/run`, then poll `GET /api/metrics/runs/{id}`. |

## API contract (backend, port 8000; the UI proxies `/api`)

- `POST /api/requests` (request JSON) → `202 {id}`; then poll `GET /api/requests/{id}` every 500 ms while `status == "processing"`.
  The detail object holds `steps[]`, `decision` (`outcome`, `articles`, `needs_review`, `review_reasons[]`, `signals`, `rule_trace[]`, `letter{greeting, headline, why, alternatives[], next_steps[]}`, `five_safes`, `permit`), `plan` (`readable[]`, `catalog_matches[]`, `sql`), `result` (`columns[]`, `rows[]` with `{value, display, suppressed}`, `answer`), `privacy.checks[]`, `spe`, `inference`, `flags`, `audit[]`.
- `GET /api/samples`, `GET /api/articles`, `POST /api/requests/batch`, `GET /api/requests`, `POST /api/requests/{id}/override` (needs `note`), `POST /api/requests/{id}/release`.
- `GET /api/spe/{spe_id}`, `GET /api/spe/{spe_id}/download` (always 403), `POST /api/spe/{spe_id}/export-request`.
- `POST /api/metrics/run`, `GET /api/metrics/runs/{run_id}`, `GET /api/health`.
- Full shapes: `docs/UI_AND_PITCH_PLAN.md` §3.

## Rules that must survive the merge

1. The UI never formats, rounds or computes a number. It shows `display`.
2. Suppressed cells arrive as `value: null`. Never fetch or show the real value.
3. A rejected request shows plan, query and privacy as skipped. No data step runs.
4. No third-party runtime requests: bundle the fonts, no CDNs, no analytics.
5. Keep the tests green: `.venv/bin/python -m pytest backend/tests -q` (134 tests) and `.venv/bin/python scripts/eval.py --runs 3` (10/10, 6/6, 0 leaks).

## Definition of done on `hackathon-melih`

- The host app's look, with our 6-step animation, the decision letter, the protected cells and the blocked-download moment.
- The host UI talks to our backend through the contract above. The R01–R10 examples work end to end.
- Backend tests and `scripts/eval.py` pass unchanged.
- The README credits both teams and keeps our "Metric results" and "What works and what does not" sections.
