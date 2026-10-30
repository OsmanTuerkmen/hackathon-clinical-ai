# Worklog

## 2026-10-29

- Track-3-Brief, Gesetzeszusammenfassung, Ziele und Design-Spec angelegt; Umsetzungsplan geschrieben.
- Task 1: Projektgerüst (`pyproject.toml`, `.env.example`), `config.py` (Settings, Datenpfad-Suche über Vorfahren),
  `data.py` (typisierter DuckDB-Import, Views mit/ohne Opt-out), Tests, Start-Doku (CLAUDE.md, AGENTS.md, docs/).
  Review-Fix: Tests laden Settings ohne `.env` (`load_settings(env_file=None)`), Unicode-Test maschinenunabhängig.
- Task 2: Pydantic-Modelle als Schnittstellen. Review-Fix: Diskriminator `kind` ist Pflichtfeld (konsistentes
  JSON-Schema für den LLM-Pfad), Metriknamen und Dimensionen eindeutig.
- Task 3: `disclosure.py` – Small-Cell-Regel, `round_half_up`, Leak-Guard als Nachbedingung.
- Task 4: `law.py` (Art. 53/54/66–69/71/73) und `decision.py` (feste Leiter, Trace mit Belegzitaten).
  Review-Fix: Regeln greifen nur innerhalb eines Satzes; „HR“ nur als Abteilung; Abgleich nur mit Personenlisten;
  LLM-Signale können verschärfen, aber nie allein zur SPE führen.
- Task 5: `terminology.py` + Lexikon. Review-Fix: zusätzliche Synonyme („diabetes type 2“ u. a.), knappe
  Datenabgleiche und Qualifier („pulmonary hypertension“) führen zu manueller Prüfung statt falscher Codes.
- Meilenstein M1 abgeschlossen; Meilenstein-Review beauftragt.

## 2026-10-30

- Task 6: SQL-Compiler und Engine; alle erwarteten Zahlen (R01, R03, R05, R07, R08, R09, R10) auf Anhieb.
- Task 7: Regelparser; Reviews mit ~200 jury-artigen Probes, 3 Fix-Runden (Restwort-Check, Verneinungsbindung,
  Hauptdiagnose → `primary_icd10`, englische Regionsnamen). Ergebnis: 0 falsch-vollständige Probes.
- Task 8: SPE (eigene DuckDB-Datei, Manifest, Audit-Log, Download 403-Äquivalent, nebenläufigkeitssicher).
- Task 9: Pipeline `DeskService.process()` + CLI; Leak-Guard über das ganze Ergebnis. 404 Tests grün.
- Sitzung wegen Nutzungslimit beendet; Übergabe in `docs/HANDOFF.md`. Task 10 nicht begonnen, M2-Review abgebrochen.
- Codex-Fortsetzung: Baseline 404 Tests bestätigt; M2-Review über 791dcd6..6d1e439 durchgeführt. Vier Befunde behoben: SPE begrenzt spezifische measurements/observations auf die beantragten LOINCs; 0-Jahres-Altersbänder führen zu manueller Prüfung statt Endlosschleife; Mittelwerte ignorieren keine Zusatzfilter; Kohorten und Opt-out-Ausschlüsse beachten dieselbe Altersbanddomäne wie Statistiken. TDD: 9 neue Regressionen zunächst rot, abschließend 416 Tests grün; separater Review ohne offene Befunde.
- Fehlende Skills auf Nutzerwunsch aus offiziellen Anthropic-Quellen installiert: claude-api, security-review (Command als Codex-Skill mit Name-Metadatum), webapp-testing. Nutzer erlaubt webapp-testing als Ersatz für den eingebauten, nicht separat auffindbaren /run-Skill. Task 10 folgt; kein Push oder Merge.
- Task 10 abgeschlossen: Optionaler Claude-Übersetzer (Opus 5.5, messages.parse, keine temperature/tool_choice), nur freigegebener Antragstext und Codekatalog, Cache mit erneuter Validation, insgesamt 30 s Budget, sichere Staff-Fallbacks. TDD: 26 neue Fehler vor Implementierung; Review fand falsches Codesystem ohne Feldbindung; 23 weitere Regressionen zunächst rot, dann 50 gezielte Tests und Gesamtsuite 466 passed in 31.55s. Separater Nachreview Approved. Kein Live-API-Aufruf; Grenze des nicht hart abbrechbaren Fremdclient-Threads dokumentiert.
- Task 11 abgeschlossen: FastAPI mit lazy app-Export, Request-/Process-/Law-Endpunkten, SPE-Manifest/Vorschau/Audit und stets protokolliertem 403-Downloadblock; generische Leak-/Validierungsfehler, Date/Decimal-Serialisierung, statische Auslieferung ausschließlich aus optionalem web/. TDD: 52 HTTP-Tests erst rot, dann grün; volle Suite 518 passed in 36.10s. Separater Review Approved, zusätzlicher Import-/CLI-Probe bestanden. Noch kein echter Browserlauf; lokale Demo ohne Auth gemäß Scope.
- Task 12 abgeschlossen: lokale Vanilla-JS-Oberfläche mit Eingang und JSON-Anträgen, Applicant-/Staff-Tabs, nachvollziehbaren Entscheidungen und Statistiken sowie separatem SPE-Arbeitsbereich mit Vorschau, sichtbarem 403-Downloadblock und Audit. Keine externen Assets; Textknoten und Epoch/AbortController schützen vor XSS und veralteten Antworten. TDD: vier Smoke-Tests erst rot, dann grün; volle Suite 522 passed in 36.04s. Echte Edge-Headless-Prüfung auf Desktop und 375 px einschließlich R01/R05/R06/R09/R08, JSON/Manual Review/XSS/Race; nach Review-Politur Prozent-Einheit jetzt 53 Browserchecks grün. Nur anonymisierte R01-Screenshots in docs/img/. Taskreview Approved; M3-Schnittstellenreview läuft. Eigener Server auf 127.0.0.1:62499 (Session 92712, PID 16260, EHDS_LLM=off, var/task12-browser); nach späteren Python-Änderungen neu starten.
- M3-Schnittstellenreview (80c6674 bis 8c38028) Approved: LLM/Cache/Parser/Pipeline/HTTP/UI-Grenzen konsistent, keine Critical/Important-Befunde. Ein kleiner Start-Race der Inbox wurde gefunden und wird separat mit Browser-Regression korrigiert. Task 13 startet unabhängig an stdlib-Referenz und TestClient-Eval; dessen Laufzeitdaten bleiben von der Browser-SPE getrennt.
- M3-Minor behoben und scoped nachreviewt: Die initiale Inbox-Ladung überschreibt keinen begonnenen eigenen Antrag und zeigt keine verspäteten Fehlermeldungen. Regression erst rot, danach 57 Browserchecks grün, JS-Syntax geprüft; kein Backend geändert. M3-Review abschließend ohne Restbefund.
