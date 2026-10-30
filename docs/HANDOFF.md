# Übergabe (Stand 2026-10-30, Codex-Fortsetzung)

Verbindlicher Auftrag: docs/PROMPT_track3.md; Design und Plan unter docs/superpowers/. Aktueller Fortschritt: docs/STATUS.md, docs/TODO.md, docs/WORKLOG.md und lokales Ledger .superpowers/sdd/2026-10-29-ehds-access-desk/progress.md.

## Arbeitsort und harte Regeln

- Worktree: C:/Users/BüsraTürkmen/Documents/Hackathon/hackathon-clinical-ai/.claude/worktrees/track3-app, Branch track3-app.
- Hauptrepo und Track-1-Branch/Worktree nicht verändern. Kein Push und kein Merge ohne ausdrückliche Nutzerfreigabe.
- Originaldaten bleiben außerhalb: C:/Users/BüsraTürkmen/Documents/Hackathon/track3. Keine CSVs, var/, .env oder DuckDB-Dateien committen; keine Patientenzeilen an externe Dienste oder in Browser-Screenshots/Toolausgaben.
- Interne Doku Deutsch; UI, README und Begründungen Englisch. TDD, separate Reviews, kleine Conventional Commits; vor jedem Commit git status und diff --check.
- In dieser Codex-Session liegt der Worktree außerhalb der Sandbox-Schreibbereiche: Writes/Git/Tests/Server via exec_command mit require_escalated. Standard-Sandbox erzeugt irreführende Git-Fehler; keine Git-Konfiguration reparieren.

## Erledigt

Tasks 1–9 bestehen wie bisher: DuckDB/Opt-out-Views, Pydantic, Disclosure, deterministische Entscheidungsleiter, Terminologie, Compiler/Engine, Regelparser, SPE und Pipeline/CLI.

M2-Review über 791dcd6..6d1e439 erneut ausgeführt. Vier Befunde mit TDD behoben und nachreviewt: spezifische measurements/observations begrenzen SPE-LOINCs; Nullbreite Altersbänder hängen nicht; Mean ignoriert keine zusätzlichen Einschränkungen; Statistik/Kohorte/Opt-out nutzen dieselbe Altersbanddomäne. Commit 80c6674, 416 Tests.

Task 10 abgeschlossen (2a63b2e): optionaler Claude-Pfad mit sicherer Text-Whitelist, Pydantic structured outputs, Cache/Revalidation, Codeprüfung und Staff-Fallback. Nach Review bindet die Validation alle elf Codepositionen an ICD-10/ATC/LOINC, auch beim Cache-Lesen. 50 gezielte Tests; volle Suite 466 passed in 31.55s. Keine echte API-Anfrage.

Task 11 abgeschlossen (3f362e6): FastAPI create_app und lazy app-Export, health/requests/process/law, SPE manifest/preview/audit/download. Download immer403 und Audit, sichere generische Fehler, Vorschau serialisiert date/Decimal; web/ wird nur bei Existenz und ausschließlich aus diesem Ordner statisch ausgeliefert. 52 API-Tests, volle Suite 518 passed in 36.10s; separater Review Approved, CLI-Importprobe bestanden.

## Aktuell / nächste Schritte

- Task 12 abgeschlossen und task-reviewt: web/index.html, app.js, styles.css; vier Smoke-Tests, volle Suite 522 passed in 36.04s, zuletzt 57 echte Browserchecks einschließlich Desktop/375 px, R05 mit 403/Audit und XSS/Race. R01-Screenshots unter docs/img/. Commit 8c38028. M3-Schnittstellenreview Approved ohne Critical/Important. Der kleine Initialladungs-Race der Inbox wurde mit Browser-TDD behoben und separat nachreviewt. Eigener Server http://127.0.0.1:62499, Session 92712, PID 16260, EHDS_LLM=off, var/task12-browser. Bei späteren Python-Änderungen eigenen Server neu starten.
- Task 13 ist implementiert und nachreviewt: unabhängige stdlib-Referenz 6/6, TestClient-Eval mit eigener Runtime unter var/eval. Task14 ist erledigt; als Nächstes Task15: unabhängige stdlib-Referenz plus Eval über TestClient (3 Läufe,5Metriken), mindestens8 eigene Anträge (Plan sieht10vor), englisches README mit Mermaid/Metriken/Grenzen, Sicherheitsprüfung und Abschluss nach PROMPT§7.
- Fertig erst bei echten Eval-Zielen: Entscheidungen10/10, Zahlen6/6, Leaks0, Konsistenz10/10, langsamsterAntrag<60s. eval/results.md belegt echte Kernziele 10/10,6/6,0,10/10,max0.506s und CSV-Referenz6/6. Der SPE-Prüfer verwendet nach Reviewkorrektur unabhängige CSV-/Vertragsspalten und Zeilenmultiplizität; 16 sichere Regressionen sowie Header-only-Probe, Nachreview ohne Restbefund. Letzte volle Suite594 passed46.53s, 72 gezielte Eval-Tests. Task14 ist ebenfalls abgeschlossen:10 neueRequests, 8 unabhängige Extra-Referenzen, insgesamt14/14 Referenzen; Kernmetriken10/10,6/6,0,10/10,max0.537s, Extrametriken10/10,8/8,0,10/10,max0.194s. Volle Suite616passed50.36s. Keine Appänderung nötig; Task14-ReviewApproved. Als NächstesTask15 README/Abschluss.

