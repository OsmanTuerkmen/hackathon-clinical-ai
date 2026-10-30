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

## Nutzer / Abgabe

- [ ] Bis2Minuten Demo-Video aufnehmen (Ablauf im README)
- [ ] Bei Bedarf ausdrückliche Freigabe für Push/PR/Merge und öffentliche Repository-Sichtbarkeit erteilen

## Bewusste Grenzen für spätere Weiterentwicklung

Echte Auth/Rollentrennung und SPE-Härtung; sekundäre Unterdrückung/Differenzschutz; breiteres Sprachverständnis und rechtliche Einzelfallprüfung statt Regex; bekanntes R11-Verneinungsproblem; Live-Claude-Verifikation; Analyse-/Ergebnisexporttools; Föderation/OMOP/FHIR/Gebühren/Fristen. Keine automatische Fortsetzung oder Veröffentlichung eingerichtet.
