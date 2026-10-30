# Übergabe (Stand 2026-10-30)

Für die nächste Agentin / den nächsten Agenten (z. B. Codex). Verbindlicher Auftrag: `docs/PROMPT_track3.md`.
Design: `docs/superpowers/specs/2026-10-29-ehds-access-desk-design.md`. Plan mit allen Tasks:
`docs/superpowers/plans/2026-10-29-ehds-access-desk.md`. Gesetz: `docs/LAW.md`. Entscheidungen: `docs/DECISIONS.md`.

## Wo der Code liegt

- Repo `OsmanTuerkmen/hackathon-clinical-ai` (privat). Lokal: `C:\Users\BüsraTürkmen\Documents\Hackathon\hackathon-clinical-ai`.
- Arbeitsbranch **`track3-app`** (Git-Worktree unter `.claude/worktrees/track3-app`). `main` enthält nur Brief, Spec und
  Gesetzesdoku. Nichts ist gepusht. Branch `worktree-track1-app` = verworfener Track-1-Versuch: nicht anfassen.
- Aufgabendaten (nicht im Repo, nie kopieren): `C:\Users\BüsraTürkmen\Documents\Hackathon\track3`
  (`data/*.csv`, `requests/R01–R10.json`, `requests/expected.json`). `config.load_settings()` findet den Ordner
  automatisch über die Vorfahren-Verzeichnisse; alternativ ENV `TRACK3_DATA`.

## Befehle (Git Bash, aus dem Worktree)

```bash
python -m venv .venv && .venv/Scripts/pip install -e ".[dev,llm]"   # einmalig (existiert bereits)
.venv/Scripts/python -m pytest -q                                  # 404 passed (2026-10-30)
.venv/Scripts/python -m ehds_desk decide <antrag.json> [--staff]    # CLI
```

## Fertig (Tasks 1–9 des Plans, je mit Review und Fix-Runden)

| Modul | Inhalt |
|---|---|
| `config.py`, `data.py` | Settings (`load_settings(env_file=None)` in Tests!), DuckDB in-memory, Views `pat/cond/med/obs/enc` ohne Opt-out, `*_all` mit |
| `models.py` | Pydantic-Schnittstellen: `AccessRequest`, `QuerySpec` (Kriterien/Metriken/Dimensionen, Diskriminator `kind` Pflicht), Raw-Zellen, `Decision` |
| `disclosure.py` | Small-Cell (`<10`, `suppressed`), `round_half_up` (Decimal), `assert_no_leak`, `PATIENT_ID_PATTERN` |
| `law.py`, `decision.py` | Artikelkatalog; Leiter REJECT(54) → Statistik-Anfrage(53,69,71) → Zugang mit Begründung(53,66,68,73,71) → Zugang sonst(53,66,69,71); satzbezogene Regex-Regeln mit Verneinungs-Guard; LLM-Belege nur verbatim ≥3 Wörter, SPE nie allein durch LLM |
| `terminology.py` (+ `_lexicon`) | Klartext → ICD-10/ATC/LOINC, gegen Daten verifiziert; Qualifier/unsichere Treffer → `None` (manuelle Prüfung) |
| `compiler.py`, `engine.py` | QuerySpec → parametrisiertes SQL; leere Gruppen per Domänen-CROSS JOIN; Opt-out-Ausschlusszahl |
| `parsing/rules.py`, `phrases.py`, `metrics.py` | Deterministischer Regelparser inkl. `primary_icd10`, `data_holder`, Klartext; Restwort-Check: nicht verstandener Text → `not_understood` statt falscher Zahlen |
| `parsing/__init__.py` | `ParseResult`, `parse_request` (bisher nur Regeln) |
| `spe.py` | SPE als eigene DuckDB-Datei unter `var/spe/<permit_id>/`, Manifest, Audit-Log (JSONL), Download immer blockiert |
| `pipeline.py`, `__main__.py` | `DeskService.process()` → `ProcessResult{applicant, staff}`; Leak-Guard vor Rückgabe; CLI `decide`/`serve` (serve braucht `ehds_desk.api:app` aus Task 11) |

Verifiziert: R01–R10 entscheiden wie `expected.json`; R01, R03, R07, R08, R09 liefern die erwarteten Zahlen je Metrik;
R05 Kohorte 1152 (55 Opt-outs ausgeschlossen). Parser-Probes: 211 jury-artige Formulierungen, 0 „vollständig, aber falsch“.

