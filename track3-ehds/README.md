# Health Data Access Desk (EHDS, Track 3)

> **Hackathon simulation.** All patients are synthetic. This is **not** a real government approval system.

A browser-based desk for a Health Data Access Body under the European Health Data Space Regulation
(EU) 2025/327, Chapter IV. An applicant submits a request in the challenge JSON format. The desk then:

1. decides `REJECT`, `APPROVE_STATISTICAL` or `APPROVE_SPE` and cites the articles,
2. for statistics, generates a query plan from the request's definitions and computes the numbers with
   the small-cell rule,
3. for a secure processing environment (SPE), copies only the selected patients' requested records into an
   isolated workspace, reports the exact cohort size and blocks downloads,
4. shows the decision, the reason and every privacy check to the applicant and to staff.

The challenge description is in [CHALLENGE.md](CHALLENGE.md). `data/` and `requests/` are copied unchanged
from `AIM-Austria/TRACK-3-ehds@ba0ff54`. A test verifies their SHA-256 checksums against
[challenge.sha256](challenge.sha256).

## Quick start (one command)

Requires Python 3.9 or newer. There are no packages to install. Tested with 3.9.6, 3.12.12 and 3.14.7.

```bash
cd track3-ehds
python3 -m desk
```

Then open **http://127.0.0.1:8000**. Use `python3 -m desk serve --port 8080` to pick another port.

| Task | Command |
|---|---|
| Start the web app | `python3 -m desk` |
| Evaluate R01–R10 three times against `expected.json` | `python3 -m desk evaluate` (add `--save` to write `reports/`) |
| Same evaluation through the running web server | `python3 -m desk evaluate --url http://127.0.0.1:8000` |
| Unit and integration tests (63) | `python3 -m unittest discover -s tests -t .` |
| Browser end-to-end test (13 checks, needs Node ≥ 22 and Chrome) | `node tests/e2e/browser_flow.mjs http://127.0.0.1:8000` |
| Process one file on the command line | `python3 -m desk run new_requests/N01.json [--staff]` |

## Results on the 10 supplied requests

Actual output of `python3 -m desk evaluate --save` ([reports/evaluation.txt](reports/evaluation.txt)):

```
req  decision             articles       dec  numbers  leaks  consistent   max ms
----------------------------------------------------------------------------------
R01  APPROVE_STATISTICAL  53,69          OK   OK       0      yes           179.5
R02  REJECT               54             OK   -        0      yes             0.9
R03  APPROVE_STATISTICAL  53,69          OK   OK       0      yes           131.8
R04  REJECT               54             OK   -        0      yes             0.7
R05  APPROVE_SPE          53,66,68,73    OK   OK       0      yes           159.8
R06  REJECT               54             OK   -        0      yes             0.8
R07  APPROVE_STATISTICAL  53,69          OK   OK       0      yes            99.7
R08  APPROVE_STATISTICAL  53,69          OK   OK       0      yes           154.7
R09  APPROVE_STATISTICAL  53,66,69       OK   OK       0      yes           215.0
R10  REJECT               54             OK   -        0      yes             1.2
```

| Metric | Result | Target |
|---|---|---|
| Correct decisions (decision and articles) | **10 / 10** | 10 of 10 |
| Correct numbers (approved requests: 5 statistical answers plus the R05 cohort size) | **6 / 6** | 6 of 6 |
| Privacy leaks | **0** | 0 |
| Consistency across 3 runs (fresh data load per run) | **10 / 10** | 10 of 10 |
| Slowest answer, submission to answer | **0.22 s** (R09; 0.21 s over HTTP) | under 60 s |

The data load at startup takes about 1.1 s. `expected.json` is read only by `desk/evaluate.py` and the tests,
and only after the answers have been produced. No runtime code path reads it.

## What the applicant and staff see

| Applicant: R10 rejected (Art. 54) | Applicant: R08 statistics with `<10` / `suppressed` |
|---|---|
| ![R10](reports/screenshots/01-r10-reject.png) | ![R08](reports/screenshots/02-r08-statistics.png) |
| **Applicant: R05 SPE, exact cohort, blocked download** | **Staff: decision trace, privacy checks, plan, SQL** |
| ![R05](reports/screenshots/03-r05-spe-download-blocked.png) | ![Staff](reports/screenshots/05-staff-view.png) |

