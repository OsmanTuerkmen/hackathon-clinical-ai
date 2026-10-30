# Branch `hackathon-melih`: bring Melih's strengths into Doccess

For: the coding agent working on Doccess (`track3-ehds/`). Read this fully, then integrate on this branch.

This branch starts from `feature/track3-ehds-access-desk` (Doccess at commit `6c1f56d`). It adds one folder,
`melih-gatekeeper/`, holding a second Track 3 app built by Melih's team (FastAPI + React). That app reaches the same
metrics as Doccess (10/10, 6/6, 0 leaks, 10/10 consistent) and passes 36 extra hidden-style and adversarial cases.

**Goal:** keep Doccess's look, stack and rules. Port Melih's *animations*, *decision report* and *safety layer* into
Doccess. Do not move Doccess to React or FastAPI, and do not run the two apps side by side in the demo.

## Doccess rules still apply (from `track3-ehds/AGENTS.md`)

- Python standard library only, plain JS, no CDN, no `innerHTML` with request data (use the existing `el()` helper),
  CSP-compatible (no inline `<style>`; dynamic sizes via `el.style.setProperty`).
- Never edit `track3-ehds/data/`, `requests/` or `CHALLENGE.md`. `expected.json` is read only by `evaluate.py` and tests.
- After every step: `python3 -m desk evaluate` still gives 10/10, 6/6, 0 leaks, 10/10;
  `python3 -m unittest discover -s tests -t .` passes; `node tests/e2e/browser_flow.mjs` passes.
- Animations only under `prefers-reduced-motion: no-preference`.

## What to port, in priority order

See the screenshots in `melih-gatekeeper/docs/screens/` (frames `stepper_R01_0..5` and `stepper_R02_0..5` show
the motion step by step).

### 1. Animated pipeline stepper (highest impact for the demo video)
- **Source:** `melih-gatekeeper/frontend/src/components/PipelineStepper.tsx` and `useDisplaySteps` in
  `melih-gatekeeper/frontend/src/hooks.ts`.
- **Target:** `renderSteps()` / `steps()` in `track3-ehds/web/app.js`, plus CSS in `web/styles.css`.
- **Behaviour to copy:**
  - Reveal steps one at a time with a minimum hold of about 340 ms per step and about 160 ms per skipped step.
  - The active step gets a pulsing ring. Each connector line fills from left to right as the step completes.
  - Done steps become filled dark circles with a check. Failed or rejected steps are red with an ×. Skipped steps are dashed with a "–".
  - For REJECT, show a chip under the stepper: "Rejected before any data was touched". Doccess already knows "no patient data touched".
  - Show the time in ms under each step once it is done.
  - Reveal the decision badge only after the last step.
- **How:** keep Doccess's `steps(view)` states (`ok/stop/warn/skip/lock`). Add a small timer loop that adds an
  `is-shown` class step by step, and use CSS transitions for the ring, fill and colours.

### 2. On-screen decision letter (the "final report")
- **Source:** `melih-gatekeeper/frontend/src/components/DecisionLetter.tsx`; screenshots `letter_R01.png` and `letter_R02.png`.
- **Target:** the applicant answer area in `renderAnswer()`. **Keep** Doccess's PDF letter button and
  `desk/letter.py`, and add the same content to the PDF where it is cheap.
- **Sections:**
  1. Seal and authority line, reference number and date.
  2. "Dear …", then a one-line headline ("Your request is approved. Here are your statistics." / "We cannot approve your request.").
  3. Decision badge.
  4. An amber **downgrade callout** when records were asked for but statistics were given (Art. 66).
  5. "Why", in plain language.
  6. The results table.
  7. **"The law"** accordion: one row per cited article, with title, plain summary and a short quote. Doccess has `law.py`/`article_titles`.
  8. "What you can do instead".
  9. "Next steps".
  10. A **Five Safes record** (project, people, setting, data, outputs).
  11. An appeal note.
  12. A footer with the reference and article chips.
- **Style:** a serif typeface for the letter body only (system serif stack, no web font download), and a thin dark top border on the letter card.

### 3. Protected cells
- **Source:** `melih-gatekeeper/frontend/src/components/ResultsTable.tsx`; screenshot `protected_cells.png`.
- **Target:** `masked()` / `renderStatistics()` in `app.js`.
- **Behaviour:** cells showing `<10` or `suppressed` get a diagonal hatch (CSS `repeating-linear-gradient`), a small lock icon and a tooltip ("Fewer than 10 people, hidden to protect privacy").
- **Legend** above the table: "N cells protected". Never compute or round in the UI.

### 4. Blocked download moment in the secure workspace
- **Source:** `melih-gatekeeper/frontend/src/pages/SpeWorkspace.tsx`; screenshots `spe_before.png`, `spe_blocking.png` and `spe_blocked.png`.
- **Target:** `renderSpe()` (`#download-result`).
- **On a blocked download:**
  1. Wait about 400 ms.
  2. Shake the workspace card (a CSS keyframe, about 400 ms) and give it a red border.
  3. Drop in a red banner: "DOWNLOAD BLOCKED · HTTP 403 · Art. 73", one sentence of explanation, and the blocked-attempts counter.
  4. Slide a new audit line in at the top.
  5. Show a toast: "Incident logged to HDAB audit trail".
