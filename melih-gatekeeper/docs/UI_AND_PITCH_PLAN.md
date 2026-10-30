# EHDS Gatekeeper: UI/UX, Demo Video and Pitch Plan

Owner: UI person (1 dev). Readers: the whole team, especially the backend dev, who should match the API contracts in section 3.
Timeline: Thu 29 Oct 20:00–22:00 (2h) + Fri 30 Oct 09:00–15:00 (6h). Video locked by **13:30**. Submit by **14:30**, not 15:00.

> Product line, used everywhere: **"The AI translates. The code computes. The law decides."**

---

## 0. Ground truth from the track repo (what the UI has to show)

| Req | Applicant | As | Expected | Articles | Demo use |
|---|---|---|---|---|---|
| R01 | Danube Inst. Diabetes (AT) | stats | APPROVE_STATISTICAL | 53, 69 | **Hero approve**: prevalence per region (Wien 263/3247 = 8.1%) |
| R02 | Alpenland Versicherung, pricing | stats | REJECT | 54 | **Hero reject**: insurance premiums |
| R03 | Federal Ministry of Health | stats | APPROVE_STATISTICAL | 53, 69 | AF anticoag gap, 3 age bands |
| R04 | Brightline Health Marketing (DE) | stats | REJECT | 54 | Marketing reject |
| R05 | GlucoSense spin-off | access app | APPROVE_SPE | 53, 66, 68, 73 | **SPE hero**: cohort 1,152, blocked download |
| R06 | Berger Logistik HR | access app | REJECT | 54 | Employer + re-identification |
| R07 | National statistics office | stats | APPROVE_STATISTICAL | 53, 69 | Counts stays, not patients |
| R08 | Comprehensive Cancer Centre (IT) | stats | APPROVE_STATISTICAL | 53, 69 | **Suppression hero**: 5 of 9 regions `<10` / `suppressed` |
| R09 | Institute for General Practice | access app | APPROVE_STATISTICAL | 53, 66, 69 | **Downgrade hero**: asked for records, gets stats |
| R10 | Nordic Pouch Company (SE) | stats | REJECT | 54 | Nicotine products |

Jury will submit **new** requests (e.g. filter by `primary_icd10`, group by `data_holder` / hospital). So the applicant form **must** accept arbitrary JSON and free-text, not only the 10 samples. Prepare 2 custom requests ourselves (C01 by hospital, C02 by primary diagnosis) so we've rehearsed it.

---

## 1. Frontend tech choice: **React + Vite + TypeScript + Tailwind + shadcn/ui**

**Use Lovable only for the first 30–45 minutes tonight** to generate the shell (routes, sidebar layout, the 4 screens with mock data), push to GitHub, then continue locally in VS Code/Cursor against the real FastAPI. Lovable writes Vite + React + Tailwind + shadcn, so nothing is lost when we leave it.