- **Applicant portal:** pick one of R01–R10 or our new requests N01–N07, or paste or upload JSON. The
  decision banner shows the cited articles with their titles, a plain-language reason, the answer time,
  whether patient data was queried and the number of privacy checks passed.
- **Statistics:** every requested group is listed, even if empty. Small cells are marked, and a legend
  explains the rules.
- **SPE:** shows the exact cohort size, the record types copied in (with row counts, columns and filters)
  and the record types that were left out. A *Download records* button returns HTTP 403, and the attempt
  is logged.
- **Staff view:** a case register, the full request, the decision trace (which rule fired, with quoted
  evidence), how each definition was interpreted (term → ICD-10/ATC/LOINC and its source), the IR, the
  generated parameterized SQL, the privacy checks and the SPE access log.
- **Evaluation tab:** runs the harness (30 submissions) and shows the five metrics.

## Architecture

```
 Browser UI (web/: index.html, app.js, styles.css; no build step, strict CSP)
        │ JSON over HTTP, 127.0.0.1
        ▼
 desk/server.py  (Python stdlib http.server)  ──►  desk/pipeline.py  Desk.process(request)
   1  request_schema.py   validate the JSON format; reject malformed input with clear errors
   2  policy.py           decision + articles, in the README order (54 → 69 → 66/68/73 → 66/69)
                          REJECT / NO_DECISION stop here: 0 database queries
   3  parser.py           definitions + question → intermediate representation (IR)
      vocabulary.py       plain English → ICD-10 / ATC / LOINC / encounter types; reference groups
      llm.py (optional)   validated LLM fallback, only if configured and only when the rules fail
   4  ir.py               IR validator (codes, references, group sizes, no free-form SQL)
   5  executor.py         IR → parameterized SQL (one feature query per request) → exact aggregation
      disclosure.py       <10, suppressed percentages and means, half-up rounding on exact fractions
   6  spe.py              one isolated SQLite database per data permit; downloads → HTTP 403 + log
   7  audit.py            independent privacy checks on the released answer; any failure withholds it
        ▼
 datastore.py  in-memory SQLite built from data/*.csv; opted-out patients are never loaded
```

**Design choices**

- **Standard library only:** `sqlite3`, `http.server`, `fractions`, `csv`. One command starts the app on
  any machine with Python, with no dependency drift.
- **One central database** (single node), not federated queries. Data holders stay visible through the
  `data_holder` column, so results can be grouped by hospital.
- **Rules first, LLM optional.** Every decision and every number on the supplied requests comes from
  deterministic code, so results are reproducible and explainable.

### Decision engine ([desk/policy.py](desk/policy.py))

Uses only `purpose`, `question`, `definitions`, `requested_as` and `requested_format`. The ID, the
applicant name and the organisation are never inspected. A test renames them and checks that the result
does not change.

1. **Prohibited purpose → `REJECT`, Art. 54.** The patterns follow Art. 54(1):
   - (a) decisions about identified individuals or re-identification, e.g. matching with an employee or
     customer list,
   - (b) insurance premiums or exclusion, credit and loans, job offers and employment decisions,
   - (c) advertising and marketing,
   - (d) developing harmful products such as tobacco, nicotine, alcohol, weapons or addictive products.

   Benign phrases such as *marketing authorisation*, *post-marketing surveillance*, *smoking cessation* and
   *tobacco control* are removed first, so they do not trigger a rejection.
2. **Health data request → `APPROVE_STATISTICAL`, Art. 53 + 69.**
3. **Access application that explains why statistics are not enough → `APPROVE_SPE`, Art. 53, 66, 68,
   73.** The explanation must be explicit, e.g. *"aggregates are not enough"* or *"needs individual-level
   histories"*. Negated forms (*"we do not need individual-level data"*) do not count.
4. **Any other access application → `APPROVE_STATISTICAL`, Art. 53, 66, 69.**

The Art. 53(1) purpose points are detected and cited in the reason. If no allowed purpose is recognised,
the desk returns **`NO_DECISION`**: it refers the case to staff rather than approving automatically.

