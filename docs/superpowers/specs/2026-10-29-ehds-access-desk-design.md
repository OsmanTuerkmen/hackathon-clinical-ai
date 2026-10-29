# Design: EHDS Access Desk (Track 3)

Stand: 2026-10-29 · Status: Entwurf zur Freigabe

## 1. Ziel und Verständnis

**Vom Nutzer vorgegeben (nicht verhandelbar, siehe `docs/PROMPT_track3.md` §2):**
Eine App nimmt einen EHDS-Antrag als JSON entgegen und liefert automatisch
(1) Entscheidung `REJECT` / `APPROVE_STATISTICAL` / `APPROVE_SPE` mit Artikeln nach fester Leiter,
(2) Statistik mit Small-Cell-Regel, (3) für SPE eine abgeschottete Kopie mit Download-Sperre,
(4) eine Ansicht für Antragsteller und eine Staff-Ansicht. Keine Handarbeit pro Antrag,
Klartext→Code-Mapping, Opt-out überall, Patientendaten verlassen die App nie, Referenzdatum 31.12.2025,
< 60 s pro Antrag, Eval mit 5 Metriken (10/10, 6/6, 0 Leaks, 10/10, < 60 s).

**Annahmen (von mir getroffen):**
- Die Jury bewertet sowohl über das Video als auch durch Ausführen des Repos. Ob ein LLM-Schlüssel vorhanden ist,
  ist unklar. Deshalb muss die App **ohne LLM vollständig funktionieren**; ein LLM ist eine optionale Verstärkung.
- Neue Jury-Anträge folgen dem Stil der 10 Beispiele (Definitionen als `Begriff = …`-Sätze, „Report per …:“),
  variieren aber Formulierungen, Dimensionen (`data_holder`, `sex`), Filter (`primary_icd10`) und lassen Codes weg.
- Interne Doku auf Deutsch; README, UI und Begründungstexte auf Englisch (Anträge, Daten und Jury-Abgabe sind englisch).

**Erfolg:** Alle Eval-Ziele erreicht, ≥ 8 eigene Anträge laufen korrekt, eine Access-Body-Mitarbeiterin kann jede
Entscheidung in der Staff-Ansicht Schritt für Schritt nachvollziehen, ein Antragsteller versteht sie ohne Jurawissen.

## 2. Verglichene Ansätze

| | A: LLM Text-to-SQL | B: Regelparser → Spec → SQL | C: Hybrid (empfohlen) |
|---|---|---|---|
| Idee | LLM schreibt SQL direkt | Grammatik-/Musterparser übersetzt Definitionen in eine typisierte QuerySpec, Compiler erzeugt SQL | B als Kern; optional Claude, das nur den Antragstext in dieselbe QuerySpec übersetzt, wenn der Regelparser nicht alles versteht |
| Korrektheit/Prüfbarkeit | schwer prüfbar, Halluzinationsrisiko | hoch, jede Zeile erklärbar | hoch; LLM-Ausgabe wird schema- und datenvalidiert |
| Reproduzierbarkeit | schwach | vollständig deterministisch | deterministisch (Regeln) bzw. Temperatur 0 + Cache (LLM) |
| Datenschutz | SQL könnte Rohdaten liefern | Small-Cell zentral erzwungen | wie B; LLM sieht nur Antragstext |
| Robustheit bei neuen Formulierungen | hoch | mittel | hoch |
| Läuft ohne API-Key | nein | ja | ja (dann wie B) |

**Entscheidung: C.** Die Entscheidungsleiter selbst ist immer deterministischer Code; das LLM liefert höchstens
zusätzliche Signale mit wörtlichem Beleg-Zitat aus dem Antrag. Festgehalten als ADR-001 in `docs/DECISIONS.md`.

Weitere Entscheidungen (ADRs):
- **ADR-002 Stack:** Python 3.14, DuckDB (in-memory, CSVs beim Start geladen, ~120k Zeilen, < 1 s), Pydantic v2 für
  alle Schemas, FastAPI + Uvicorn, statisches Frontend (HTML/CSS/Vanilla-JS, kein Build-Schritt), pytest.
  Optional `anthropic`-SDK. Begründung: schnell, reproduzierbar, SQL ist für Staff zeigbar, keine Node-Toolchain nötig.
- **ADR-003 Zentrale DB statt föderiert:** eine DuckDB-Instanz, `data_holder` bleibt als Dimension erhalten.
  Föderation pro Klinikum wäre fachlich näher an der Realität, bringt für 20.000 Patienten aber nur Komplexität.
  OMOP/FHIR-Konvertierung: nein (YAGNI).
