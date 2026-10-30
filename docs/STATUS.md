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
| M4 – Task 14: zehn eigene Anträge | fertig, unabhängige Referenzen, Extra-Eval und separater Review |
| M4 – Task 15: README und Abschluss | offen; statischer Sicherheitsreview ohne qualifizierte High/Medium-Befunde abgeschlossen |

Tests: `.venv/Scripts/python -m pytest -q` → 616 passed in 50.36s (2026-10-30, nach Task 14); UI zusätzlich 57 Browserchecks.
Übergabe für die Weiterarbeit: `docs/HANDOFF.md`.
Verifizierter Lauf nach Task 14: Kern 10/10 Entscheidungen, 6/6 Zahlen, Privacy 0, Konsistenz 10/10, maximal 0.537 s. Zehn Extras: 10/10 Entscheidungen, 8/8 Zahlen, Privacy 0, Konsistenz 10/10, maximal 0.194 s. Je drei Läufe, insgesamt 60 POSTs; unabhängige CSV-Referenzen 14/14. N06 kopiert 294 Patienten ausschließlich als encounters+cohort; N07 zeigt alle 342 Gruppen unterdrückt. Eval-Prüfer und Extra-Fälle separat reviewt.

Zwischenstand auf Nutzerwunsch: Der abschließende Gesamt-Review hat zwei P1-SPE-Parserfälle bestätigt: ausdrücklich ausgeschlossene Recordtypen können in der Auswahl bleiben; nachgestellte Messartenbeschränkungen wie observations for HbA1c only können unbeschränkt bleiben. Die bisherigen Benchmarkwerte sind echt, decken diese Fälle aber nicht ab. Noch kein Projektabschluss. README/CLAUDE liegen als Entwurf vor; nach Korrektur folgen Regressionen, Nachreview, neuer Eval und separater finaler Commit.
