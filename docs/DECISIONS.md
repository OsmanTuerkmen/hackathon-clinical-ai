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

## ADR-010: Optionaler Claude-Pfad mit lokaler Reproduzierbarkeit

Status: angenommen und umgesetzt (Task 10, 2026-10-30).
Der Regelparser bleibt der erste Pfad. Nur bei unvollständigem Parsing, auto-Modus und vorhandenem Key darf das offizielle Anthropic-SDK Antragstext und einen Code-Katalog ohne Patientenzeilen übersetzen. Modell ist claude-opus-5-5; temperature und erzwungenes tool_choice werden nicht gesendet. Strukturierte Ausgabe nutzt messages.parse mit Pydantic; die lokal geprüfte SDK-Version 2.3.0 bereitet das JSON-Schema API-kompatibel auf. Volle lokale Modellvalidierung bleibt erforderlich. Reproduzierbarkeit beruht auf einem versionierten, lokal validierten Cache unter var/cache/llm; das Zeitbudget schließt die einzige erlaubte Korrekturrunde ein. Bei Fehlern bleibt das Regelergebnis mit Staff-Hinweis bestehen. Ohne echten API-Key wird ausschließlich mit Fake-Clients und transportlosen SDK-Schematests verifiziert; eine Live-API-Verifikation ist damit nicht belegt.

Review-Ergänzung: Jedes Codefeld wird vor Übernahme und beim Cache-Lesen an sein Codesystem gebunden (Diagnosen/Hauptdiagnosen ICD-10, Medikamente ATC, Messungen LOINC). Ein falsches System löst eine Korrektur oder den sicheren Fallback aus; fehlende Treffer bei richtigem System bleiben Staff-Warnungen. Ein Fremdclient, der seinen Timeout ignoriert, kann nach Ablauf im Daemon-Thread weiterlaufen; dessen Ergebnis wird nicht ausgeliefert oder gecacht.

## ADR-011: Lokale UI mit sicherer Textausgabe und Anfrageversionen

Status: angenommen und umgesetzt (Task 12, 2026-10-30).
Die UI nutzt lokale Assets und DOM-Textknoten statt HTML-Strings aus Anträgen oder API-Antworten. AbortController und Versionszähler verhindern, dass verspätete Antworten einen neu gewählten Antrag überschreiben. Abbruch einer Browseranfrage ist keine Zusage, bereits gestartete Serverarbeit hart abzubrechen. Browserprüfungen erfassen SPE-Funktionen nur als Bool-/Anzahlnachweise; Doku-Screenshots enthalten ausschließlich anonymisierte Statistik.

## ADR-012: Unabhängiger Eval-Vertrag statt Selbstvergleich

Status: angenommen und umgesetzt (Task 13, 2026-10-30).
Die Referenz rechnet ausschließlich aus Original-CSVs mit der Standardbibliothek. Eval prüft jede der drei HTTP-Antworten und scannt auch Fehlantworten. SPE-Spalten stammen als Erwartung unabhängig aus CSV-Headern beziehungsweise dem ausdrücklich erlaubten cohort-/patients-Schema; tatsächliche DB-Spalten definieren keine Erwartung. Record-Vergleich erhält Zeilenmultiplizität. Ein eigener Runtime-Unterordner verhindert Überschneidungen mit der laufenden Browser-Demo. Bei fehlender IANA-Datenbank berechnet ein durch DST-Grenztests abgesicherter stdlib-Fallback die aktuelle Europe/Vienna-Zeit; dessen EU-Zeitregeln müssten bei künftigen gesetzlichen Änderungen angepasst werden.

## ADR-013: Nicht übersteuerbare manuelle Scope-Prüfung

Status: angenommen und umgesetzt (abschließende Reviewkorrektur, 2026-10-30).
Teiltreffer dürfen weder mehr Recordtypen/Messarten noch größere Kohorten oder grobere Gruppen freigeben. Recordausschlüsse, Messbeschränkungen, Größenformulierungen und Dimensionsausdrücke werden vollständig geprüft. ParseReport.manual_review_required wird lokal berechnet und in complete berücksichtigt; bei dieser Pflichtmarkierung erfolgt keine optionale LLM-Übersetzung und keine Cache-Übernahme. Gewöhnliche Parserlücken bleiben optional übersetzbar.
Kosten: Auch manche klare Ausschlüsse wie encounters without medications und ungewöhnliche Scopeformulierungen verlangen derzeit Staff-Prüfung. Diese zusätzliche manuelle Arbeit ist gegenüber einer stillschweigend breiteren Datenfreigabe akzeptiert. Vor-/nachgestellte und parenthetische, vollständig erkannte HbA1c-Formen werden dagegen auf ihren LOINC begrenzt. Die Gruppierungssperre gilt gleichermaßen für Definition und Frage. Keine Antrags-ID-Sonderfälle oder Änderungen an Disclosure/Opt-out/Entscheidungsleiter.

## ADR-014: Produktname Doccess und Richtung „J Compliance“

Status: angenommen und umgesetzt (2026-10-30).
Kontext: Die alte Oberfläche wirkte mit Hero, Kartenstapel und Navy/Teal austauschbar; der Nutzer wünschte eine eigenständige Arbeitsanwendung unter dem Namen Doccess und wählte aus neun Entwürfen die Richtung J Compliance.
Entscheidung: Feste Forest-Sidebar `#10362C` mit großer Wortmarke (D mit Türöffnung), Suche und allen Anträgen; die vier Stufen der Entscheidungsleiter stehen neben den Ergebnissen; der Entscheidungs-Badge sitzt im Kopf und gilt für Applicant und Staff. Mint `#7FE0A9` bleibt der Sidebar vorbehalten, damit „Approved“ im Hauptbereich über Häkchen, Text und `#14573C` lesbar bleibt. Schriften Instrument Sans und IBM Plex Mono lokal aus @fontsource unter SIL OFL.
Abgrenzung: Änderungen nur in `web/` und `tests/test_web.py`; Backend, API, Disclosure und Tests der Fachlogik unverändert. Der Name `ehds_desk` und „EHDS Access Desk“ in Paketmetadaten, FastAPI-Titel und CLI-Beschreibung bleiben bewusst bestehen, weil der Auftrag Backendänderungen ausschloss.
Kosten: Anzahlwerte zeigen jetzt Tausendertrennzeichen in der UI; die API-Werte bleiben unverändert. Die Leiter zeigt dem Applicant Schritt-Titel und Status, aber keine Belegzitate.