- **ADR-004 SPE als eigene DuckDB-Datei pro Datenerlaubnis** unter `var/spe/<permit_id>/` plus Audit-Log (JSONL).
- **ADR-005 Sprache:** Doku Deutsch, Produkt/README Englisch.

## 3. Architektur

```
Antrag (JSON)
   │
   ▼
pipeline.process(request) ───────────────────────────────────────────────────────┐
   │ 1. decision.assess_purpose()   Regeln (Lexikon Art. 53/54, SPE-Begründung)    │
   │                                + optional LLM-Signal mit Beleg-Zitat           │
   │ 2. decision.decide()           feste Leiter → Outcome, Artikel, Trace          │
   │ 3. parsing.parse()             Regelparser → QuerySpec; bei Lücken LLM          │
   │ 4. terminology.resolve()       Klartext → ICD-10/ATC/LOINC, gegen Daten geprüft │
   │ 5. compiler.compile()          QuerySpec → parametrisiertes SQL                │
   │ 6. engine.run()                DuckDB auf Opt-out-gefilterten Views → Rohwerte  │
   │ 7a. disclosure.apply()         Small-Cell + ROUND_HALF_UP + Leak-Guard          │
   │ 7b. spe.provision()            nur bei APPROVE_SPE: Kopie + Sperre + Audit      │
   └──► Response {applicant: …, staff: …}                                          │
                                                                                   ┘
FastAPI (/api/requests, /api/process, /api/spe/…) ── statisches Web-UI
CLI (python -m ehds_desk decide|serve) ── eval/run_eval.py ── eval/reference.py
```

### Module (`src/ehds_desk/`)

| Modul | Zweck | Abhängigkeiten |
|---|---|---|
| `config.py` | `TRACK3_DATA` (Default `../track3`), `EHDS_VAR_DIR` (Default `var/`), `ANTHROPIC_API_KEY`, `EHDS_LLM` (`auto`/`off`), Referenzdatum | – |
| `models.py` | Pydantic: `AccessRequest`, `QuerySpec` (+ Kriterien, Dimensionen, Metriken), `Decision`, `Response` | pydantic |
| `law.py` | Artikelkatalog (Nr., Titel, Kurzfassung in eigenen Worten, Unterpunkte von Art. 53/54) | – |
| `decision.py` | `assess_purpose()` und `decide()`; reine Funktionen | `law`, `models` |
| `terminology.py` | Synonym-Lexikon + Fuzzy-Match gegen Beschreibungen in den Daten; Validierung gegen vorhandene Codes | `data` |
| `parsing/rules.py` | Regelparser Definitionen/Frage/„Report per“ → `QuerySpec` + Abdeckungsbericht | `terminology`, `models` |
| `parsing/llm.py` | Claude-Tool-Call mit JSON-Schema der `QuerySpec`; Cache in `var/cache/` | `anthropic` (optional) |
| `parsing/__init__.py` | Orchestrierung: Regeln zuerst, LLM nur bei unvollständiger Abdeckung | – |
| `data.py` | DuckDB-Verbindung, CSV-Import, Views `pat` (ohne Opt-out, mit `age`), `cond`, `med`, `obs`, `enc` (jeweils Semi-Join auf `pat`), Domänen (9 Bundesländer, 3 Klinika, 2 Geschlechter) | duckdb |
| `compiler.py` | `QuerySpec` → SQL-Text + Parameter (Codes nie per String-Konkatenation) | `models` |
| `engine.py` | SQL ausführen → `RawTable` mit typisierten Zellen (`RawCount n`, `RawPercent num/den`, `RawMean sum/n`) | `data`, `compiler` |
| `disclosure.py` | Small-Cell-Regel, Rundung via `Decimal.quantize(ROUND_HALF_UP)`, Leak-Guard | – |
| `spe.py` | SPE anlegen, Download-Sperre, Audit-Log | `data` |
| `pipeline.py` | Orchestrierung, Zeitmessung, Response-Aufbau | alle |
| `api.py`, `__main__.py` | FastAPI-App, CLI | – |

### QuerySpec (Kern-Schnittstelle)

