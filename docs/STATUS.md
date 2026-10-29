# Status

Stand: 2026-10-29 · Branch `track3-app` (Worktree `.claude/worktrees/track3-app`)

| Bereich | Stand |
|---|---|
| Spec und Plan | fertig (`docs/superpowers/`) |
| M1 – Task 1: Gerüst, Konfiguration, Datenschicht | fertig, reviewt (Opt-out-Views, Settings ohne `.env` in Tests) |
| M1 – Task 2: Modelle (QuerySpec, Raw-Zellen, Decision) | fertig, reviewt |
| M1 – Task 3: Disclosure (Small-Cell, ROUND_HALF_UP, Leak-Guard) | fertig, reviewt |
| M1 – Task 4: Gesetzeskatalog, Entscheidungsleiter | fertig, reviewt; R01–R10 entscheiden wie `expected.json` |
| M1 – Task 5: Terminologie (Lexikon + Datenabgleich) | fertig, reviewt |
| M2: Compiler/Engine, Regelparser, SPE, Pipeline | offen |
| M3: LLM-Pfad, API, Web-UI | offen |
| M4: Referenz, Eval, eigene Anträge, README | offen |

Tests: `.venv/Scripts/python -m pytest -q` → 147 passed (Stand nach Task 5).
Eval-Metriken: noch nicht messbar (Eval in M4).