### Data engine: IR → SQL ([desk/parser.py](desk/parser.py), [desk/ir.py](desk/ir.py), [desk/executor.py](desk/executor.py))

Nothing is hand-written per request. Each definition is classified and compiled into a small IR:

| Definition shape (examples from the requests) | IR |
|---|---|
| `Adult = aged 18 or older on 31 December 2025` | patient set `age >= 18` (age = 2025 − birth year) |
| `… ICD-10 code starting with E11` / `… ATC code starting with B01AA or B01AF` | condition / medication concept (prefix match) |
| `A medication is active on 31 December 2025 if …` | `has_medication(active=true)`: start ≤ ref and (end empty or ≥ ref) |
| `Use the latest BMI (LOINC 39156-5) per patient; patients without a BMI are left out` | observation with `pick=latest` + population filter |
| `Inpatient stay = encounter with type 'inpatient'`, `… primary_icd10 starts with I50` | encounter concept (type, dates, primary_icd10, data_holder) |
| `Count stays (not patients) whose start_date is in 2025` | encounter counting unit + date filter |
| `Age bands …: 65-74, 75-84, 85+` / `Report per region and age band: …` | dimensions: region, age band, sex, hospital, year |
| `Prevalence = A / B × 100`, `% with an active ARB`, `that share in %` | percent measure on (hidden) numerator and denominator counts |
| `mean BMI`, `their mean HbA1c` | mean measure over the latest value per patient |
| `Cohort = …` + `Provide pseudonymised conditions, medications and HbA1c values …` | SPE cohort + record types (observations limited to LOINC 4548-4) |

<details><summary>Example: IR for R08 (simplified)</summary>

```json
{"concepts": {
   "breast_cancer": {"kind": "condition", "icd10": [{"code": "C50", "match": "prefix"}]},
   "women": {"kind": "set", "expr": {"op": "attr", "field": "sex", "values": ["female"]}},
   "bmi": {"kind": "observation", "loinc": "39156-5", "pick": "latest"}},
 "population": {"op": "and", "args": [{"op": "has_observation", "id": "bmi"},
                                      {"op": "has_condition", "id": "breast_cancer"}]},
 "dimensions": [{"type": "region", "groups": ["Burgenland", "...", "Wien"]}],
 "measures": [
   {"id": "m1", "type": "count_patients", "label": "Number of women with a BMI",
    "set": {"op": "and", "args": [{"op": "ref", "id": "women"}, {"op": "has_observation", "id": "bmi"}]}},
   {"id": "m2", "type": "mean", "label": "Mean BMI", "observation": "bmi", "set": "<same as m1>"}]}
```

Breast cancer is defined but not named in the report line. It is named in the question, so it becomes a
population filter, and the staff view states that reason.
</details>

How a validated IR is executed:

- **Compilation:** every atom becomes one parameterized `EXISTS`/scalar subquery column of a single
  `SELECT … FROM patients`. Encounter counts use a second parameterized query.
- **Aggregation:** grouping and aggregation run in Python on exact fractions.
- **Safety net:** every content word of a definition must be understood. Unknown words, unsupported filters
  or ambiguous roles raise an `InterpretationError`. The case is then shown as *"could not be interpreted
  safely, no numbers produced"*, with the reason and a hint, instead of a guessed answer.

### Privacy controls

