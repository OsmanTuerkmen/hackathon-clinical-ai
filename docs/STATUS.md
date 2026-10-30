# Status

Stand: 2026-10-30 · Branch track3-app · Worktree .claude/worktrees/track3-app

Die Implementierung der Tasks 1–15 und die abschließenden Prüfungen sind abgeschlossen. Die endgültige Ablage erfolgt mit dem Abschlusscommit; kein Push und kein Merge nach main.

| Bereich | Stand |
|---|---|
| Tasks 1–5 | Datenschicht, Modelle, Disclosure, Gesetzesleiter und Terminologie fertig/reviewt |
| Tasks 6–9 / M2 | Compiler, Engine, konservativer Regelparser, SPE und Pipeline/CLI fertig; M2-Befunde korrigiert |
| Task 10 | optionaler Claude-Pfad mit validiertem Cache, Codesystembindung und sicheren Fallbacks; Fake-/SDK-Schematests, kein Live-API-Nachweis |
| Tasks 11–12 / M3 | FastAPI und Applicant-/Staff-/SPE-UI fertig; M3 inklusive Initialladungs-Race nachreviewt |
| Tasks 13–14 | unabhängige stdlib-CSV-Referenz, gehärteter Drei-Lauf-Eval und zehn eigene Anträge fertig/reviewt |
| Task 15 / Abschlussreview | englisches README, Mermaid, Screenshots, Grenzen und Sicherheitsbericht aktualisiert; alle vier abschließenden Parserbefunde geschlossen |

## Geführtes Antragsformular (2026-10-30)

„+ New request“ öffnet jetzt ein fünfstufiges Formular statt des JSON-Felds. „Assess request“ erzeugt daraus das Antrags-JSON im Browser; es ist auf der Entscheidungsseite unter „View request JSON“ sichtbar. Der Schalter Form/JSON bleibt für eingefügte Anträge. Keine Backend-Änderung (ADR-016).

Nachweise: 771 Python-Tests (69.18 s, EHDS_LLM=off), 133 Edge-Browserchecks, 50 Formularprüfungen, 29 Dashboardprüfungen, CSV-Referenz 14/14. Die Eval-Zahlen stehen in `eval/results.md`. Grenze: Freie Definitionszeilen laufen weiter durch den konservativen Parser und können zur manuellen Prüfung führen.

## Dashboard, Animationen und Export (2026-10-30)

Applicant zeigt jetzt eine animierte Entscheidungsleiter und ein Bento-Dashboard mit Entscheidung, Privacy-Ring, Balkendiagramm samt Metrik- und Filterwahl, Rechtsgrundlage und Records released. Gesperrte Zellen sind schraffiert. Der blockierte SPE-Download zeigt Banner, Zähler, Audit-Zeile und Toast. Freigegebene Statistik lässt sich als CSV exportieren; SPE-Datensätze bleiben gesperrt. Keine Backend-Änderung (ADR-015).

Nachweise: 739 Python-Tests (59.44 s, EHDS_LLM=off), 133 Edge-Browserchecks, 29 zusätzliche Dashboard-/Export-/Animationsprüfungen, CSV-Referenz 14/14. Die Eval-Zahlen stehen in `eval/results.md`.

## Doccess-Redesign (2026-10-30)

Oberfläche unter dem Namen Doccess neu gestaltet (Richtung J Compliance, ADR-014): Sidebar mit Inbox und Suche, Entscheidungsleiter neben den Ergebnissen, Staff mit Abschnittsnavigation, klar abgegrenzter SPE-Arbeitsbereich, Desktop und 375 px. Nur `web/` und `tests/test_web.py` geändert. Unabhängiger UI-Review: Textausgabe, Raceguards, Manual-Review-Gate und Requests unverändert; alle relevanten Befunde behoben.

Frische Nachweise nach dem Redesign: 714 Python-Tests bestanden (62.94 s, EHDS_LLM=off), 133 Edge-Browserchecks, CSV-Referenz 14/14. Die Eval-Zahlen stehen in `eval/results.md`.

## Frische Nachweise nach allen Korrekturen (vor dem Redesign)

- Volle Python-Suite: 702 passed in 82.69 s unter EHDS_LLM=off, Exit 0.
- Unabhängige CSV-Referenz: 14/14 (sechs Originale, acht genehmigte Extras), Exit 0.
- Echte Evaluation: 60 TestClient-POSTs, jeder der 20 Anträge dreimal; LLM off, API-Key None; ursprüngliche und Extra-SPEs mit unabhängigem Schema-/Record-/Multiplizitätsaudit.
- Reale Edge-Browserprüfung: 133 Checks; alle acht UI-Matrixfälle in Applicant/Staff bei Desktop und375px, beide SPEs mit Vorschaugrenze, HTTP403 und Audit, Init-Race/XSS; keine unerwarteten Netzwerkfehler, externen Requests oder JS-Fehler.
- Finaler scoped Funktionsnachreview: alle vier ursprünglichen Befunde behoben, einschließlich sechs nicht umgehbarer Gruppierungspfade mit breiterer Fake-LLM-Spec.
- Abschließender statischer Sicherheitsnachreview: keine neue qualifizierte High-/Medium-Schwachstelle; Grenzen und zunächst funktional gefundene Fehler in docs/SECURITY_REVIEW.md ausdrücklich dokumentiert.

| Metrik | Originale | Extras | Ziel |
|---|---:|---:|---|
| Entscheidungen/Artikel | 10/10 | 10/10 | alle korrekt |
| Zahlen | 6/6 | 8/8 | alle genehmigten Fälle |
| Privacy leaks, alle Läufe | 0 | 0 | 0 |
| Applicant-Konsistenz | 10/10 | 10/10 | identisch über drei Läufe |
| Langsamster HTTP-Lauf | 0.909 s | 0.246 s | <60s |

R05:1152 Patienten, nur angeforderte Recordtypen und HbA1c; N06:294 Patienten, ausschließlich encounters+cohort. N07 zeigt alle342 Gruppen mit unterdrückten Counts. Stats/SPE werden bei unaufgelöstem Scope nicht freigegeben; eine verpflichtende Staff-Prüfung lässt sich weder durch LLM noch Cache aufheben.

## Demo und Grenzen

Frisch gestarteter eigener Server: http://127.0.0.1:62499, Session3889, PID8808, EHDS_LLM=off, var/task12-browser. Screenshots unter docs/img/ zeigen ausschließlich anonymisierte R01-Statistik. Start alternativ im Worktree: .venv/Scripts/python -m ehds_desk serve.

Lokale synthetische Demo, keine echte Auth oder gehärtete SPE, keine sekundäre Unterdrückung. Konservativer englischer Parser und bekannte Art54-Regex-Verneinungsgrenzen; kein Live-Claude-Nachweis. Vollständige Grenzen im README. Videoaufnahme, öffentliche Freigabe, Push und Merge bleiben beim Nutzer.
