# CLAUDE.md – Doccess (Track 3)

## Überblick

Lokale Python-Demo für EHDS-Anträge als JSON: `REJECT`, `APPROVE_STATISTICAL` oder `APPROVE_SPE` mit Artikeln und nachvollziehbarer Begründung. Statistiken werden aus 20.000 synthetischen Patienten berechnet; Applicant-, Staff- und SPE-Arbeitsbereich zeigen Entscheidung, Herleitung und nächsten Schritt. Die Kernfunktion läuft ohne LLM. Claude ist ausschließlich eine optionale Übersetzungshilfe bei unvollständigem Regelparsing.

Die Original-CSVs und R01–R10 liegen **außerhalb** des Repos unter `track3/data/` und `track3/requests/`. Nicht kopieren oder erneut klonen. Eigene Anträge N01–N10 liegen unter `requests/extra/`. README, UI und Begründungen sind Englisch; interne Projektdokumentation ist Deutsch.

## Befehle

Python >= 3.12, getestet auf 3.14. Aus Repo-/Worktree-Wurzel, Windows PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e '.[dev,llm]'
$env:EHDS_LLM = 'off'
.\.venv\Scripts\python.exe -m ehds_desk serve
# Optional anderer Port:
.\.venv\Scripts\python.exe -m ehds_desk serve --port 8001
.\.venv\Scripts\python.exe -m ehds_desk decide requests/extra/N01.json
.\.venv\Scripts\python.exe -m ehds_desk decide requests/extra/N01.json --staff
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe eval/reference.py
.\.venv\Scripts\python.exe eval/run_eval.py
```

Unix/macOS: `python3 -m venv .venv`, danach `.venv/bin/python -m pip install -e '.[dev,llm]'` und für dieselben Befehle `.venv/bin/python` verwenden; Offline-Modus mit `export EHDS_LLM=off`. Mit aktivierter venv lautet der Startbefehl `python -m ehds_desk serve`. URL: http://127.0.0.1:8000. Kein Frontend-Build nötig.

`decide` gibt Applicant-JSON aus, `--staff` den vollständigen Applicant-/Staff-Response. Originalanträge werden mit externem Dateipfad übergeben. `reference.py` akzeptiert zusätzlich `--data <track3>`. Beide Extras installieren: `dev` enthält pytest/httpx, `llm` den optionalen Anthropic-SDK für die Offline-Tests mit Fake-Clients. Kein Schlüssel und kein echter API-Aufruf sind dafür erforderlich.

`run_eval.py` sendet drei Läufe pro Original- und Extra-Antrag über FastAPI TestClient, setzt LLM explizit auf `off` und Schlüssel auf `None`, nutzt `<EHDS_VAR_DIR>/eval` und überschreibt `eval/results.md`. Referenz/Eval laden keine `.env`; bei Bedarf `TRACK3_DATA` in der Shell setzen. Aktuelle Messergebnisse und Messgrenzen stehen in `eval/results.md`, `docs/STATUS.md` und README.

## Konfiguration

App-Einstellungen kommen aus Umgebung oder lokaler `.env` (Vorlage `.env.example`; keine Secrets in andere Dateien):

- `TRACK3_DATA`: Ordner **mit** `data/` und `requests/`. Ohne Einstellung wird ab Repo-Wurzel aufwärts der erste Vorfahr mit `track3/requests/expected.json` gesucht; funktioniert auch aus `.claude/worktrees/...`.
- `EHDS_VAR_DIR`: Laufzeitwurzel, Standard `<repo>/var`; enthält SPE-Dateien, Manifeste, Audit und Cache.
- `EHDS_LLM`: `off` oder `auto` (Standard). `auto` nutzt Claude nur bei unvollständigem Regelparse und vorhandenem Schlüssel.
- `ANTHROPIC_API_KEY`: optional, ausschließlich lokal in `.env` oder Umgebung; nie in Code, URL, Antrag oder Commit.
- `EHDS_LLM_MODEL`: Standard `claude-opus-5-5`.

Vollständige Regeln lösen keinen LLM-Aufruf aus. Der reale Evaluationsnachweis ist offline; es gibt keinen Live-Claude-Nachweis. Übersetzungen werden anhand kanonischem Payload, Modell und Promptversion lokal gecacht und beim Lesen erneut validiert; kein Samplingparameter wird gesendet. 30 Sekunden Antwortbudget inklusive höchstens einer Schema-Korrektur, keine SDK-Retries. Ein fremder Clientthread kann weiterlaufen, wenn er den Timeout ignoriert; sein spätes Ergebnis wird weder ausgeliefert noch gecacht.

## Architektur

**Tatsächliche Reihenfolge:** lokaler CSV-Loader/Codekatalog → Regelparsing und Terminologie → QuerySpec/optionale Zwecksignale → Zweckbewertung → deterministische Entscheidungsleiter → nur bei Genehmigung und vollständiger Spec parametrischer Compiler/Engine → Disclosure oder SPE → Response-Guard → FastAPI/CLI → Applicant/Staff; SPE-Vorschau, Download-Sperre und Audit laufen über eigene Workspace-Endpunkte. Ein Reject wird ebenfalls geparst, erhält aber keine Statistik/SPE. Unvollständige Interpretation liefert Hinweise für manuelle Prüfung ohne Datenfreigabe. Die lokal berechnete ParseReport.manual_review_required-Markierung für unaufgelösten Scope ist vor LLM und Cache unverzichtbar; sie darf nicht automatisch überschrieben werden (ADR-013).

| Bereich | Verantwortung |
|---|---|
| `config.py`, `models.py`, `law.py` | Settings, Pydantic-v2-Verträge und Artikelkatalog |
| `parsing/`, `terminology.py` | Regeln zuerst, ICD-10/ATC/LOINC-Mapping, optional Claude, validierter Cache |
| `decision.py`, `pipeline.py` | Zweckbelege, feste Leiter, Freigabegate und Applicant-/Staff-Antwort |
| `data.py`, `compiler.py`, `engine.py` | In-Memory-DuckDB, CSV-Import, Opt-out-Views, SQL mit Parametern, Rohzellen |
| `disclosure.py`, `spe.py` | Unterdrückung/Rundung/Leak-Guard bzw. ausgewählte SPE-Kopie, Preview, Audit |
| `api.py`, `__main__.py`, `web/` | FastAPI/Uvicorn, JSON-CLI, HTML/CSS/Vanilla-JS ohne Build-Schritt; `web/dashboard.js` enthält die reine Diagramm-/CSV-Logik, `web/assets/` Favicon und selbst gehostete OFL-Schriften |
| `eval/reference.py`, `eval/run_eval.py` | Unabhängige stdlib-CSV-Rechnung; HTTP-Eval mit Schema-/Multiplizitätskontrolle der SPE |

`AccessRequest` beschreibt den Antrag; `QuerySpec` Kohorte, Einheiten, Gruppen, Metriken und Record-Typen; `PurposeAssessment` hält Zweckbelege und `Decision` die Leiter/Artikel. `RawCount`, `RawPercent` und `RawMean` bewahren Zähler, Nenner und n bis zur Disclosure-Prüfung. `ProcessResult` enthält Applicant und Staff. Das Mermaid-Diagramm im README zeigt den vollständigen Datenfluss.

Views `pat`, `cond`, `med`, `obs`, `enc` enthalten ausschließlich Patienten ohne Opt-out. Die `_all`-Views dienen intern dem Vergleich für die Staff-Kennzahl „opt-out exclusions“; auch deren Ausgabe wird unterdrückt. Der LLM-Payload hat keinen Patientenzeilenpfad: nur freigegebene Antragstextfelder (`requested_as`, `requested_format`, `purpose`, `question`, `definitions`), Code-/Beschreibungspaare und Schema. Identität, beliebige Zusatzfelder, Ergebnisse und Terminologie-Zeilenzahlen werden nicht übernommen. Schema, Codes und Zweckbelege werden lokal geprüft. Claude erzeugt weder SQL noch die Zugangsentscheidung.

## Fachliche Regeln und Grenzen

1. **Entscheidungsleiter:** Art. 54 hat Vorrang → `REJECT`. Health data request → Statistik (53/69). Access application mit erkannter Begründung, warum Statistik nicht genügt → SPE (53/66/68/73). Sonstige Access application → Statistik (53/66/69). Bei Genehmigungen kommt Art. 71 für Opt-out hinzu.
2. **Statistik:** jede angefragte Gruppe inklusive leerer Gruppen anzeigen. Count < 10 einschließlich 0 → `<10`; Prozent bei Zähler oder Nenner < 10 und Mittelwert bei n < 10 → `suppressed`. `Decimal.quantize(Decimal("0.1"), ROUND_HALF_UP)` für eine Dezimale; kein Float vor der Rundung.
3. **Stichtag 2025-12-31:** Alter = 2025 − Geburtsjahr. Medikament aktiv bei Start <= Stichtag und leerem Ende oder Ende >= Stichtag. Letzter Messwert pro Patient; Aufenthalte als Aufenthalte zählen. Hauptdiagnose/`primary_icd10` nur filtern, wenn ausdrücklich angefragt.
4. **SPE:** nur ausgewählte consented Kohorte und genannte Record-Typen kopieren; Patienten-IDs unverändert im lokalen SPE-DB-File, ausschließlich im expliziten Preview-Response sichtbar, höchstens 20 Zeilen pro Aufruf. Exakte SPE-Patienten-/Tabellengrößen sind laut Challenge erlaubt. Download am bestehenden Permit → 403 plus Audit.
5. **Export:** Nur freigegebene anonymisierte Statistik darf als CSV heraus, clientseitig und exakt wie angezeigt, einschließlich `<10` und `suppressed`. Kein Export bei Reject oder manueller Prüfung; SPE-Datensätze bleiben gesperrt (Art. 73(2)).
6. **Nur synthetische Daten:** keine Patientenzeilen an externe Dienste; statistische Applicant-/Staff-Antworten durch zentrale Disclosure und Kennungsprüfung absichern. Kein absoluter Anonymitäts- oder Rechtskonformitätsanspruch.
7. **Demo-Grenzen ehrlich benennen:** keine echte Authentifizierung/Rollentrennung oder gehärtete SPE; Browserpreview und lokale Dateien sind kopierbar. Keine sekundäre Unterdrückung/Differenzsicherung. Konservativer englischer Parser führt bei nicht verstandenen Teilen zur manuellen Prüfung. Art.-54-Regex-Verneinungsfälle wie „No, we will use the data for advertising.“ können ohne gesonderte Staff-Prüfung durchrutschen. Kein Modelltraining/Resultatexport, keine Föderation, OMOP/FHIR, Gebühren oder Fristen implementiert.

## Konventionen und Workflow

- Python-Typannotationen, kleine reine Funktionen und Pydantic v2 für Datenverträge; Pfade mit `pathlib`, Textdateien UTF-8 (auch bei `ü` im Pfad).
- SQL-Werte (Codes, Daten, Labels) nur als Parameter; Tabellen-/Spaltenwahl ausschließlich aus validierten internen Optionen.
- Keine Secrets oder Datenkopien ins Repo: `.env`, `var/`, `*.csv`, `*.duckdb` und lokale Worktrees sind ignoriert. Bei anderem `EHDS_VAR_DIR` erzeugte Dateien ebenfalls außerhalb versionierter Inhalte halten. Vor jedem Commit `git status` prüfen, kein Push ohne Auftrag.
- Superpowers-Workflow bei Implementierung: Brainstorming → Spec → Plan → Subagent-Driven Development mit Spec-/Qualitätsreview; TDD bei Codeänderungen und Verifikation vor Abschlussbehauptungen. Kleine Conventional Commits gemäß globalen Constraints.
- Menschenlesbare Dokumentation durch Abgleich mit Auftrag, aktuellem Code, Commands und vorhandenen Nachweisen prüfen; keine tautologischen Texttests für Formulierungen. Der Controller pflegt WORKLOG, STATUS, TODO, DECISIONS und HANDOFF nach Tasks.
- Vor Push/Abgabe Sicherheitsreview; vorhandener Bericht `docs/SECURITY_REVIEW.md` ist eine statische Prüfung im Demo-Umfang, keine Produktionszertifizierung. Live-API-Aufrufe nicht aus Offline-Nachweisen ableiten.
- `AGENTS.md` bleibt ein Verweis auf diese Datei; Inhalte nicht doppelt pflegen.

## Verweise

- `README.md`: Setup, Demo inkl. 403/Audit, Mermaid, reale Metriken und Grenzen
- `docs/PROMPT_track3.md`: verbindlicher Auftrag
- `docs/CHALLENGE.md`, `docs/LAW.md`, `docs/GOALS.md`: Aufgabe, Rechtsnotizen und Erfolgskriterien
- `docs/superpowers/specs/2026-10-29-ehds-access-desk-design.md`, `docs/superpowers/plans/2026-10-29-ehds-access-desk.md`: Design und Plan; bei Abweichungen aktuellen Code und ADRs beachten
- `eval/results.md`, `docs/STATUS.md`, `docs/TODO.md`, `docs/DECISIONS.md`, `docs/WORKLOG.md`, `docs/HANDOFF.md`
