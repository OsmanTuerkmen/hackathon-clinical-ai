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
| M3 – Task 12: Web-UI | fertig, Applicant/Staff/SPE, 57 echte Browserchecks (Desktop/375 px), Taskreview und M3-Review Approved; Initialladungs-Race behoben |
| M4 – Task 13: Referenz und Eval | fertig, unabhängige CSV-Kontrolle, Prüfer separat reviewt und korrigiert |
| M4 – Tasks 14–15: eigene Anträge und Abschluss | offen |

Tests: `.venv/Scripts/python -m pytest -q` → 594 passed in 46.53s (2026-10-30, nach Task 13 und Reviewkorrektur); UI zusätzlich 57 Browserchecks.
Übergabe für die Weiterarbeit: `docs/HANDOFF.md`.
Verifizierter Kernlauf (Task 13): Entscheidungen 10/10, Zahlen 6/6, Privacy 0 über 30 Antworten, Konsistenz 10/10, langsamster POST 0.506 s; unabhängige CSV-Referenz 6/6. SPE-Spaltenvertrag und Zeilenmultiplizität sind unabhängig geprüft; Nachreview ohne Restbefund. Eigene Anträge sind noch offen.