- If Doccess has no download endpoint that returns 403, add one in `desk/server.py` that always returns 403 and writes an audit entry (`desk/audit.py`).

### 5. Staff view: signals and review reasons
- **Source:** `melih-gatekeeper/frontend/src/components/panels.tsx` and `pages/StaffDetail.tsx`; screenshots `staff_r02.png` and `queue.png`.
- **Show:**
  - **Review reasons** as amber callouts.
  - A **Signals** table: Rules / AI classifier / AI red-team / Justification / Injection guard, each with "agrees / disagrees / not run", and the quoted evidence ("verified verbatim").
  - A **Data flow** panel: "Patient data sent to AI: none", plus what was sent and where.
  - "Recommended: X · Needs human review" whenever review is needed.

### 6. Safety layer (port the logic into `desk/`, standard library only)
| Feature | Source (Python) | Notes |
|---|---|---|
| Injection detector (EN+DE phrases, chat-template tokens, embedded JSON, base64, mixed-script/homoglyph words, zero-width characters) | `backend/app/security.py` | Pure stdlib. A hit means human review and **never** APPROVE_SPE. |
| Homoglyph folding (Cyrillic/Greek look-alikes to Latin) before the keyword rules | `security.sanitise_text` | Catches "insurance prеmiums" with a Cyrillic е. |
| Negation-aware prohibited rules ("will **not** be used for premiums" means review, not REJECT) | `decision.rules_signal` | Fixes over-rejection of near-misses. |
| Art. 53(2): purposes (a)–(c) are reserved for public bodies; a private applicant claiming one means review | `decision.decide`, `policy.py` | A real legal rule not mentioned in the track README. |
| Decision table with a strictness order: 2 votes reject automatically, 1 vote rejects with review; injection blocks SPE | `decision.decide` | Property test in `tests/test_boundary.py`. |
| Unknown term in a report item (e.g. "gout") means numbers are held, not "count everyone" | `parser._leftover` | We found this bug in our own app: without it, "patients with gout" counted all patients. |
| Differencing ledger (releases that differ from an earlier one by 1–9 people mean review) | `backend/app/ledger.py` | Pure stdlib. |
| Datamarking, canary and verbatim quote check for LLM outputs | `security.py`, `llm.py` | Only matters if Doccess's `llm.py` returns free text. |

### 7. Extra test suites (run them against Doccess)
- **Source:** `melih-gatekeeper/fixtures/custom/C01–C20` and `fixtures/adversarial/A01–A16`, each with
  `*.expected.json`. The expected numbers come from independent oracle SQL in `scripts/make_fixtures.py`.
- **What they cover:**
  - stays by hospital;
  - pneumonia as main diagnosis without a code;
  - stays that ended in a year;
  - latest vs any HbA1c;
  - active-on 30 June;
  - asthma by sex;
  - hospital × sex nesting;
  - small cells;
  - German definitions;
  - an unknown term;
  - credit scoring, recruiting, alcohol, data resale, disguised marketing;
  - an insurer near-miss;
  - prompt injection in 4 fields;
  - homoglyphs, zero-width characters, Art. 53(2).
- **How:** add a runner, e.g. `track3-ehds/tests/test_melih_suites.py`, that feeds each request to Doccess's pipeline and checks the
  decision, the articles, the values ("every expected value appears under its group") and `needs_review` where Doccess has
  an equivalent. Where Doccess deliberately behaves differently (e.g. `NO_DECISION`), adapt the expectation and note why.
  Do not copy `fixtures/` into `track3-ehds/requests/`.

## Not to port
- The React/Vite frontend, FastAPI and DuckDB. They conflict with Doccess's stdlib-only rule.
- `frontend/src/mock/`, the mock engine. Its copy of `expected.json` must not reach Doccess runtime code.

## Running Melih's app for reference
```bash
cd melih-gatekeeper
git clone https://github.com/AIM-Austria/TRACK-3-ehds.git track
uv venv .venv && uv pip install --python .venv/bin/python duckdb pandas fastapi uvicorn pydantic openai httpx pytest
.venv/bin/uvicorn app.api:app --app-dir backend --port 8001
cd frontend && npm install && npm run dev   # set the vite proxy target to :8001 if Doccess uses :8000
```

## Definition of done
- Doccess looks like Doccess, with the animated stepper, the on-screen decision letter, the protected cells, the
  blocked-download moment and the staff signals.
- `python3 -m desk evaluate`: 10/10, 6/6, 0 leaks, 10/10. Unit tests and the browser E2E pass.
- The new suite from step 7 passes, with any deliberate differences documented.
- The README credits both teams, and the "what works / what doesn't" list is updated.
