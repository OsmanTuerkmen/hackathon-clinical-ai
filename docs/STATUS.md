# Status

Stand: 2026-10-30 · Branch `track3-app` (Worktree `.claude/worktrees/track3-app`)

| Bereich | Stand |
|---|---|
| Spec und Plan | fertig (`docs/superpowers/`) |
| M1 – Task 1: Gerüst, Konfiguration, Datenschicht | fertig, reviewt (Opt-out-Views, Settings ohne `.env` in Tests) |
| M1 – Task 2: Modelle (QuerySpec, Raw-Zellen, Decision) | fertig, reviewt |
| M1 – Task 3: Disclosure (Small-Cell, ROUND_HALF_UP, Leak-Guard) | fertig, reviewt |
| M1 – Task 4: Gesetzeskatalog, Entscheidungsleiter | fertig, reviewt; R01–R10 entscheiden wie `expected.json` |
| M1 – Task 5: Terminologie (Lexikon + Datenabgleich) | fertig, reviewt |
| M2 – Task 6: Compiler/Engine | fertig, reviewt |
| M2 – Task 7: Regelparser (inkl. primary_icd10, data_holder, Klartext) | fertig, 3 Fix-Runden, reviewt |
| M2 – Task 8: SPE mit Download-Sperre und Audit | fertig, reviewt |
| M2 – Task 9: Pipeline und CLI | fertig, reviewt; Meilenstein-Review M2 abgeschlossen, vier Befunde mit Regressionstests behoben |
| M3 – Task 10: optionaler Claude-Pfad | fertig, Fake-Client-/SDK-Schematests, separat reviewt; kein Live-API-Nachweis |
| M3 – Task 11: FastAPI | fertig, 52 HTTP-Tests, separat reviewt |
| M3 – Task 12: Web-UI | offen |
| M4: Referenz, Eval, eigene Anträge, README | offen |

Tests: `.venv/Scripts/python -m pytest -q` → 518 passed in 36.10s (2026-10-30, nach Task 11).
Übergabe für die Weiterarbeit: `docs/HANDOFF.md`.
Eval-Metriken: noch nicht messbar (Eval in M4).
