# EHDS Gatekeeper

An automated Health Data Access Body for the European Health Data Space (Regulation (EU) 2025/327, Chapter IV).
Built for AIM Healthcare Hackathon Vienna 2026, Track 3.

A request arrives as JSON. The app decides `REJECT`, `APPROVE_STATISTICAL` or `APPROVE_SPE`, cites the articles,
computes privacy-safe statistics or provisions a secure processing environment (SPE) with downloads blocked,
and explains the decision to the applicant and to staff.

**Core idea: the AI translates, the code computes.** No model ever sees patient data, writes SQL, produces a number
or makes the decision. The whole system meets every track metric with the AI switched off.

## Metric results (rules-only mode, 3 runs; `scripts/eval.py`)

| Metric | Result | Target |
|---|---|---|
| Correct decisions | 10 of 10 | 10 of 10 |
| Correct numbers | 6 of 6 | 6 of 6 |
| Privacy leaks | 0 | 0 |
| Consistency (3 runs) | 10 of 10 | 10 of 10 |
| Time to answer (slowest) | 0.3 s | under 60 s |
| Extra suites: 20 hidden-style + 16 adversarial requests | 36 of 36 | all |

Full per-request table: `docs/METRICS.md`.

## Run it

```bash
uv venv .venv && uv pip install --python .venv/bin/python duckdb pandas fastapi uvicorn pydantic openai httpx pytest
git clone https://github.com/AIM-Austria/TRACK-3-ehds.git track      # the synthetic data
.venv/bin/uvicorn app.api:app --app-dir backend --port 8000          # API on :8000
cd frontend && npm install && npm run dev                             # UI on :5173
.venv/bin/python -m pytest backend/tests -q                           # 134 tests
.venv/bin/python scripts/eval.py --runs 3                             # metrics -> docs/METRICS.md
```

AI layer (optional): set `EHDS_LLM_BASE_URL`, `EHDS_LLM_MODEL` and `EHDS_LLM_API_KEY` for any OpenAI-compatible endpoint
(self-hosted vLLM, an EU provider). See `infra/.env.example` and `infra/vllm.sh`. `scripts/fake_llm.py` is a keyword
stand-in server (not a model) for testing the AI path without a GPU.

## Architecture

```
React UI ── /api ──> FastAPI (backend/app/api.py)
                         │
 A Pre-screening   pipeline.validate · security.sanitise_request · security.detect_injection
 B Purpose         decision.rules_signal ─┐
                   llm: classifier ───────┼─> decision.decide (fixed decision table, strictness order)
                   llm: red-team ─────────┤    REJECT stops here: no data is touched
                   llm: justification ────┘    every AI claim needs a verbatim quote, checked in code
 C Query plan      parser.parse (rule grammar over the definitions, terminology.py for plain English)
                   catalog.unknown_codes · coverage check · explain.readable (template back-translation)
 D Execute         compiler.compile_sql -> DuckDB; opted-out patients removed in the hdab.* views (db.py)
 E Output check    privacy.publish (small-cell rule) · privacy.leak_check · ledger (differencing guard)
 F Release         decision letter + Five Safes record · spe.create (cohort + named record types only)
                   SPE download -> 403 + audit (Art. 73) · audit.py hash-chained log
```

| Component | File | Notes |
|---|---|---|
| Data layer | `db.py` | DuckDB over the CSVs. Opt-outs (Art. 71) removed at the view layer, so no query can see them. |
| Query plan | `plan.py` | Closed schema: population, criteria, encounter filter, groups, measures, SPE record types. |
| Rule parser | `parser.py`, `terminology.py` | Translates definitions without a model; maps plain English (e.g. "pneumonia", "blood thinner") to codes present in the data. Unknown terms hold the numbers for review. |
| Compiler | `compiler.py` | Plan to SQL, deterministic; codes, dates and names validated against strict patterns (no injection). |
| Privacy | `privacy.py`, `ledger.py` | Counts <10 shown as `<10`; percentages and means from <10 patients suppressed; halves rounded up; empty groups shown. Ledger flags releases that differ from earlier ones by 1–9 people. |
| Decision | `decision.py`, `policy.py` | Signals from rules, an AI classifier and an AI red-team prompt. Fixed table: 2 prohibited votes reject automatically, 1 rejects with review; injection never allows an SPE; Art. 53(2) public-body check; Art. 66 downgrade. |
| AI layer | `llm.py`, `security.py` | Any OpenAI-compatible endpoint; stateless calls per task; datamarking, canary, schema-constrained enums with verified evidence quotes; results cached for consistency. |
| SPE | `spe.py` | Per-permit DuckDB file with only the cohort and the named record types; IDs kept; downloads blocked. |
| Explanations | `explain.py`, `articles.json` | Plain-English plan, decision letter, Five Safes record, article summaries. |
| API | `api.py`, `pipeline.py`, `metrics.py`, `audit.py` | Contract in `docs/UI_AND_PITCH_PLAN.md` §3. Suppressed cells reach the browser as `value: null`. |

Models and services: no external service is required. Optionally an open-weight model (e.g. Mistral Small 3.2 24B)
served by vLLM on EU infrastructure. Data flow: `infra/SOVEREIGNTY.md`.

## Tests (`backend/tests`, 134)

- Privacy units, rounding (Python's banker's rounding trap), leak checker.
- One test per data trap: opt-outs in denominators, age boundary, empty `end_date` read as NULL, latest vs any value,
  stays started vs ended, main diagnosis, empty groups, other active-on dates, SQL injection.
- Official 10: golden plans, parser equals golden, pipeline decisions, SPE minimisation, consistency.
- 20 hidden-style requests (grouping by hospital, main diagnosis without a code, German, plain English, unknown term) and
  16 adversarial requests (credit scoring, recruiting, alcohol, data resale, disguised marketing, negated near-miss,
  prompt injection, homoglyphs, zero-width characters, Art. 53(2)). Expected values come from independent oracle SQL
  (`scripts/make_fixtures.py`).
- Decision-table property test: adding a red flag never makes the outcome less strict. 32 injection variants
  across 4 fields never succeed.

## What works and what does not

Works: all metrics in rules-only mode; hidden-style requests in the template style; injection and near-miss handling;
SPE with blocked download; full audit trail.

Limits: definitions in German (or other free wording) are not translated without the AI layer, so the numbers are held
for staff review (the decision is still made). The AI layer has been tested against a stand-in server, not yet against
a real model on the A1 GPU. The `strict` output profile (secondary suppression, rounding to 5) is designed but not built.
Article summaries are paraphrases; verify quotes against EUR-Lex.