## Offen (in dieser Reihenfolge)

1. **Task 10 – optionaler Claude-Pfad** (nicht begonnen). Brief = Plan Task 10. Verbindliche API-Fakten (aus dem
   offiziellen claude-api-Skill, 2026-10-30): Modell `claude-opus-5-5` (Default in `config.py`/`.env.example` noch
   `claude-sonnet-5-5` → ändern); **kein** `temperature` (seit 2026-10-21 HTTP 400) → Reproduzierbarkeit nur über
   Cache `var/cache/llm/<sha256>.json`; **kein** erzwungenes `tool_choice` (400) → strukturierte Ausgabe mit
   `client.messages.parse(model=..., max_tokens=16000, system=..., messages=[...], output_format=<Pydantic-Modell>,
   output_config={"effort": "medium"})`, `response.parsed_output`, vorher `stop_reason` auf `refusal`/`max_tokens` prüfen;
   Schema-Grenzen: `anyOf` ok, `oneOf`/Rekursion/Längen-Constraints nicht → ggf. Schema nachbearbeiten;
   optional Refusal-Fallback `client.beta.messages.parse(..., betas=["server-side-fallback-2026-07-01"], fallbacks="default")`.
   Nur Antragstext + Code-Katalog senden, nie Patientenzeilen. LLM nur wenn Regelparser unvollständig UND Key gesetzt;
   Fehler → Regelergebnis + Staff-Hinweis. Tests mit Fake-Client (kein Key auf dieser Maschine).
2. **Meilenstein-Review M2** (Tasks 6–9, Range `791dcd6..6d1e439`) wurde wegen Limit abgebrochen → neu ausführen.
3. **Task 11 – FastAPI** (`api.create_app`, `app` exportieren; `/api/process`, `/api/spe/{id}/download/{table}` → 403;
   `web/` nur mounten, wenn vorhanden; `preview` liefert date/Decimal → JSON-serialisieren).
4. **Task 12 – Web-UI** (Antragsteller-/Staff-Ansicht, SPE-Arbeitsbereich mit blockiertem Download, Screenshot nach `docs/img/`).
5. **Task 13 – Eval** (`eval/reference.py` nur stdlib; `eval/run_eval.py` über TestClient, 3 Läufe, 5 Metriken → `eval/results.md`).
6. **Task 14 – ≥ 8 eigene Anträge** in `requests/extra/` (+ `expected.json`, Zahlen aus Referenzskript).
7. **Task 15 – README (englisch, Mermaid, Metriken, Grenzen), `security-review`, Abschluss** gemäß Prompt §7.
   Danach Branch nach `main` mergen bzw. PR – **Push nur nach Freigabe durch den Nutzer**.

## Getroffene Entscheidungen (Kurzfassung, Details in DECISIONS.md / Commits)

- R1 Tasks sequenziell (ein Worktree). R2 API mountet `web/` nur, wenn vorhanden.
- R4/ADR-006 Small-Cell exakt wie Aufgabe, keine Komplement-Unterdrückung (bekannte Grenze).
- R5–R6/ADR-007 Art.-54-Regeln satzbezogen; LLM darf verschärfen, nie allein SPE öffnen.
- R7 Zeilenzahlen in Code-Mappings nur ohne Opt-outs. R8/ADR-008 unsichere Terminologie → manuelle Prüfung.
- R10/R11 Verneinungs-Guard: Komma ist keine Satzteilgrenze; konstruierte Sätze wie „No, we will use the data for
  advertising.“ rutschen ohne LLM durch (bekannte Grenze, in TODO).
- R12 Parser: Restwort-Check überall, lieber `not_understood` als falsche Zahl.
- R13 SPE-Patientenzahl und SPE-Tabellenzeilen exakt (Aufgabe verlangt das), keine Small-Cell-Regel dort.

## Arbeitsweise (vom Nutzer verlangt)

Superpowers-Workflow (TDD je Task, Review nach jedem Task und Meilenstein, `verification-before-completion`,
`finishing-a-development-branch`); nach jedem Task `docs/STATUS.md`, `docs/TODO.md`, `docs/WORKLOG.md` pflegen;
kleine Conventional Commits; vor jedem Commit `git status` (keine CSV, kein `var/`, keine `.env`); nichts pro Antrag
hart kodieren; Patientendaten nie an externe Dienste. Interne Doku Deutsch, UI/README Englisch.
