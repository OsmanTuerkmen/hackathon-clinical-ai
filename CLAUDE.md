# CLAUDE.md – EHDS Access Desk (Track 3)

## Überblick

Python-App, die EHDS-Anträge (JSON) auf Zugang zu Gesundheitsdaten automatisch entscheidet
(`REJECT` / `APPROVE_STATISTICAL` / `APPROVE_SPE`, jeweils mit Artikeln) und Statistiken mit
Small-Cell-Schutz aus 20.000 synthetischen Patienten (CSV) berechnet. Zwei Ansichten: Antragsteller und Staff.
Läuft vollständig ohne LLM; ein LLM (Anthropic) ist eine optionale Verstärkung.

Die CSVs und Beispielanträge liegen **außerhalb** des Repos (`track3/data`, `track3/requests`) und werden nie kopiert.

## Befehle

Git Bash, aus dem Repo-/Worktree-Wurzelverzeichnis:

```bash
python -m venv .venv && .venv/Scripts/pip install -e ".[dev,llm]"   # Setup
.venv/Scripts/python -m pytest -q                                    # Tests
.venv/Scripts/python -m ehds_desk serve                              # Server (geplant, http://127.0.0.1:8000)
.venv/Scripts/python -m ehds_desk decide <antrag.json>               # CLI (geplant)
.venv/Scripts/python eval/run_eval.py                                # Eval, 5 Metriken (geplant)
```

Konfiguration über Umgebungsvariablen oder `.env` (siehe `.env.example`): `TRACK3_DATA`, `EHDS_VAR_DIR`,
`EHDS_LLM` (`auto`/`off`), `ANTHROPIC_API_KEY`, `EHDS_LLM_MODEL`. Ohne `TRACK3_DATA` wird der erste Vorfahr des
Repos gesucht, der `track3/requests/expected.json` enthält (funktioniert auch aus `.claude/worktrees/…`).

## Architektur (Kurzfassung)

Pipeline: Antrag → Zweck/Entscheidung (deterministische Leiter) → Parsing (Regeln, optional LLM) → Terminologie →
Compiler (SQL, parametrisiert) → Engine (DuckDB) → Disclosure (Small-Cell) bzw. SPE-Bereitstellung → Antwort
`{applicant, staff}`. Details: `docs/superpowers/specs/2026-10-29-ehds-access-desk-design.md`.

| Modul (`src/ehds_desk/`) | Zweck |
|---|---|
| `config.py` | Settings (ENV/.env), Referenzdatum, Small-Cell-Schwelle |
| `models.py` | Pydantic-Schemas: Antrag, QuerySpec, Decision, Response |
| `law.py` | Artikelkatalog (Art. 53/54 usw.) |
| `decision.py` | `assess_purpose()`, `decide()` – reine Funktionen |
| `terminology.py` | Klartext → ICD-10/ATC/LOINC, gegen Daten geprüft |
| `parsing/` | Regelparser (`rules.py`), optionaler LLM-Pfad (`llm.py`), Orchestrierung |
| `data.py` | DuckDB, CSV-Import, Views mit/ohne Opt-out |
| `compiler.py` / `engine.py` | QuerySpec → SQL + Parameter → Rohwerte |
| `disclosure.py` | Small-Cell, Rundung, Leak-Guard |
| `spe.py` | Abgeschottete Kopie, Download-Sperre, Audit-Log |
| `pipeline.py` | Orchestrierung, Zeitmessung |
| `api.py`, `__main__.py` | FastAPI-App, CLI |

Datenzugriff: Views `pat, cond, med, obs, enc` enthalten nur Patienten **ohne** Opt-out (`pat` mit Spalte `age`);
`pat_all, cond_all, …` nur für die Staff-Kennzahl „opt-out exclusions“.

## Konventionen

- Python ≥ 3.12 (entwickelt auf 3.14), Pydantic v2 für alle Schemas, Typannotationen, kleine reine Funktionen.
- TDD: erst fehlschlagender Test, dann Implementierung. Kleine Commits (Conventional Commits).
- SQL-Werte (Codes, Daten, Labels) nur als Parameter; Tabellennamen nur aus Whitelist.
- Geld/Prozent/Mittelwerte: `Decimal`, Rundung `quantize(Decimal("0.1"), ROUND_HALF_UP)`, kein Float vor der Rundung.
- Doku in `docs/`: Deutsch. UI-Texte, Begründungen, README: Englisch.
- Pfade können Nicht-ASCII-Zeichen enthalten (`ü`); immer `pathlib` und UTF-8.

## Harte Regeln

1. **Keine Patientendaten an externe Dienste.** Ans LLM gehen nur der Antrag (Textfelder) und der Code-Katalog
   (Codes + Beschreibungen, keine Zeilen).
2. **Small-Cell-Regel (Schwelle 10):** Count `< 10` → `"<10"`; Prozent mit Zähler oder Nenner `< 10` → `"suppressed"`;
   Mittelwert mit `n < 10` → `"suppressed"`. Antworten enthalten nie rohe Counts `< 10` und nie Patienten-IDs
   (`p-[0-9a-f]{8}`) außerhalb der SPE-Vorschau.
3. **Opt-out (Art. 71):** Opt-out-Patienten fehlen in allen Views ohne `_all`-Suffix.
4. **Referenzdatum 2025-12-31:** Alter = 2025 − Geburtsjahr; Medikament aktiv ⇔ `start_date ≤ 2025-12-31` und
   (`end_date` leer oder `≥ 2025-12-31`).
5. **Keine Secrets im Repo:** `.env`, `var/`, `*.duckdb`, `*.csv` sind gitignored; vor jedem Commit `git status` prüfen.
   Kein Push ohne Auftrag.
6. **Workflow (Superpowers):** Brainstorming → Spec → Plan → Ausführung per Subagent-Driven Development
   (Implementer → Spec-Review → Qualitäts-Review) → Verification vor „fertig“. Doku-Pflege (WORKLOG, STATUS, TODO,
   DECISIONS) macht der Controller nach jedem Task.

## Verweise

- `docs/CHALLENGE.md` – Aufgabenstellung Track 3
- `docs/LAW.md` – Rechtsgrundlagen (EHDS-Artikel) in Kurzform
- `docs/GOALS.md` – Ziele und Erfolgskriterien
- `docs/PROMPT_track3.md` – ursprünglicher Auftrag
- `docs/superpowers/specs/` und `docs/superpowers/plans/` – Design-Spec und Umsetzungsplan
- `docs/STATUS.md`, `docs/TODO.md`, `docs/DECISIONS.md` (ADRs), `docs/WORKLOG.md`