| Rule | Where it is enforced | How it is checked |
|---|---|---|
| Opted-out patients excluded (Art. 71) | `datastore.py` never inserts their rows into the queryable DB (839 patients, 4,148 rows) | `audit.py` intersects contributing patients and SPE cohorts with the opted-out IDs; mini-dataset tests (Wien would show `10` instead of `<10` if they leaked) |
| Counts < 10, including 0 → `<10` | `disclosure.count_cell` | audit recomputes from internal raw counts |
| Percentages with numerator or denominator < 10 → `suppressed` | `disclosure.percent_cell` | audit |
| Means of fewer than 10 patients → `suppressed` | `disclosure.mean_cell` | audit |
| Half-up rounding, one decimal | exact `Fraction` arithmetic; floats are refused | tests: `37.25 → 37.3`, `1.45 → 1.5` (Python `round` gives 37.2 and 1.4) |
| Every requested group shown | group lists come from the request (age bands) or reference domains (9 federal states, 3 hospitals, 2 sexes) | audit: rows = product of group counts |
| No patient-level records in statistics | patient-level report lines are refused; helper counts stay internal | audit scans the released JSON for patient IDs, encounter IDs and dates |
| SPE contains only the cohort and the requested record types | `spe.py` copies into `spe_workspaces/<id>/workspace.sqlite` with pseudonymous IDs | audit opens the workspace read-only and checks tables, IDs and LOINC filter |
| Downloads blocked (Art. 73) | `/api/spe/<id>/download` always returns 403 and logs the attempt; workspaces are never served as static files | HTTP test + browser test |
| Prohibited purposes never touch data | policy runs before planning | test: database query log unchanged for R02/R04/R06/R10 |

If any check fails, the answer is **withheld** rather than released.

### Models and services

- **No external service is used by default.** The reported metrics were produced with no network access to
  any model.
- **Optional LLM fallback** ([desk/llm.py](desk/llm.py)). Set `DESK_LLM_PROVIDER=anthropic|openai`,
  `DESK_LLM_MODEL=<model>` and the matching API key to enable it. It is called only when the rule-based
  interpreter fails.
  - Only the request text is sent: `requested_as`, `requested_format`, `purpose`, `question`,
    `definitions`. The applicant identity and patient data are never sent.
  - The model's JSON plan must pass the same IR validator before any query. Unknown codes are flagged, and
    staff see *"LLM-assisted, staff review recommended"*.
  - Decisions are never delegated to the model.
  - **This path has only been tested with a mocked model** (`tests/test_llm_fallback.py`). No API key was
    used during development.

## New test requests (not in the challenge repository)

| ID | What it exercises | Result on the data |
|---|---|---|
| [N01](new_requests/N01.json) | `primary_icd10` filter (I50) + grouping by hospital (`data_holder`), stays in 2025 | Nord 66, Süd 60, West 31 stays |
| [N02](new_requests/N02.json) | inpatient stays vs distinct patients, by hospital | Nord 421 stays / 381 patients, Süd 382 / 351, West 276 / 252 |
| [N03](new_requests/N03.json) | SPE with encounters + conditions + medications (readmission model) | `APPROVE_SPE`, cohort 248 |
| [N04](new_requests/N04.json) | credit scoring → prohibited | `REJECT`, Art. 54(1)(b) |
| [N05](new_requests/N05.json) | latest eGFR threshold (< 45), sex × age band, percentages | 6 cells, e.g. female 80+: 89 / 48 / 53.9 % |
| [N06](new_requests/N06.json) | plain English only ("type 2 diabetes", "statin") → vocabulary codes E11*, C10AA* | per region, e.g. Wien 263 / 109 / 41.4 % |
| [N07](new_requests/N07.json) | unsupported derived value (length of stay) | approved, **no numbers produced**, clear reason |

`tests/test_new_requests.py` checks N01–N06 against an independent brute-force calculation that reads the
CSV files directly. That calculation shares no code with the desk.

## Tests

- `tests/test_disclosure.py`: zero and small cells, suppressed percentages and means, half-up rounding,
  floats refused.
- `tests/test_engine_rules.py`: a hand-made mini dataset ([tests/minidata.py](tests/minidata.py)) with known
  answers. It covers:
  - opt-outs excluded in every table,
  - empty groups still shown,
  - latest vs earliest observation,
  - active medications (end date on the reference day, start date on the reference day, start date after
    it),
  - encounter vs patient counts,
  - hospital grouping,
  - `primary_icd10` vs `conditions`,
  - percentage suppression,
  - refusal of patient-level output,
  - SPE contents.
- `tests/test_server.py`: SPE download returns 403 over HTTP (GET/POST, per table), the access log, no
  records in the manifest, and no path traversal to data or workspaces.
- `tests/test_policy.py`, `tests/test_parser.py`: prohibited and benign purposes, the rule order, applicant
  identity ignored, vocabulary mapping, conservative failures, IR validation.