```
QuerySpec
  unit: "patient" | "encounter"
  population: [Criterion]            # UND-verknüpft
  encounter_scope: EncounterScope?   # nur unit=encounter: types, start_from, start_to, primary_icd10 CodeSet
  group_by: [Dimension]              # region | data_holder | sex | age_band(bands)
  metrics: [Metric]
  output: "statistics" | "cohort_size"
  record_types: ["conditions"|"medications"|"observations"|"encounters"|"patients"]   # für SPE
  observation_loincs: [str]?         # SPE-Einschränkung (z. B. nur HbA1c)

Criterion = Age(min,max) | Sex(value) | Region(values) | DataHolder(values)
          | HasCondition(codes, negate) | ActiveMedication(codes, negate) | AnyMedication(codes, negate)
          | HasObservation(loinc, negate) | HadEncounter(types, start_from, start_to, primary_icd10, negate)
CodeSet   = {system: icd10|atc|loinc, prefixes:[…], label, source: explicit|lexicon|data_match}
Metric    = Count(name, where:[Criterion]) | Percent(name, numerator, denominator) | Mean(name, loinc, method="latest")
Dimension = Region | DataHolder | Sex | AgeBand(bands:[{label,min,max}])
```

Semantik-Festlegungen:
- Alter = 2025 − Geburtsjahr. Altersbänder schließen Patienten außerhalb aller Bänder aus (R03: implizit ≥ 65).
- Medikament aktiv: `start_date ≤ 2025-12-31 AND (end_date IS NULL OR end_date ≥ 2025-12-31)`.
- `Mean(method=latest)`: letzter Messwert pro Patient (max `date`), nur Patienten mit Wert.
- `unit=encounter`: gezählt werden Aufenthalte; `region` = Region des Patienten, `data_holder` = Klinikum des Aufenthalts.
- Gruppen: kartesisches Produkt der Dimensionsdomänen, Ergebnis per LEFT JOIN → leere Gruppen erscheinen mit 0 (→ `<10`).
- Diagnose = Zeile in `conditions.csv`; `primary_icd10` nur, wenn der Antrag es nennt („main diagnosis“, „primary diagnosis“, `primary_icd10`).

### Regelparser (deterministisch)

Satzweise Verarbeitung von `definitions` (plus `question` als Kontext). Jeder Satz wird einem Muster zugeordnet;
nicht verstandene Sätze landen im Abdeckungsbericht.
- `Term = …`-Definitionen (auch mehrere mit `;`): Alter („aged 18 or older“), Geschlecht, Diagnose („ICD-10 code starting
  with X [or Y]“), Medikament („ATC code starting with …“), Messwert (LOINC oder Name), Aufenthalt („encounter with type …“,
  „main/primary diagnosis …“), Kohorte („Cohort = adults with … who have …“), Prozent („A / B × 100“).
  Ohne Code → Terminologie-Mapping.
- „Age bands on …: a-b, …, 85+.“ → `AgeBand`.
- „Use the latest X per patient; patients without X are left out.“ → `Mean(latest)` + `HasObservation`.
- „Count stays (not patients) whose start_date is in 2025.“ → `unit=encounter`, Datumsbereich.
- „Report per <Dim> [and <Dim>]: a, b and c.“ → `group_by` + Metriken. Nominalphrasen werden zerlegt:
  Subjekt (adults/patients/women/men/stays) + „with <Term>“ + „who have a <Messwert> value“ + „no/active <Medikament>“;
  „% with …“, „share in %“, „prevalence“ → `Percent`; „mean <Messwert>“ → `Mean`; „size of the cohort“ → `cohort_size`.
- Basispopulation = Kriterien der ersten Zählmetrik; definierte, aber in keiner Metrik genutzte Diagnose-Begriffe
  wandern in die Basispopulation (R08: Brustkrebs).
- Unterstützte Gruppierwörter: region, hospital/data holder/`data_holder`, sex/gender, age band.

### LLM-Pfad (optional)

Aktiv, wenn `ANTHROPIC_API_KEY` gesetzt und `EHDS_LLM != off` und der Regelparser Lücken meldet. Claude bekommt nur
den Antrag (Text-Felder) plus Beschreibung des Schemas und der verfügbaren Codes (Codes sind keine Patientendaten),
antwortet per Tool-Call mit `QuerySpec`-JSON und Zweck-Signalen inkl. wörtlicher Belegzitate. Validierung: Pydantic,
Codes müssen in den Daten vorkommen, Zitate müssen wörtlich im Antrag stehen; eine Korrekturrunde bei Fehlern.
Cache-Schlüssel: SHA-256 über kanonisiertes Antrags-JSON + Prompt-Version + Modell. Modell und SDK-Details werden vor
der Umsetzung im `claude-api`-Skill nachgelesen. Ohne Key: Antrag wird mit dem Teilergebnis beantwortet, nicht
verstandene Teile werden in der Staff-Ansicht als „needs manual review“ markiert.