Why this one:
- **Looks:** shadcn gives a credible "government SaaS" look in minutes (Table, Badge, Card, Tabs, Dialog, Sheet, Tooltip, Toast). Streamlit looks like a notebook, and the jury will recognise it as one. "Would an access body use this?" is a third of the score, so it has to look like a real tool.
- **Speed:** No SSR, no server components, no auth plumbing (Next.js adds friction we don't need). Vite hot reload is instant. A single `VITE_API_URL` points at FastAPI.
- **Animations for the video:** `framer-motion` gives the pipeline stepper and the blocked-download shake in about 20 lines each. Streamlit can't do that.
- **Data fetching:** `@tanstack/react-query` with `refetchInterval` polls the pipeline status. No websockets needed (SSE only if there's spare time).

Rejected:
- **Streamlit:** fastest to start, but it can't do a staff/applicant split that looks real, has poor control over table cell styling, and polished micro-interactions are impossible.
- **Next.js:** no benefit for a localhost demo and more ways to break.
- **Pure Lovable all the way:** credits run out, it's hard to wire to a local backend, and AI-edit loops get slow at the end.

Packages (lock tonight): `react-router-dom`, `@tanstack/react-query`, `framer-motion`, `lucide-react`, `sonner` (toasts), `recharts` (one small bar chart on the scoreboard only), shadcn components: `button card badge table tabs dialog sheet tooltip textarea input select separator progress scroll-area accordion alert skeleton`.

Routes:
```
/                     -> landing switcher: "Applicant portal" | "HDAB staff console" (two big cards)
/apply                -> Applicant: submit
/apply/:id            -> Applicant: status + decision letter
/staff                -> Staff: queue
/staff/requests/:id   -> Staff: request detail (tabs)
/spe/:workspaceId     -> SPE workspace
/metrics              -> Scoreboard
```
Top bar has a persona toggle ("Viewing as: Applicant / HDAB Staff") so the video can cut between them in one click. Both views live in one app; no real auth.

---

## 2. Screen-by-screen spec

### 2.0 Global shell
```
+--------------------------------------------------------------------------------+
| [shield] EHDS Gatekeeper   Health Data Access Body · Austria (demo)            |
|          Applicant | Staff console | SPE | Metrics        [Viewing as: Staff v] |
+--------------------------------------------------------------------------------+
| (page)                                                                         |
+--------------------------------------------------------------------------------+
| Synthetic data only · 20,000 patients · 839 opted out, excluded everywhere · Reg. (EU) 2025/327 |
```
The footer is always visible and states the privacy facts (opted-out count, synthetic data). It keeps repeating them for the jury.

### 2.1 (a) Applicant portal: Submit `/apply`

```
+-------------------------------------------+------------------------------------+
| Submit a request                          |  What happens next                 |
| [ Sample requests v ] R01 Diabetes...     |  1 Purpose check (Art. 54)         |
|                                           |  2 Request type (Art. 69 / 67)     |
| Tabs: [ Paste JSON ] [ Upload ] [ Form ]  |  3 Your definitions -> query plan  |
| +---------------------------------------+ |  4 Privacy checks (small cells)    |
| | { "id": "R01", "applicant": {...},    | |  5 Decision letter                 |
| |   "requested_as": "health data ...",  | |                                    |
| |   ...                                 | |  Typical time: < 30 s              |
| +---------------------------------------+ |                                    |
| JSON valid ✓  requested_as: statistics    |                                    |
|                         [ Submit request ]|                                    |
+-------------------------------------------+------------------------------------+
```
Components:
- `SamplePicker`: a Select listing R01–R10, C01, C02, each showing its id, organisation and a small "expected" hint visible only in staff mode. Picking one fills the editor.
- `JsonEditor`: a plain `<Textarea>` in a mono font with live `JSON.parse` validation. No Monaco, because it's too slow to set up.
- `UploadDrop`: an `<input type=file accept=.json>` that fills the editor.
- `RequestForm` (Form tab): name, organisation, country, a `requested_as` radio, purpose, question, and a definitions list (add/remove rows). It serialises to the same JSON. **Cut-line item.**
- On submit: `POST /api/requests`, then navigate to `/apply/:id`.

### 2.2 (a) Applicant portal: Status + Decision letter `/apply/:id`

```
+--------------------------------------------------------------------------------+
| Request R02 · Alpenland Versicherung AG · submitted 18:40                      |
| (o)Received -(o)Purpose check -(x)Decision          [ REJECTED ]  4.2 s         |
+--------------------------------------------------------------------------------+
| Dear Markus Gruber,                                                            |
| Your request has been REJECTED.                                                |
|                                                                                |
| Why: You want to use health data to set private insurance premiums for         |
| people with diabetes. The EHDS forbids using health data to make decisions     |
| that exclude people from insurance or change their premiums.                   |
|                                                                                |
| The law  > Art. 54(1)(b) ... [quoted text, expandable]                         |
|                                                                                |
| What you can do instead                                                        |
|  • Use published, aggregated risk statistics from Statistik Austria.           |
|  • Research on diabetes outcomes for prevention is allowed (Art. 53) if it      |
|    doesn't feed into pricing individuals.                                       |
|                                                                                |
| Your right to appeal: contact the HDAB within ... [placeholder]                 |
| Reference: HDAB-2026-R02 · decided automatically · reviewed by: pending         |
+--------------------------------------------------------------------------------+
```
For APPROVE_STATISTICAL the letter body is followed by the **results table** (same `ResultsTable` component as staff) plus a "Small numbers hidden to protect privacy" legend. For APPROVE_SPE it shows a "Your data permit" card with the cohort size, the record types, an "Open secure workspace" button that goes to `/spe/:id`, and the permit conditions (no download, only aggregate exports after review).

For **R09 downgrade** a yellow info callout sits above the table: *"You asked for patient records. Your question can be fully answered with statistics, so under the data-minimisation principle (Art. 66) we approved statistics instead. Here they are. If you need records, explain why aggregates are not enough."*

Components: `PipelineStepper` (compact), `DecisionBadge`, `DecisionLetter`, `ArticleQuote` (accordion), `AlternativesList`, `ResultsTable`, `PermitCard`.

### 2.3 (b) Staff console: Queue `/staff`

```
+--------------------------------------------------------------------------------+
| Request queue                  [Run all samples]  Filter: [All v] [Needs review]|
| KPIs: 12 requests · 4 rejected · 6 stats · 1 SPE · 1 needs review · avg 7.9 s   |
+----+------------------+------------------------+--------------+------+--------+
| ID | Applicant        | Purpose (short)        | Decision     | Flags| Time   |
+----+------------------+------------------------+--------------+------+--------+
| R01| Danube Inst. (AT)| T2D regional prevention| APPROVED·STAT|      | 6.1 s  |
| R02| Alpenland Vers.  | Insurance premiums     | REJECTED     |      | 2.3 s  |
| R05| GlucoSense       | Train prediction model | APPROVED·SPE |      | 9.8 s  |
| R08| Cancer Centre(IT)| BMI & breast cancer    | APPROVED·STAT| 5 sup| 7.2 s  |
| R09| Inst. Gen. Pract.| ACE/ARB teaching       | STAT (downgr)| ↓    | 8.0 s  |
| C03| ???              | ...                    | NEEDS REVIEW | ⚠ diff| ...   |
+----+------------------+------------------------+--------------+------+--------+
```
- Rows are clickable and go to the detail page. Rows still in flight show a mini spinner and the current step name.
- Flag icons, each with a Tooltip: `↓ downgraded`, `5 sup` (cells suppressed), `⚠ differencing risk`, `✎ overridden`, `LLM low confidence`.
- "Run all samples" calls `POST /api/requests/batch {ids:[...]}`. It looks great in the video because 10 rows fill in live.

### 2.4 (b) Staff console: Request detail `/staff/requests/:id`

```
+--------------------------------------------------------------------------------+
| R08 · Prof. Elena Rossi · Comprehensive Cancer Centre (IT)   [APPROVED · STATS] |
| Received ✓ ─ Purpose ✓ ─ Plan ✓ ─ Query ✓ ─ Privacy ✓ ─ Decision ✓   7.2 s      |
+-------------------------------------+------------------------------------------+
| Tabs: [Decision] [Query plan] [Results] [Privacy] [Audit]                       |
+--------------------------------------------------------------------------------+
| DECISION tab                         | STAFF ACTIONS                           |
|  Decision: APPROVE_STATISTICAL       |  [ Confirm & release ]                  |
|  Purpose class: scientific research  |  [ Override decision v ]  -> Dialog     |
|   (LLM, conf 0.97) + rule: no Art.54 |  [ Request clarification ]              |
|   keyword hit                        |  Note: [______________]                 |
|  Reasoning (rule trace):             |                                          |
|   1. Prohibited purpose? NO          |  Applicant sees: [Preview letter ->]    |
|   2. requested_as = statistics -> 69 |                                          |
|  Articles                            |                                          |
|   [Art. 53] [Art. 69]  (click = quote)|                                         |
+-------------------------------------+------------------------------------------+
```

**Query plan tab.** The plan is rendered in English, not JSON. JSON sits behind a "Show raw plan / SQL" toggle.
```
Population     All patients, excluding 839 opted out
Filter         sex = female                              <- "Women = sex 'female'"
Cohort         has condition ICD-10 C50*  (Breast cancer) <- "Breast cancer = ... C50"
Measure        latest observation LOINC 39156-5 (BMI) per patient; drop missing
Group by       region (all 9 regions, empty groups shown)
Output         count(patients) · mean(BMI) 1 dp, half-up
Catalog matches  C50 ✓ in ICD-10 catalog · 39156-5 ✓ in LOINC catalog
[ Show raw plan JSON ]  [ Show compiled SQL ]
```
Each plan line links back to the definition sentence it came from (hover highlights the source sentence). **This is our "AI helps, AI doesn't compute" proof. Show it in the video.**

**Results tab:** `ResultsTable`, see section 4.4 for cell rendering. A legend sits above the table with a "Show raw (staff only, never released)" toggle. **Decision: no raw toggle.** Staff should never see unsuppressed numbers in the UI either. Say so in the pitch: "Even staff can't see small cells." That's a stronger privacy story.

**Privacy tab:** a checklist with green ticks and the numbers.
```
✓ Opted-out patients excluded           839 removed before any query
✓ Small-cell rule                       5 counts shown as <10, 5 means suppressed
✓ No patient-level fields in output     columns: region, count, mean
✓ All requested groups present          9 / 9 regions
✓ Rounding                              half-up, 1 decimal
✓ Differencing guard                    no overlapping prior queries by this applicant
   (or) ⚠ Overlap with R08-v1: differ by 1 filter → secondary suppression applied to 2 cells
```

**Audit tab:** a vertical timeline, newest at the bottom.
```
18:40:01.120  request.received        applicant=Markus Gruber
18:40:01.410  purpose.classified      insurance_pricing (LLM conf 0.99) + rule hit "premium"
18:40:01.412  decision.made           REJECT · Art. 54        actor=system
18:41:30.000  decision.overridden     -> ...                  actor=staff:anna  note="..."
```

**Override dialog:** a Select for the new decision, multi-select articles, a required justification textarea, and a Confirm button. The audit entry appears immediately (optimistic update). Overrides never silently reveal suppressed cells.

Components: `RequestHeader`, `PipelineStepper` (full), `DecisionPanel`, `RuleTrace`, `ArticleChip` + `ArticleQuoteSheet` (side Sheet with quoted text), `QueryPlanView`, `RawToggle`, `ResultsTable`, `PrivacyChecklist`, `AuditTimeline`, `OverrideDialog`, `StaffActions`.

### 2.5 (c) SPE workspace `/spe/:workspaceId`

```
+--------------------------------------------------------------------------------+
| 🔒 Secure Processing Environment · Workspace spe_R05 · Permit HDAB-2026-R05      |
| Holder: GlucoSense · Valid until 2027-10-29 · Art. 68 permit · Art. 73 SPE       |
+------------------------+-------------------------------------------------------+
| COHORT                 | Tables in this workspace (schema spe_r05)              |
|  1,152 patients        |  ▸ patients        1,152 rows   pseudonymised IDs       |
|  adults · E11* · ≥1    |  ▸ conditions      xx,xxx rows                          |
|  HbA1c (4548-4)        |  ▸ medications     xx,xxx rows                          |
| Record types copied    |  ▸ observations    x,xxx rows (LOINC 4548-4 only)       |
|  ✓ conditions          |  ✗ encounters      not requested, not copied            |
|  ✓ medications         |                                                         |
|  ✓ HbA1c observations  |  Preview (first 5 rows, inside SPE only) [table]        |
|  ✗ encounters          |                                                         |
+------------------------+-------------------------------------------------------+
|  [ ⬇ Download dataset (CSV) ]   [ ⬇ Export model weights → request review ]       |
+--------------------------------------------------------------------------------+
```
**The blocked download moment (dramatic, about 3 s on video):**
1. Click "Download dataset". The button shows a spinner for 400 ms while it really calls `GET /api/spe/:id/download`.
2. The server returns **403**. The whole workspace card gets a red 2px border and a framer-motion shake (x: [0,-8,8,-6,6,0], 400 ms). A full-width red banner drops in:
   `⛔ DOWNLOAD BLOCKED · HTTP 403 · Art. 73: data in a secure processing environment may not be downloaded. This attempt has been logged.`
3. The audit entry `spe.download_blocked actor=GlucoSense ip=...` slides into a mini audit panel on the right. A toast says "Incident logged to HDAB audit trail".
4. Optional: a counter, "Blocked attempts: 1".

The preview table shows pseudonymised IDs only, and it exists only to prove the records really are in there. The "Export model weights" button opens a dialog: "Exports require HDAB output review (Art. 73). Request submitted." This matches the R05 applicant's own statement that they'll export weights only.

### 2.6 (d) Metrics scoreboard `/metrics`

```
+--------------------------------------------------------------------------------+
| Metrics · evaluated against requests/expected.json      [ ▶ Run all 10 × 3 ]    |
+-----------+-----------+-------------+-------------+--------------+-------------+
| Decisions | Numbers   | Privacy     | Consistency | Slowest      | Custom tests|
|  10 / 10  |  6 / 6    |  0 leaks    |  10 / 10    |  11.4 s <60s | 2 / 2 run   |
+-----------+-----------+-------------+-------------+--------------+-------------+
| Req | Expected        | Run 1 | Run 2 | Run 3 | Articles ✓ | Numbers ✓ | max t  |
| R01 | APPROVE_STAT    |  ✓    |  ✓    |  ✓    | 53,69 ✓    | 27/27 ✓   | 6.1 s  |
| R02 | REJECT          |  ✓    |  ✓    |  ✓    | 54 ✓       | n/a       | 2.3 s  |
| ... |                 |       |       |       |            |           |        |
+-----+-----------------+-------+-------+-------+------------+-----------+--------+
| [timing bar chart: per-request max seconds, 60 s threshold line]                 |
| Custom: C01 (inpatient by hospital), C02 (by primary_icd10) -> decision + values |
+--------------------------------------------------------------------------------+
```
- The run cells fill in live (poll `GET /api/metrics/runs/:runId`). Big numbers count up with framer-motion when they finish.
- Clicking a ✗ cell opens a diff view (expected vs got). It's honest and it helps us debug.
- Metric tiles turn green when they hit target and amber otherwise. No red unless it's a privacy leak (>0 leaks is the only red).
- This is the slide-4 screenshot and the video's closing shot.

---

## 3. API contract (backend dev: match these shapes)

Base: `http://localhost:8000/api`. CORS allows `http://localhost:5173`. All timestamps are ISO-8601. Enums:
```
Decision     = "REJECT" | "APPROVE_STATISTICAL" | "APPROVE_SPE" | "NEEDS_REVIEW"
Status       = "received" | "processing" | "decided" | "released" | "error"
StepKey      = "received" | "purpose" | "plan" | "query" | "privacy" | "decision"
StepState    = "pending" | "running" | "done" | "failed" | "skipped"
```

### 3.1 Requests
`POST /requests`  body = the raw request JSON exactly as in `requests/R01.json` (an `id` is optional, and the server assigns one if missing). Processing starts async (BackgroundTasks).
```json
→ 202 { "id": "R01", "status": "processing" }
→ 422 { "detail": "requested_as must be 'health data request' or 'health data access application'" }
```

`POST /requests/batch`  `{ "ids": ["R01", "...", "R10"] }` loads the samples from disk and submits them all. Returns `{ "ids": [...] }`.

`GET /samples` returns `[{ "id": "R01", "organisation": "...", "requested_as": "...", "json": {…} }]` for the sample picker (R01–R10 + C01, C02).

`GET /requests` (queue)
```json
[{
  "id": "R08", "submitted": "...", "status": "decided",
  "applicant": { "name": "Prof. Elena Rossi", "organisation": "Comprehensive Cancer Centre, epidemiology group", "country": "IT" },
  "requested_as": "health data request",
  "purpose_short": "BMI as breast cancer risk factor",
  "decision": "APPROVE_STATISTICAL",
  "articles": ["53","69"],
  "flags": { "downgraded": false, "suppressed_cells": 10, "differencing_risk": false, "overridden": false, "low_confidence": false },
  "current_step": "decision",
  "elapsed_ms": 7210
}]
```

`GET /requests/{id}` (the detail page; this one object powers the applicant letter too)
```json
{
  "id": "R08",
  "request": { "...raw request json..." : "" },
  "status": "decided",
  "elapsed_ms": 7210,
  "steps": [
    { "key": "received", "label": "Received",      "state": "done", "ms": 3 },
    { "key": "purpose",  "label": "Purpose check", "state": "done", "ms": 1840, "detail": "scientific_research" },
    { "key": "plan",     "label": "Query plan",    "state": "done", "ms": 3900 },
    { "key": "query",    "label": "Query",         "state": "done", "ms": 120 },
    { "key": "privacy",  "label": "Privacy",       "state": "done", "ms": 4 },
    { "key": "decision", "label": "Decision",      "state": "done", "ms": 1 }
  ],
  "decision": {
    "outcome": "APPROVE_STATISTICAL",
    "articles": ["53","69"],
    "downgraded_from": null,
    "purpose": { "category": "scientific_research", "allowed": true, "confidence": 0.97, "source": "llm+rules", "rule_hits": [] },
    "rule_trace": [
      { "step": 1, "question": "Is the purpose prohibited (Art. 54)?", "answer": "No", "article": "54" },
      { "step": 2, "question": "Is this a health data request?", "answer": "Yes → statistics", "article": "69" }
    ],
    "reason_staff": "Research is an allowed purpose (Art. 53). Statistics answer the question (Art. 69). Small cells are suppressed.",
    "letter": {
      "greeting": "Dear Prof. Rossi,",
      "headline": "Your request has been approved. Here are your statistics.",
      "why": "Plain-language paragraph…",
      "alternatives": ["…"],
      "next_steps": ["…"]
    },
    "needs_review": false
  },
  "plan": {
    "readable": [
      { "label": "Population", "text": "All patients, excluding opted-out", "source_definition": null },
      { "label": "Filter", "text": "sex = female", "source_definition": 1 },
      { "label": "Cohort", "text": "condition ICD-10 starts with C50 (Breast cancer)", "source_definition": 0 },
      { "label": "Measure", "text": "latest LOINC 39156-5 (BMI) per patient, missing dropped", "source_definition": 2 },
      { "label": "Group by", "text": "region (9 groups, empty shown)", "source_definition": 3 },
      { "label": "Output", "text": "count, mean BMI (1 dp, half-up)", "source_definition": 3 }
    ],
    "catalog_matches": [ { "system": "ICD-10", "code": "C50", "label": "Breast cancer", "ok": true },
                         { "system": "LOINC", "code": "39156-5", "label": "BMI", "ok": true } ],
    "raw": { "...validated plan json...": "" },
    "sql": "SELECT …"
  },
  "result": {
    "kind": "table",
    "group_by": ["region"],
    "columns": [
      { "key": "region", "label": "Region", "type": "group" },
      { "key": "women_with_bmi", "label": "Women with BMI", "type": "count" },
      { "key": "mean_bmi", "label": "Mean BMI", "type": "mean", "unit": "kg/m²" }
    ],
    "rows": [
      { "region": "Burgenland", "women_with_bmi": { "value": null, "display": "<10", "suppressed": "small_count" },
                                "mean_bmi":       { "value": null, "display": "suppressed", "suppressed": "small_n" } },
      { "region": "Wien",       "women_with_bmi": { "value": 14, "display": "14" },
                                "mean_bmi":       { "value": 26.6, "display": "26.6" } }
    ],
    "answer": { "Burgenland": { "women_with_bmi": "<10", "mean_bmi": "suppressed" }, "Wien": { "women_with_bmi": 14, "mean_bmi": 26.6 } }
  },
  "privacy": {
    "opted_out_excluded": 839,
    "checks": [
      { "key": "opt_out", "label": "Opted-out patients excluded", "passed": true, "detail": "839 removed" },
      { "key": "small_cell", "label": "Small-cell rule", "passed": true, "detail": "5 counts <10, 5 means suppressed" },
      { "key": "no_patient_level", "label": "No patient-level fields", "passed": true },
      { "key": "all_groups", "label": "All requested groups present", "passed": true, "detail": "9/9" },
      { "key": "differencing", "label": "Differencing guard", "passed": true, "detail": "no overlap" }
    ]
  },
  "spe": null,
  "audit": [
    { "ts": "...", "event": "request.received", "actor": "applicant", "detail": "..." }
  ]
}
```
Notes:
- `display` is computed **server-side**. The UI never formats or rounds a number, so there's exactly one source of truth. Keep the trailing zero: "7.0", not "7".
- Suppressed cells send `value: null`. The real number never reaches the browser. Say this in the pitch.
- `result.answer` is the flat shape the metrics script compares against `expected.json`.
- For REJECT: `plan`, `result` = null (we don't even compute). The stepper shows plan/query/privacy as `skipped`.
- For APPROVE_SPE: `result` = `{ "kind": "cohort", "cohort_size": 1152 }` and `spe` is filled (see 3.3).

`POST /requests/{id}/override`
```json
{ "decision": "APPROVE_STATISTICAL", "articles": ["53","69"], "note": "Clarified purpose with applicant by phone", "actor": "staff:anna" }
→ 200 { ...updated request detail... }   // appends audit "decision.overridden"
```
`POST /requests/{id}/release` `{ "actor": "staff:anna" }` sets status → `released` and appends audit.

`GET /articles` returns `{ "53": { "title": "Purposes for which electronic health data can be processed for secondary use", "summary": "plain English", "quote": "verbatim excerpt", "url": "https://eur-lex.europa.eu/eli/reg/2025/327/oj/eng" }, "54": {…}, "66": {…}, "67": {…}, "68": {…}, "69": {…}, "73": {…} }`
**Someone copies the verbatim quotes from EUR-Lex tonight (Chapter IV). Don't let the LLM paraphrase them as "quotes".** Store them in `backend/law/articles.json`. Working titles to verify: 53 permitted purposes; 54 prohibited secondary use; 66 data minimisation and purpose limitation; 67 data access applications; 68 data permits; 69 health data requests; 73 secure processing environment.

### 3.2 Live progress
Polling is enough: `GET /requests/{id}` every 500 ms while `status=processing` (react-query `refetchInterval: s => s==='processing' ? 500 : false`).
**Backend:** update `steps[].state` as each stage completes. Also add a **minimum 250 ms per step** visual hold on the frontend (not backend), so fast steps don't flash by invisibly in the video.

### 3.3 SPE
`GET /spe/{workspaceId}` (workspaceId = `spe_R05`)
```json
{
  "id": "spe_R05", "request_id": "R05", "schema": "spe_r05",
  "permit": { "number": "HDAB-2026-R05", "holder": "GlucoSense", "valid_until": "2027-10-29", "articles": ["68","73"] },
  "cohort_size": 1152,
  "cohort_definition": "Adults (≥18 on 2025-12-31) with ICD-10 E11* and ≥1 HbA1c (LOINC 4548-4)",
  "tables": [
    { "name": "patients",     "rows": 1152, "copied": true },
    { "name": "conditions",   "rows": 0, "copied": true },
    { "name": "medications",  "rows": 0, "copied": true },
    { "name": "observations", "rows": 0, "copied": true, "note": "HbA1c only" },
    { "name": "encounters",   "rows": 0, "copied": false, "note": "not requested" }
  ],
  "preview": { "table": "patients", "columns": ["patient_id","sex","birth_year","region"], "rows": [["P00123","female",1961,"Wien"]] },
  "blocked_attempts": 0
}
```
`GET /spe/{workspaceId}/download` → **always 403**
```json
{ "error": "download_blocked", "article": "73", "message": "Data in a secure processing environment cannot be downloaded.", "audit_id": "aud_123", "blocked_attempts": 1 }
```
`POST /spe/{workspaceId}/export-request` `{ "artifact": "model_weights" }` → `{ "status": "pending_review" }`

### 3.4 Metrics
`POST /metrics/run` `{ "runs": 3, "include_custom": true }` → `{ "run_id": "m_001" }`
`GET /metrics/runs/{run_id}`
```json
{
  "status": "running",
  "summary": { "decisions_correct": 10, "decisions_total": 10, "numbers_correct": 6, "numbers_total": 6,
               "privacy_leaks": 0, "consistent": 10, "consistent_total": 10, "slowest_ms": 11400, "threshold_ms": 60000 },
  "rows": [
    { "id": "R01", "expected": "APPROVE_STATISTICAL", "runs": [
        { "decision": "APPROVE_STATISTICAL", "articles_ok": true, "numbers_ok": true, "leaks": 0, "ms": 6100 }, {…}, {…} ],
      "consistent": true, "values_matched": 27, "values_total": 27, "diff": [] }
  ],
  "custom": [ { "id": "C01", "decision": "APPROVE_STATISTICAL", "ms": 7000, "answer": {…} } ]
}
```
The same logic should exist as a CLI (`python -m gatekeeper.eval`) that writes `metrics.json` for the README. The endpoint just calls it.

---

## 4. Visual design system

### 4.1 Palette: "Archive & Ink" (not EU-flag blue + yellow stars, not hospital mint)
A calm institutional look: deep ink navy, warm paper neutrals, one accent. It should feel like a well-run public registry, not a startup.

| Token | Light | Dark | Use |
|---|---|---|---|
| `--bg` | `#F7F5F0` (warm paper) | `#0F1419` | page |
| `--surface` | `#FFFFFF` | `#161D24` | cards |
| `--ink` | `#14213D` (ink navy) | `#E6E9EE` | text, primary buttons |
| `--muted` | `#5B6473` | `#9AA4B2` | secondary text |
| `--line` | `#E4E0D6` | `#26303B` | borders |
| `--accent` | `#2F5D8A` (registry blue) | `#7FA7D1` | links, active step, focus ring |
| `--gold` | `#B8892B` (seal gold, use sparingly) | `#D6AE5A` | article chips, permit seal |

Decision colours (badge = tinted bg + strong text + icon; never colour alone):
| Decision | BG | Text/Border | Icon | Label |
|---|---|---|---|---|
| REJECT | `#FBE9E7` | `#B3261E` | `ShieldX` | **Rejected · Art. 54** |
| APPROVE_STATISTICAL | `#E6F2EC` | `#1E6B4A` | `BarChart3` | **Approved · Statistics** |
| APPROVE_SPE | `#E8EEF8` | `#24508F` | `LockKeyhole` | **Approved · Secure environment** |
| Downgraded (modifier) | `#FFF4DB` | `#8A5A00` | `ArrowDownRight` | "↓ from records" suffix chip |
| NEEDS_REVIEW | `#FFF4DB` | `#8A5A00` | `UserCheck` | **Needs human review** |

Dark mode: **ship it only if it's free** (shadcn `class` strategy with tokens above). Record the video in **light mode**, because it reads better compressed and projected.

### 4.2 Typography (Google Fonts)
- **UI / body:** `Inter Tight` (600 for headings, 400/500 body). It's denser than Inter, so tables fit.
- **Decision letter:** `Source Serif 4` (400, 600). The letter should read like an official letter, and the serif/sans contrast instantly tells "letter to a human" apart from "staff tooling".
- **Codes, plan, SQL, IDs, numbers in tables:** `JetBrains Mono` 400/500 with `font-variant-numeric: tabular-nums`.
Scale: 12 / 14 (base) / 16 / 20 / 28 / 40 (scoreboard numbers). Line height 1.5 for body and 1.65 for the letter.

### 4.3 Components look
- Cards: 12px radius, 1px `--line` border, no heavy shadows (one `shadow-sm` max).
- Article chips: `Art. 54` in mono, gold 1px border, and a hover Tooltip with the title. Clicking opens a side Sheet with the verbatim quote in serif, with a left gold rule like a blockquote.
- Tables: zebra off, 44px rows, right-aligned numbers, sticky header, group column in medium weight.

### 4.4 Rendering `<10` and `suppressed`
They must not look like errors or missing data. They should look deliberately protected.
- `<10` cell: mono text `<10` in `--muted` on a **diagonal-hatch background** (`repeating-linear-gradient(135deg, transparent 0 4px, rgba(20,33,61,.06) 4px 5px)`), plus a tiny `Lock` icon (12px). Tooltip: "Fewer than 10 patients. Exact number hidden to prevent re-identification."
- `suppressed` cell: same hatch, with the text `suppressed` in small caps in italic muted. Tooltip: "Based on fewer than 10 patients, so not reliable or safe to show."
- Secondary suppression (differencing guard): the same hatch in amber with a `GitCompare` icon. Tooltip: "Hidden because combined with your earlier query it could reveal a small group."
- A legend row above the table: `[hatch] Protected by small-cell rule · 10 cells protected`.
- Empty groups (0) render as `<10` per the rules. Don't show "0" anywhere.

### 4.5 Micro-interactions (the video is the product)
1. **Pipeline stepper** (the signature element): 6 nodes, `Received → Purpose check → Plan → Query → Privacy → Decision`. The active node shows a pulsing ring (accent) and its connector line fills left to right (framer `scaleX`). A completed node becomes a filled check, and a failed one an X in red. On REJECT, plan/query/privacy collapse to grey "skipped" dashes and the decision node turns red. **That visual itself says "we didn't even touch the data."** Each node shows its ms below it in mono.
2. **Decision badge reveal:** a scale 0.9→1 plus fade, and a soft glow ring in the badge colour for 600 ms.
3. **Results table:** rows stagger in (30 ms each), and hatched cells fade in last with the lock icon "clicking" (rotate -10°→0).
4. **Query plan:** hovering a plan line highlights its source definition sentence (yellow marker sweep).
5. **SPE blocked download:** a shake, a red border pulse, a banner drop, and an audit line sliding in (see 2.5).
6. **Scoreboard:** numbers count up, and tiles flip to green with a check.
7. **Queue batch run:** rows appear one at a time with live step names. That's 10 requests racing.
Keep every animation ≤600 ms. Respect `prefers-reduced-motion`.

---

## 5. Demo video: 2:00 storyboard

Recording: 1920×1080, browser at 110% zoom, light mode, hide bookmarks bar, use Screen Studio or OBS + auto-zoom. **Pre-warm everything**: run all requests once before recording so the LLM cache is warm. Voiceover is recorded separately, by the clearest English speaker, then laid over the screen capture. Burned-in captions for the key lines. If a step is slow, cut it in edit and show the real timing number on screen (honesty: never fake numbers).

| Time | Screen | Voiceover |
|---|---|---|
| 0:00–0:08 | Title card: "EHDS Gatekeeper: an automated Health Data Access Body", subtitle "Reg. (EU) 2025/327, Chapter IV". Then cut to the staff queue, empty. | "From 2027 every EU country needs a Health Data Access Body to decide who may reuse health data. Today that review takes weeks. Gatekeeper does it in seconds, and shows its working." |
| 0:08–0:20 | Click **Run all samples**. 10 rows fill in live with step names and badges popping. | "Here are ten real-world requests: researchers, a ministry, an insurer, a marketing agency, an employer. Each one runs through the same pipeline." |
| 0:20–0:38 | Open **R01**. The stepper animates through. Query plan tab: hover "Type 2 diabetes = E11" and the plan line lights up. Results tab: 9 regions, Wien 8.1%. | "R01, diabetes prevention research: approved under Articles 53 and 69. The AI translates the English definitions into a query plan using only codes from a closed catalogue. Staff can read it line by line. Then plain code computes the numbers. The AI never touches patient data." |
| 0:38–0:52 | Open **R02**, Applicant view. The stepper skips plan/query/privacy (grey), red **Rejected · Art. 54**. Scroll the letter: "Why" and "What you can do instead". Quick cut to the R04 row badge. | "R02, an insurer wanting to price premiums: rejected under Article 54, before any data is touched. The applicant gets a plain-language letter quoting the law and what they could do instead. Marketing in R04 and nicotine in R10 are stopped the same way." |
| 0:52–1:07 | Open **R08** Results: hatched `<10` / `suppressed` cells, hover tooltip. Privacy tab: green checklist, "839 opted-out excluded". | "R08, breast cancer and BMI. Five regions have fewer than ten women, so the counts show as 'less than 10' and the means are suppressed. The real values never leave the server, not even to staff. Opted-out patients are excluded everywhere." |
| 1:07–1:20 | Open **R09**: amber "↓ downgraded from records" chip plus the applicant callout, then the table. | "R09 asked for patient records to update a teaching module. Statistics fully answer that question, so by data minimisation (Article 66) we approve statistics instead and explain why." |
| 1:20–1:38 | Open **R05**, APPROVE_SPE, then **Open secure workspace**: cohort 1,152 and the table list. Click **Download**: shake, red 403 banner, audit line. | "R05 trains a prediction model and explains why aggregates aren't enough. Approved for a secure processing environment: exactly 1,152 patients, only the record types they asked for. And downloads? Blocked, and logged." |
| 1:38–1:50 | **Metrics** page: hit Run 3×, numbers count up: 10/10, 6/6, 0 leaks, 10/10 consistent, slowest X s. | "On the ten test requests: ten of ten decisions, six of six correct answers, zero privacy leaks, identical results over three runs, every answer under [X] seconds." |
| 1:50–2:00 | Split card "Works / Doesn't yet" (text on screen as well). | "What doesn't work yet: no real identity or eIDAS login, the law quotes are limited to Chapter IV, and new definitions outside our code catalogue go to human review rather than being guessed. Gatekeeper: the AI translates, the code computes, the law decides." |

**Works / doesn't (on-screen card, edit to match reality on Friday 13:00):**
- Works: all 10 decisions and articles; 6/6 numbers; small-cell rule + opt-out; SPE copy + 403 block + audit; staff override + audit trail; arbitrary new requests (hospital / primary diagnosis); readable query plan.
- Doesn't (yet): authentication/eIDAS; real data permit workflow and fees; full-text law coverage beyond Chapter IV; terms outside the catalogue escalate to review; differencing guard is heuristic (exact-overlap only); federated mode [if not done].

Target: 1:55, leaving 5 s of buffer. Export MP4 H.264, <100 MB. Upload as unlisted YouTube **and** keep the file.

---

## 6. Live stage pitch (3–4 min, 6 slides + live demo)

Slides in Google Slides or Pitch.com, same palette/fonts as the app. One idea per slide and big type. Speaker A pitches, speaker B drives the laptop. **The demo runs on localhost with a pre-recorded video ready as fallback (on a USB stick + downloaded locally).**

1. **Hook (0:00–0:30)**: Big text: *"March 2027: every EU country must answer health data requests. Most have no tooling."* Speaker: "Under the EHDS, every member state needs a Health Data Access Body. Today a data access application can take months to review: lawyers read the purpose, statisticians write queries by hand, someone checks small cells in Excel. With the EHDS, the number of requests is going to explode." *(Keep timeline claims hedged: "applications for secondary use become applicable from 2029 for most data categories." Verify the exact date before stage and say "from 2027–2029".)*
2. **What we built (0:30–0:50)**: The six-step pipeline graphic (same as the stepper) with the line "The AI translates. The code computes. The law decides."
3. **LIVE DEMO (0:50–2:30)**, three moments only:
   - a. Paste a **new jury-style request live** (C01: inpatient stays by hospital), watch the stepper run, show the readable query plan and results. *(This proves it isn't hard-coded, which is the jury's biggest doubt.)*
   - b. Open R02: the rejection letter with Art. 54 and "what you can do instead".
   - c. R05 SPE: click Download, 403, shake. *(Let the moment breathe: pause 1 s of silence.)*
4. **Trust by design (2:30–2:55)**: Three columns. **Correct:** a closed code catalogue and deterministic SQL. **Private:** small cells never leave the server; opt-outs excluded; differencing guard; downloads blocked. **Accountable:** every decision cites the law, staff can override, and everything is audited.
5. **Results (2:55–3:15)**: The scoreboard screenshot: 10/10 · 6/6 · 0 leaks · 10/10 consistent · <X s. "Every answer in seconds instead of weeks."
6. **Ask / next (3:15–3:40)**: "Next: pilot with an HDAB on real request backlogs, eIDAS login, federated queries per data holder (already prototyped per hospital)." Close: "Gatekeeper: the access body's first reviewer, never its last." Team names + repo QR.

Key lines to memorise:
- "The AI never sees a single patient record. It only turns English into a plan we can check."
- "Small numbers never leave the server, not even for staff."
- "Rejected before the database is touched."
- "Every decision is a letter a human can understand and a trail an auditor can follow."

### Anticipated jury questions
| Q | A (≤20 s) |
|---|---|
| What if the LLM hallucinates a code? | The plan is validated against a closed catalogue of ICD-10/ATC/LOINC codes and a JSON schema. Unknown term means NEEDS_REVIEW, never a guess. The compiler is deterministic. |
| Is it consistent? Results vary with LLM temperature. | Temperature 0, the plan is cached by request hash, and the numbers come from SQL. 10/10 identical over 3 runs. |
| How do you detect prohibited purposes the LLM misses? | Rules first (Art. 54 keyword/category rules), LLM second. Both must agree to approve. Disagreement or low confidence sends it to the staff queue. We fail closed. |
| Does patient data go to the cloud LLM? | No. Only the request text is sent. Patient data stays in local DuckDB. That's allowed explicitly by the challenge and matches the EHDS spirit. |
| What about differencing attacks? | We keep each applicant's query history. Overlapping cohorts that differ by a small group trigger secondary suppression and a flag for staff. |
| Would an HDAB actually trust automation? | It's decision support with a human in the loop: auto-decisions are explained, overridable and audited. Staff review the hard 10%, not all 100%. |
| Why approve R09 as stats rather than reject? | Art. 66 data minimisation: give the least identifying form that answers the question. The applicant still gets their answer, today. |
| How is the SPE enforced beyond a 403? | A separate schema with only the selected patients and record types. The app user has no export path and every attempt is audited. In production: VDI/airgap, output review (Art. 73). |
| Scale / other countries? | Federated per data holder (prototype per hospital). The terminology catalogue is the only country-specific part. OMOP mapping is a straightforward extension. |
| Cost / speed? | ~1–2 LLM calls per request, seconds each, cents per request vs weeks of staff time. |

---

## 7. Build timeline for the UI person

### Tonight, Thu 20:00–22:00 (2h): skeleton + contracts
| Time | Task |
|---|---|
| 20:00–20:15 | Agree on section 3 contracts with the backend dev. Backend commits `mock/R01.json`, `R02`, `R05`, `R08`, `R09` detail fixtures (hand-written from `expected.json`) so the UI isn't blocked. |
| 20:15–21:00 | Lovable (or `npm create vite` + shadcn init): shell, routes, top nav, persona toggle, design tokens, fonts. Push to repo `frontend/`. |
| 21:00–21:45 | `DecisionBadge`, `ResultsTable` with hatched cells, `PipelineStepper` (static states), `DecisionLetter`, all on mock fixtures. |
| 21:45–22:00 | Staff queue table on mock data. Commit. Write down tomorrow's first 3 tasks. |
| Off-site (optional, no building): | Copy the article quotes from EUR-Lex into `articles.json` (it's research, not building, so check the rules). Draft the slides text. |

### Friday 09:00–15:00 (6h)
| Time | Task |
|---|---|
| 09:00–09:45 | Wire to the real API: `/samples`, `POST /requests`, `/requests`, `/requests/:id` polling. Stepper animates on real step states. |
| 09:45–10:45 | Staff detail tabs: Decision (rule trace, article Sheet), Query plan (readable + raw toggle), Privacy checklist, Audit timeline. |
| 10:45–11:30 | SPE workspace + blocked download animation + audit panel. |
| 11:30–12:15 | Metrics scoreboard (run 3×, live fill, count-up). Applicant submit page polish (sample picker, upload). |
| 12:15–12:45 | **Feature freeze.** Override dialog + release (if backend has them). Run C01/C02 custom requests. Fix ugly bits. |
| 12:45–13:30 | **Record the video** (screen takes 20 min, voiceover 15 min, edit 10 min). Team member 2 records VO in parallel. |
| 13:30–14:15 | README screenshots + metrics table, slides (screenshots from the app), rehearse the pitch twice. |
| 14:15–14:30 | Submit: video link, repo public, metrics. **Done by 14:30.** |
| 14:30–15:00 | Buffer only. |

### Cut-lines (drop in this order if behind)
1. **First to go:** dark mode; the Form tab (keep Paste + Upload + Sample picker); the recharts timing chart; hover-to-highlight definition sources.
2. **Then:** Override dialog (keep it as a disabled button labelled "Override (staff)" with audit shown from backend); separate applicant status page (show the letter as a tab within staff detail with a "Applicant view" label).
3. **Then:** the live polling stepper. Fall back to animating the stepper client-side after the response arrives, using real `ms` values. It still looks the same on video.
4. **Then:** scoreboard live run. Show a static scoreboard loaded from `metrics.json` produced by the CLI.
5. **Never cut:** decision badge + letter with articles; results table with hatched suppressed cells; readable query plan; SPE page with the 403 blocked download; metrics numbers on screen; "works / doesn't" in the video.

### Risks and mitigations
- **LLM latency in the live pitch:** pre-run and cache. For the live new request, have it pre-typed in a text file and paste it. If the API is slow (>15 s), say "while that runs…" and talk over the stepper.
- **Wi-Fi on stage:** cached plans mean the stored requests run offline. Keep the local video on the desktop.
- **Backend shape drift:** keep TypeScript types in `frontend/src/api/types.ts` mirroring section 3. The backend dev pings before changing any field.
