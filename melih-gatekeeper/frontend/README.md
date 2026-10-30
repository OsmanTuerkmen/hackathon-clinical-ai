# EHDS Gatekeeper · Frontend

React 18 + Vite 5 + TypeScript + Tailwind 3, with hand-written shadcn-style components on Radix primitives, framer-motion, TanStack Query, React Router and lucide-react.

**Sovereignty:** the app makes no third-party requests at runtime. Fonts (Inter Tight, Source Serif 4, JetBrains Mono) are self-hosted via `@fontsource`. There are no CDNs and no analytics. The only external URLs are EUR-Lex links that the user clicks.

## Run

```bash
cd frontend
npm install
npm run dev          # http://localhost:5173, proxies /api -> http://localhost:8000
npm run dev:mock     # same, but always uses the in-browser mock (VITE_MOCK=1)
npm run build        # tsc -b && vite build -> dist/
npm run preview      # serve dist/ (no /api proxy: use ?mock=1 or VITE_API_URL)
```

Node 18+ is required (tested with Node 24). If `node` is not on your PATH: `export PATH=/opt/homebrew/bin:$PATH`.

## Backend vs mock mode

On page load, `src/api.ts` resolves a mode once:

1. `VITE_MOCK=1`, `?mock=1` or `localStorage["ehds.mode"]="mock"` → **mock**
2. `?live=1` or `localStorage["ehds.mode"]="live"` → **live** (no probe)
3. Otherwise it probes `GET /api/health`. A JSON answer means **live**; a network error, a 5xx (the Vite proxy returns one when FastAPI is down) or a timeout means **mock**.

The pill in the top bar shows the mode (**Live API** / **Mock data**). Clicking it switches modes and saves the choice. `VITE_API_URL` overrides the base URL (default `/api`).

**Mock mode** (`src/mock/engine.ts`) is a time-based in-browser implementation of every §3 endpoint:

- Decisions, articles and answers come from `track/requests/expected.json` (copied to `src/mock/data/`).
- Raw plans come from `fixtures/plans/` (also copied there).
- Readable plans, letters, rule traces, signals, Five Safes, SPE tables and audit entries are hand-written in `src/mock/content.ts`.
- Step progress is simulated from submit time, so the pipeline, the queue batch run and the metrics run all animate.
- Samples: R01–R10, plus C01 (inpatient stays by hospital), C02 (stays by primary diagnosis S72, with real numbers computed from the CSVs) and C03 (a prompt-injection attempt that is flagged NEEDS_REVIEW).
- Other pasted requests go through a small keyword heuristic and are flagged `MOCK_NO_ENGINE`.
- Article quotes in mock mode are best-effort excerpts, marked as such in the UI. The backend serves the verified EUR-Lex text.

## Screens

| Route | Screen |
|---|---|
| `/` | Landing: applicant portal or staff console |
| `/apply` | Submit: sample picker (grouped by `group`), Paste JSON, Upload, Form |
| `/apply/:id` | Status and decision letter: serif letter, article accordion, results / permit card, downgrade callout, Five Safes, appeal |
| `/staff` | Queue: KPIs, "Run all 10 samples", filters, live step names, flags |
| `/staff/requests/:id` | Detail: Decision (review reasons, signals, rule trace, Five Safes), Query plan (hover links each plan line to its definition), Results, Privacy, Audit (hash chain); override, release, data-flow panel |
| `/spe/:workspaceId` | SPE workspace: cohort, tables, preview. A blocked download shakes the card, drops a red 403 banner and adds an audit entry |
| `/metrics` | Scoreboard: run 10 × 3, count-up tiles, live run cells, timing chart, custom/adversarial list |

The persona toggle ("Applicant / HDAB Staff") switches between `/apply/:id` and `/staff/requests/:id` for the same request. Dark mode is behind the moon icon. Record the video in light mode.

## Contract notes (tolerated variations)

- `plan.readable[].source_definition`: when this is missing, the UI infers the source definition from shared codes and words and marks it `≈ def N`. An explicit `null` shows `rule`.
- `decision.purpose` or `decision.purpose_category` / `purpose_source`: either is accepted.
- `decision.signals.*.available === false`: the row renders as "Not run" and is left out of the agree/disagree vote. A quote with `quote_verified === false` is labelled as unverified.
- `request.spe` may be `{workspace_id}`, `{id}` or omitted. The workspace id falls back to `spe_<id>`.
- `metrics.custom` may be flat (`{id, decision, ms}`) or row-shaped (`{id, expected, runs[]}`). `summary.custom_correct` / `custom_total` are used when present.
- Metrics rows without `values_matched` derive it from `numbers_ok` on every run.
- The minimum visual hold per pipeline step (340 ms) is applied on the frontend. `prefers-reduced-motion` disables the animations.