- `tests/test_supplied_requests.py`: R01–R10 against `expected.json`, zero queries for rejections, results
  independent of ID and applicant, determinism, unchanged challenge files.
- `tests/test_llm_fallback.py`: only request text is sent, invalid proposals are refused, the model is not
  called when the rules succeed.
- `tests/e2e/browser_flow.mjs`: headless Chrome through the DevTools protocol (no npm packages). It runs the
  demo flow and checks the evaluation tab and that the browser console has no errors (including CSP
  violations). Screenshots are written to `reports/screenshots/`.

## Limitations

- **Supported phrasings.** The rule-based interpreter supports the shapes above and many variations, such as
  hospital or year grouping, thresholds on the latest measurement, onset or start-date filters,
  "at least N stays", and/or/not, and plain-English vocabulary terms. Phrasings outside this grammar are
  refused with an explanation rather than guessed (N07). The optional LLM fallback is meant to widen
  coverage, but it is untested against a live model.
- **Unsupported computations:** derived values such as length of stay, date differences, incidence over
  person-time and statistics other than counts, percentages, means and medians.
- **Decisions are keyword rules.** They cite their evidence, but adversarial wording could evade them. A real
  access body would keep human review.
- **Art. 53(2)** (purposes (a)–(c) reserved for public bodies) is only a staff note, because the challenge
  forbids deciding by applicant identity.
- **Defaults when a term is undefined.** "Adults" or "children" without a definition default to 18+ and
  under 18, and the answer says so explicitly. A definition that is used neither in the report nor in the
  question makes the request fail as ambiguous.
- **Small-cell rule.** It is applied exactly as specified (counts, percentages, means). There is no
  secondary suppression, and encounter counts from fewer than 10 distinct patients are only flagged to
  staff.
- **Simulated SPE.** The SPE is a local SQLite file per permit, with no remote desktop, user accounts or
  egress review workflow. The case register is in memory and is lost on restart. There is no login and no
  identity verification.

## Two-minute demo script

| Time | Action | What to say |
|---|---|---|
| 0:00 | Open http://127.0.0.1:8000 | "A Health Data Access Desk for EHDS secondary use. This is a hackathon simulation with synthetic data, as the banner says." |
| 0:10 | Select **R10** → *Submit* | "A nicotine-pouch company wants COPD statistics. It is rejected under Art. 54(1)(d) before any data is touched: *Patient data queried: no*." |
| 0:30 | Select **R08** → *Submit* | "A research request, approved as anonymised statistics under Art. 53 and 69. The numbers come from a query plan generated from the definitions. Regions under 10 show `<10` and the means are suppressed. Opted-out patients are excluded and values are rounded half-up." |
| 0:55 | Select **R05** → *Submit*, then click **Download records** | "A model-training application that explains why aggregates are not enough, so it gets an SPE under Art. 53, 66, 68 and 73. Exactly 1 152 patients are selected, with only conditions, medications and HbA1c values copied in. A download attempt returns HTTP 403 and is logged." |
| 1:25 | Select **N01** (our new request) → *Submit* | "A request the jury could send: heart-failure stays by hospital, using `primary_icd10` and `data_holder`, which none of the ten supplied requests use." |
| 1:40 | Click *Open staff view* | "Staff see the rule trace with quoted evidence, how each definition was mapped to ICD-10, ATC or LOINC, the SQL and all privacy checks." |
| 1:50 | *Evaluation* tab → *Run* | "10 of 10 decisions, 6 of 6 answers, 0 leaks, 10 of 10 consistent, about 0.2 seconds per answer. What doesn't work yet: derived values like length of stay are refused (N07), and the LLM fallback has not been tested against a live model." |

## Repository layout

```
track3-ehds/
  CHALLENGE.md, data/, requests/      challenge files (unchanged, see challenge.sha256)
  desk/                               application package (python3 -m desk)
  web/                                static UI
  new_requests/                       N01–N07, our additional requests in the same format
  tests/                              unittest suites + e2e/browser_flow.mjs
  reports/                            evaluation output and screenshots
  spe_workspaces/                     created at runtime, one folder per data permit (git-ignored)
```