### Entscheidung (deterministisch)

`assess_purpose()` liefert Treffer mit Belegstellen:
- Art. 54 Kategorien: (a) nachteilige Entscheidungen über Personen / Re-Identifizierung (Abgleich mit Personallisten),
  (b) Beschäftigung, Versicherung/Kredit/Prämien, (c) Werbung/Marketing, (d) schädliche Produkte (Tabak/Nikotin,
  Alkohol, Glücksspiel, Waffen, Suchtprodukte) nur mit Produkt-/Vermarktungskontext und nicht bei Entwöhnung/Therapie,
  (e) ethikwidrige Tätigkeiten (keine Heuristik, nur Staff-Hinweis).
- Art. 53(1) Zweck (a)–(f) für die Begründung.
- SPE-Begründung (Art. 66(3), 67(2)(e)): explizite Aussage, dass Aggregate/Statistik/anonymisierte Daten nicht reichen,
  oder Bedarf an Individual-/Patientenebene für Modelltraining.

`decide()` – feste Leiter, erste zutreffende Stufe gewinnt:
1. Verbotener Zweck → `REJECT`, Art. 54.
2. `requested_as == "health data request"` → `APPROVE_STATISTICAL`, Art. 53, 69.
3. Access-Antrag mit SPE-Begründung → `APPROVE_SPE`, Art. 53, 66, 68, 73.
4. Sonstiger Access-Antrag → `APPROVE_STATISTICAL`, Art. 53, 66, 69.
Art. 71 wird bei jeder Genehmigung als Hinweis auf Opt-out-Ausschluss mitgenannt (erlaubt laut Aufgabe).
Ein LLM-Signal zählt nur mit wörtlich verifiziertem Zitat; für Art. 54 reicht ein Signal (konservativ), Trace zeigt die Quelle.
Kein erkannter Art.-53-Zweck → Entscheidung bleibt laut Leiter, aber Staff-Warnung „purpose unclear“.

### Small-Cell-Regel und Leak-Guard (`disclosure.py`)

Einziger Weg von Rohwerten zur Ausgabe:
- `RawCount n`: n < 10 → `"<10"`, sonst `n`.
- `RawPercent num/den`: num < 10 oder den < 10 → `"suppressed"`, sonst `round_half_up(100·num/den, 1)`.
- `RawMean sum/n`: n < 10 → `"suppressed"`, sonst `round_half_up(sum/n, 1)`.
- Alles in `Decimal` (Messwerte als `DECIMAL` aus DuckDB), kein Float vor der Rundung.
- Leak-Guard prüft die fertige Antwort: keine Ganzzahl < 10, keine Patienten-ID (`p-…`), keine Zelle ohne
  Disclosure-Herkunft. Verstoß → Exception, Antwort wird nicht ausgeliefert.
- SPE-Kohortengröße wird exakt berichtet (Vorgabe), aber nur im SPE-Pfad.

### SPE (`spe.py`)

- `permit_id = <request_id>-<8 Zeichen Hash des Antrags>` → idempotent, wiederholte Läufe erzeugen dieselbe SPE.
- Neue DuckDB-Datei `var/spe/<permit_id>/spe.duckdb` mit Tabelle `cohort(patient_id)` und nur den genannten
  Record-Typen, gefiltert auf Kohorte (ohne Opt-out), Patienten-IDs unverändert; Messwerte ggf. auf genannte LOINCs.
- `manifest.json` (Tabellen, Zeilenzahlen, Patientenzahl, Artikel, Erstellzeit) und `audit.jsonl` (Art. 73(1)(e)).
- API: `GET /api/spe/{id}` (Manifest), `GET /api/spe/{id}/preview/{table}` (max. 20 Zeilen, nur im SPE-Arbeitsbereich),
  `GET /api/spe/{id}/download/{table}` → immer **HTTP 403** + Audit-Eintrag „download blocked (Art. 73(2))“.

### UI

Einseitige App, drei Bereiche:
- **Eingang** (links): R01–R10 aus `TRACK3_DATA/requests`, eigene Anträge aus `requests/extra/`, „Neuer Antrag“ (JSON einfügen/hochladen).
- **Antragsteller-Ansicht:** großes Entscheidungs-Banner (Farbe + Text, nicht nur Farbe), Begründung in einfachen Sätzen
  mit Artikel-Chips (Tooltip mit Kurzfassung), Ergebnistabelle mit allen Gruppen, `<10`/`suppressed` grau mit Fußnote
  zur Small-Cell-Regel, bei SPE: Patientenzahl, Tabellen, Button „Open secure workspace“.
