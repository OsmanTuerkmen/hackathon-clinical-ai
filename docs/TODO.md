# TODO

Stand: 2026-10-30. Implementierung und Verifikation abgeschlossen; kein Push/Merge ohne Nutzerfreigabe.

- [x] Tasks 1–9: Daten, Modelle, Disclosure, Gesetzesleiter, Terminologie, Compiler/Engine, Regelparser, SPE, Pipeline/CLI
- [x] M2-Review über791dcd6..6d1e439 und Korrekturen
- [x] Task10: optionaler Claude-Pfad, validierter Cache, Codesystembindung, Fake-/SDK-Schematests
- [x] Task11: FastAPI einschließlich 403/Audit, sichere Fehler und Vorschau-Serialisierung
- [x] Task12: Applicant-/Staff-/SPE-UI, Screenshots, responsiv, Init-Race/XSS-Prüfung
- [x] M3-Schnittstellenreview und Nachreview
- [x] Task13: unabhängige stdlib-Referenz und gehärteter Drei-Lauf-Eval
- [x] Task14: zehn neue Anträge und acht unabhängige Extra-Referenzen
- [x] Task15: englisches README, Mermaid, echte Metriken, Demo-/Videoablauf und Grenzen
- [x] Finaler P1: ausgeschlossene SPE-Recordtypen sicher manuell prüfen und aus Teil-Spec entfernen
- [x] Finaler P1: vor-/nachgestellte und parenthetische Messartenbeschränkungen vollständig prüfen
- [x] Finaler P1: Einschränkungen nach cohort-size nicht verschlucken
- [x] Finaler P2: Gruppierungsqualifier vollständig prüfen, auch vor LLM/Cache unverzichtbar manuell
- [x] Fokussierte Regressionen, scoped Nachreviews und Sicherheitsnachreview
- [x] Frische702Tests,14/14Referenzen,60POST-Eval und133Browserchecks nach allen Korrekturen
- [x] Trackingprüfung: keineCSV, var/, .env oderDuckDB-Dateien versioniert
- [x] Doccess-Redesign (Richtung J Compliance): Marke, Sidebar, Entscheidungsleiter, Applicant/Staff/SPE, lokale OFL-Schriften, neue Screenshots

- [x] Animationen aus `hackathon-melih`, Bento-Dashboard aus `handoff/bento-dashboard`, CSV-Export freigegebener Statistik, Review-Bugfixes
- [x] Geführtes Formular für neue Anträge mit erzeugtem JSON, Review-Bugfixes

## Sicherheitsreview Frontend (offen, Auftrag vom 30.10.)

Basis: lokaler Branch `track3-app` ab Commit `caf5613` (205bdc1 und caf5613 noch nicht auf origin), eigener Branch `security-review-update`. Zuerst `CLAUDE.md` lesen.

- [ ] `docs/SECURITY_REVIEW.md` aktualisieren: Stand, Commit, neuer Prüfumfang, Befunde (Schweregrad, Datei:Zeile, Szenario), Grenzen. Vermutungen kennzeichnen.
- [ ] Nachweisen, dass das Backend seit dem letzten Bericht unverändert ist (nicht übernehmen, selbst prüfen). Hinweis: Branch `melih/jury-fixes` ändert `decision.py` und `parsing/rules.py`, siehe unten.
- [ ] Prüfumfang: `web/app.js`, `web/dashboard.js`, `web/request-form.js`, `web/index.html`, `web/styles.css`, `tests/test_web.py`, `tests/test_dashboard_model.py`, `tests/test_request_form.py` (ADR-014, -015, -016)
- [ ] 1. Textausgabe: alle nicht vertrauenswürdigen Werte nur als DOM-Text, nie `innerHTML` (Antragstexte, Parser-Hinweise, Werte aus eingefügtem JSON)
- [ ] 2. CSV-Export: nur bei genehmigter Statistik; `<10`/`suppressed` exakt; kein Export bei Reject oder manueller Prüfung; keine SPE-Datensätze; CSV-Formelinjektion und Dateiname prüfen
- [ ] 3. Dashboard: maskierte Werte dürfen weder über Skalierung, Balkenlänge, Tooltips noch Prozentangaben auf den echten Wert schließen lassen; Opt-out-Zahl je Kohorte nur für Staff
- [ ] 4. Formular/JSON: Zusatzfelder aus eingefügtem JSON (`buildRequest` mit `base`) serverseitig prüfen; `requestKind` (web/request-form.js) gegen `_classify` (src/ehds_desk/decision.py) abgleichen
- [ ] 5. Race Guards: `epoch`/`AbortController` dürfen keine veraltete Antwort oder Datenfreigabe anzeigen; Manual-Review-Gate nicht umgehbar
- [ ] 6. Keine externen Hosts, keine Secrets, keine Patientenzeilen in `docs/img/`, Logs oder versionierten Dateien
- [ ] Echte High-/Medium-Befunde testgetrieben beheben (Regressionstest erst rot, dann Fix); Backend nur mit Begründung ändern
- [ ] Prüfungen: `pytest -q` (Ausgangsstand 771), `eval/reference.py` (14/14), `eval/run_eval.py` (10/10, 6/6, 0 Leaks, 10/10; eigene 10/10, 8/8, 0, 10/10)
- [ ] WORKLOG, STATUS, TODO, HANDOFF aktualisieren; kleine Conventional Commits; vor jedem Commit `git status`
- Grenzen: kein Push/Merge/main ohne Freigabe; `worktree-track1-app` nicht anfassen; keine Originaldaten, `.env`, `var/`, CSV/DuckDB committen; keine Patientenzeilen in Tools/Screenshots; keine Zertifizierungs- oder absoluten Anonymitätsaussagen