## Skills und Browser

Superpowers-Skills sind installiert unter C:/Users/BüsraTürkmen/.claude/plugins/cache/anthropic-plugin-directory/superpowers/6.4.2-8ca22dba9a94/skills/ und gelesen (using-superpowers, subagent-driven-development, TDD, systematic-debugging, requesting/receiving-code-review, verification-before-completion, using-git-worktrees). Nutzerauftrag erlaubt Subagent-Workflow; Controller pflegt Doku und Commits.

Auf ausdrücklichen Nutzerwunsch offizielle Anthropic-Quellen nach ~/.codex/skills installiert: claude-api, security-review (offizieller Command, nur YAML-name ergänzt), webapp-testing. Nutzer hat webapp-testing ausdrücklich als Ersatz für den eingebauten, nicht separat auffindbaren /run-Skill genehmigt.

Python-Playwright1.64.1 ist in der bestehenden .venv installiert. Vorhandener Browser: C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe (Chrome ebenfalls vorhanden). Headless prüfen; keine zusätzlichen Browserdownloads nötig. webapp-testing/scripts/with_server.py --help wurde gelesen. Bei Start-Process immer WindowStyle Hidden. Keine fremden Server stoppen.

## Claude-API-Fakten und Grenzen

- Offizieller Skill ~/.codex/skills/claude-api; lokal SDK anthropic2.3.0. Modell claude-opus-5-5.
- KEIN temperature, KEIN erzwungenes tool_choice. Stabile client.messages.parse(output_format=LLMTranslation, output_config={effort:medium}); SDK bereitet das Schema auf, lokale volle Validation bleibt bestehen.
- Nur requested_as/requested_format/purpose/question/definitions plus Code-Katalog ohne Zeilenzahlen. Keine IDs/Namen/Organisationen/Extras im Payload; Patient-ID-Muster verhindert Versand.
- Cache unter var/cache/llm, versionierter Hash mit Antrag/Katalog/Schema/Modell/Prompt; atomisch und erneut validiert.
- Gesamtbudget30s inklusive höchstens einer Schema-Korrekturrunde, SDK-Retries0. Ignoriert ein fremder Client den Timeout, kann sein Daemon-Thread weiterlaufen; verspätetes Ergebnis wird weder ausgeliefert noch gecacht. Kein Live-API-Nachweis.

## Befehle

.venv/Scripts/python -m pytest -q
.venv/Scripts/python -m ehds_desk decide <antrag.json> [--staff]
.venv/Scripts/python -m ehds_desk serve [--port 8000]

Bekannte Grenzen bleiben dokumentiert: keine echte Auth/SPE-Härtung, keine sekundäre Unterdrückung, konservativer englischer Parser, bekannte adversariale Verneinungsfälle in Art54-Regeln. R13: exakte SPE-Kohorten-/Tabellenzahlen sind von Small-Cell ausgenommen. Nichts pro Antrag hart codieren.

## Aktueller Nutzerauftrag zum Zwischenstand

Vor weiteren Arbeiten jetzigen Stand auf track3-app committen, dann weiterarbeiten und den finalen Teil separat committen. README/CLAUDE und Sicherheitsbericht liegen vor. Gesamt-Reviewer final_review hat zwei P1-SPE-Fälle bestätigt: negierte Recordtypen und nachgestellte Messbeschränkungen. Vollständige gebündelte Fundliste steht noch aus; danach genau eine gebündelte Fixrunde mit TDD und scoped Nachreview. Letzte frische Controllerprüfung:616 Tests51.34s, Referenz14/14, Kern10/10,6/6,0,10/10,max0.527s; Extras10/10,8/8,0,10/10,max0.202s. Werte echt, aber vor SPE-Korrektur. Kein Fertigmelden, Push oder Merge. Eigener Demo-Server62499/Session92712/PID16260 muss nach Python-Korrektur neu gestartet werden.