- **Staff-Ansicht:** Entscheidungsleiter mit Status je Stufe und Belegstellen, erkannter Zweck (Art. 53/54-Punkte, Quelle
  Regeln/LLM), Spec lesbar + JSON, Terminologie-Mapping (Begriff → Codes → in Daten gefundene Codes mit Beschreibung
  und Zeilenzahl, Warnungen), generiertes SQL, Opt-out-Ausschlüsse (wie viele Patienten der Kohorte wegen Opt-out
  fehlen), Disclosure-Protokoll (welche Zelle warum unterdrückt), Parser-Quelle, Laufzeit.
- **SPE-Arbeitsbereich:** Permit-Daten, Tabellen mit Zeilenzahlen, Vorschau, Download-Buttons → rotes Banner
  „Download blocked“ + Audit-Log sichtbar.

## 4. Fehlerbehandlung

- Ungültiges JSON / fehlende Pflichtfelder → HTTP 422 mit verständlicher Meldung.
- Unbekanntes `requested_as` → aus `requested_format` ableiten (records → Access-Antrag), Staff-Warnung.
- Term ohne Mapping → Staff-Warnung, Metrik als „not computed – needs manual review“ statt falscher Zahl.
- Mapping auf Codes ohne Treffer in den Daten → Staff-Warnung (Ergebnis 0 → `<10`).
- Leak-Guard-Verstoß → 500 mit generischer Meldung, Details nur im Server-Log/Staff.
- LLM-Fehler/Timeout (Budget 30 s) → Fallback auf Regelergebnis, Staff-Hinweis.

## 5. Tests und Evaluation

- **Unit (pytest, TDD):** `disclosure` (Grenzen 9/10, 0, Rundung 0.05/0.15/0.25 halbe aufwärts, Leak-Guard),
  `decision` (alle 10 Beispiele + Grenzfälle: Nikotin-Entwöhnung erlaubt, Werbung ohne Schlagwort „marketing“,
  Access ohne Begründung), `terminology`, `parsing.rules` (alle 10 Anträge → erwartete Spec), `compiler/engine`
  gegen echte Daten (Opt-out, aktive Medikation, letzter Messwert, Encounter-Zählung, leere Gruppen), `spe`
  (nur Kohorte, nur Record-Typen, kein Opt-out, Download 403 + Audit).
- **Eval (`eval/run_eval.py`):** schickt alle Anträge über die FastAPI-App (TestClient), 3 Läufe, misst die 5 Metriken,
  schreibt `eval/results.md`. Läuft zusätzlich über `requests/extra/` gegen `requests/extra/expected.json`.
- **Referenz (`eval/reference.py`):** unabhängiges Skript nur mit `csv`-Modul, rechnet R01, R03, R05, R07, R08, R09 nach
  und vergleicht mit `expected.json`; erzeugt auch die Sollwerte der eigenen Anträge.
- **Eigene Anträge (≥ 8) in `requests/extra/`:** `primary_icd10`-Filter, Gruppierung nach `data_holder`,
  Klartext ohne Codes, Grenzfall-Verbot (Werbung ohne das Wort „marketing“), Grenzfall-erlaubt (Nikotin-Entwöhnung),
  SPE mit Encounters, viele kleine Zellen (Region × Geschlecht × Altersband), Access-Antrag ohne Begründung.

## 6. Repo-Layout und Betrieb

```
pyproject.toml          src/ehds_desk/…       web/ (index.html, app.js, styles.css)
tests/                  eval/ (run_eval.py, reference.py, results.md)
requests/extra/         docs/ (CHALLENGE, LAW, GOALS, STATUS, TODO, DECISIONS, WORKLOG, superpowers/)
CLAUDE.md  AGENTS.md  README.md  .env.example
```
- Setup: `python -m venv .venv` → `.venv\Scripts\pip install -e ".[dev,llm]"`.
- Start: `python -m ehds_desk serve` → http://127.0.0.1:8000 · CLI: `python -m ehds_desk decide <file.json>`.
- `.gitignore`: `var/`, `.env`, `*.duckdb`, `*.csv`, `.claude/worktrees/`.

## 7. Nicht im Umfang (bewusst)

Echte Nutzerverwaltung/Authentifizierung, sekundäre Unterdrückung (Differenzangriffe), föderierte Ausführung,
OMOP/FHIR, Gebühren/Fristen, Analysewerkzeuge innerhalb der SPE (außer Vorschau). Werden in README als Grenzen genannt.