## Jury-Tests aus `hackathon-melih` (Branch `melih/jury-fixes`)

36 jury-ähnliche und adversariale Anträge aus `melih-gatekeeper/fixtures/` gegen Doccess laufen lassen (Erwartungswerte aus unabhängigem Oracle-SQL).

- [x] Alkohol-Markenkampagne (A03) wurde genehmigt → jetzt REJECT, Art. 54(1)(d) (Muster `alcohol`, `beer`, `brewer`, `wine`, `brand campaign`)
- [x] Weiterverkauf von Tabellen / Datenbroker (A04) wurde genehmigt → jetzt REJECT, Art. 54(e)
- [x] „Aktiv am 30. Juni 2025" (C07) lieferte stillschweigend Zahlen zum 31.12. → jetzt manuelle Prüfung statt falscher Zahlen
- [ ] Homoglyphen („prеmiums" mit kyrillischem е, A14) und deutsche Injektion (A16) werden genehmigt → Normalisierung/Injektionserkennung aus `melih-gatekeeper/backend/app/security.py` portieren
- [ ] Injektion mit „Aggregates are not enough" (A08) führt zu APPROVE_SPE → bei Injektionsverdacht nie SPE
- [ ] Headline lautet „Approved: you receive anonymised statistics", obwohl bei manueller Prüfung keine Zahlen kommen (C05, C06, C07, C10, C16) → Headline anpassen
- [ ] Optional unterstützen statt ablehnen: Aufenthalte mit Ende im Jahr (C05), Schwellenwert auf letzten Messwert als Definition (C06), Mittelwert systolischer Blutdruck (C10), Regionsfilter im Report (C16), anderes Aktiv-Datum (C07)

## Nutzer / Abgabe

- [ ] Bis2Minuten Demo-Video aufnehmen (Ablauf im README)
- [ ] Bei Bedarf ausdrückliche Freigabe für Push/PR/Merge und öffentliche Repository-Sichtbarkeit erteilen

## Optional

- [ ] Paketmetadaten, FastAPI-Titel und CLI-Beschreibung von „EHDS Access Desk“ auf Doccess umstellen (Backend, daher nicht Teil des UI-Auftrags)

- [ ] Bei Bedarf weitere Punkte aus `HACKATHON_MELIH.md` und `SUGGESTIONS.md` prüfen (Entscheidungsbrief, Sicherheitsschicht, Zusatzsuiten, geführter Assistent); nicht beauftragt

## Bewusste Grenzen für spätere Weiterentwicklung

Echte Auth/Rollentrennung und SPE-Härtung; sekundäre Unterdrückung/Differenzschutz; breiteres Sprachverständnis und rechtliche Einzelfallprüfung statt Regex; bekanntes R11-Verneinungsproblem; Live-Claude-Verifikation; Analyse-/Ergebnisexporttools; Föderation/OMOP/FHIR/Gebühren/Fristen. Keine automatische Fortsetzung oder Veröffentlichung eingerichtet.
