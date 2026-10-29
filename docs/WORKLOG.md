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
