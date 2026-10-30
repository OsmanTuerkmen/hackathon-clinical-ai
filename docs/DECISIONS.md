# Entscheidungen (ADR)

Stand: 2026-10-29. Kontext und Vergleich der Ansätze: `docs/superpowers/specs/2026-10-29-ehds-access-desk-design.md` §2.

## ADR-001: Hybrid-Ansatz (Regelparser als Kern, optionales LLM)

Status: angenommen.
Der Regelparser übersetzt Definitionen deterministisch in eine typisierte `QuerySpec`; der Compiler erzeugt
parametrisiertes SQL. Ein LLM übersetzt höchstens den Antragstext in dieselbe `QuerySpec`, wenn der Regelparser
Lücken meldet. Die Entscheidungsleiter ist immer deterministischer Code; LLM-Signale zählen nur mit wörtlich
verifiziertem Zitat.
Gründe: prüfbar, reproduzierbar, Small-Cell zentral erzwungen, läuft ohne API-Key. Verworfen: reines Text-to-SQL
(schwer prüfbar, Rohdaten-Risiko) und reiner Regelparser (weniger robust bei neuen Formulierungen).

## ADR-002: Stack

Status: angenommen.
Python 3.14 (≥ 3.12), DuckDB (in-memory, CSVs beim Start geladen, ~120k Zeilen, < 1 s), Pydantic v2 für alle
Schemas, FastAPI + Uvicorn, statisches Frontend (HTML/CSS/Vanilla-JS, kein Build-Schritt), pytest; optional
`anthropic`-SDK.
Gründe: schnell, reproduzierbar, SQL für Staff zeigbar, keine Node-Toolchain nötig.

## ADR-003: Zentrale Datenbank statt föderiert

Status: angenommen.
Eine DuckDB-Instanz; `data_holder` bleibt als Dimension erhalten. Föderation pro Klinikum wäre fachlich näher an
der Realität, bringt bei 20.000 Patienten aber nur Komplexität. OMOP/FHIR-Konvertierung: nein (YAGNI).

## ADR-004: SPE als eigene DuckDB-Datei pro Datenerlaubnis

Status: angenommen.
Jede Genehmigung `APPROVE_SPE` erzeugt `var/spe/<permit_id>/spe.duckdb` (nur Kohorte, nur genannte Record-Typen,
ohne Opt-out) plus `manifest.json` und `audit.jsonl`. Download ist immer gesperrt (HTTP 403) und wird protokolliert
(Art. 73). `permit_id` ist aus dem Antrag abgeleitet, wiederholte Läufe sind idempotent.

## ADR-005: Sprache

Status: angenommen.
Interne Doku (`docs/`) auf Deutsch; README, UI-Texte und Begründungen auf Englisch (Anträge, Daten und
Jury-Abgabe sind englisch).

## ADR-006: Small-Cell-Regel exakt wie vorgegeben, keine Komplement-Unterdrückung

Status: angenommen (2026-10-29).
Kontext: Prozentwerte mit Zähler und Nenner ≥ 10 können trotzdem eine kleine Differenz (Nenner − Zähler < 10)
verraten. Optionen: (a) Regel der Aufgabe exakt umsetzen, (b) zusätzlich Komplement unterdrücken.
Entscheidung: (a). Die Regel ist in der Aufgabe fest vorgegeben und die erwarteten Zahlen hängen davon ab.
Die Lücke wird in README und TODO als bekannte Grenze genannt.

## ADR-007: Zweckregeln satzbezogen, LLM darf nur verschärfen

Status: angenommen (2026-10-29).
Kontext: Wortlisten über den ganzen Antrag erzeugten Fehl-Ablehnungen (z. B. „HR“ als Hazard Ratio,
„matched with controls“, „insurance“ und „exclude“ in verschiedenen Sätzen).
Entscheidung: Alle Teilmuster einer Art.-54-Regel müssen im selben Satz stehen; „HR“ zählt nur als Abteilung;
Datenabgleich nur mit Personenlisten. LLM-Belege brauchen ≥ 3 wörtliche Wörter; eine SPE-Begründung zählt nur,
wenn auch die Regel im Zitat greift. So kann das LLM eine Ablehnung auslösen, aber nie allein Zugang zu
Einzeldaten öffnen.

## ADR-008: Terminologie lieber „manuelle Prüfung“ als falscher Code

Status: angenommen (2026-10-29).
Entscheidung: Datenabgleich nur bei Jaccard > 0,5 oder wenn alle Wörter des Begriffs in genau einer Beschreibung
stehen; Qualifier direkt vor einem Lexikonbegriff („pulmonary hypertension“) heben den Treffer auf. Nicht
abbildbare Begriffe gehen an das Personal statt falsche Zahlen zu liefern. Zeilenzahlen in der Staff-Ansicht
zählen nur Patienten ohne Opt-out.

## ADR-009: Gemeinsame Altersbandpopulation und vollständige Messphrasen

Status: angenommen (2026-10-30, M2-Review).
Statistik, SPE-Kohorte und Opt-out-Ausschlusszahl verwenden dieselbe Vereinigung der angefragten Altersbänder. Spezifische Messanforderungen gelten unabhängig vom Nomen values/measurements/observations. Ein unauflösbarer Messname oder ein nicht unterstützter Mittelwertfilter führt zur manuellen Prüfung statt stillschweigend breiterer Daten. Kosten: Mehr unübliche Formulierungen können manuelle Prüfung erfordern; Datenschutz und korrekte Bedeutung haben Vorrang.
