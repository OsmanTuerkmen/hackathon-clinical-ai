# AccessDesk 2 – Plan

Stand 29.10.2026. Abgabe in weniger als 24 Stunden. Arbeitsordner `C:\Users\basre\Desktop\IBM_Hackathon\accessdesk2` (eigenes Git-Repo, ohne Datenordner).

## 1. Ziel

Eine automatisierte Datenzugangsstelle (Health Data Access Body) nach VO (EU) 2025/327, gebaut nach den Five Safes. Jede Anfrage bekommt eine Five-Safes-Übersicht, jeder Safe ist ein Modul. Die Metriken bleiben zu jedem Zeitpunkt auf Zielwert (10/10, 6/6, 0, 10/10, < 60 s). Die neue Architektur liefert auf allen Anfragen dieselben Zahlen wie der Prototyp.

## 2. Rahmen und Entscheidungen

| Thema | Entscheidung | Grund |
|---|---|---|
| Umfang | P0 + P1 komplett. Aus P2 sicher: Hash-Kette, Transparenzregister; Differenz-Schutz, wenn Zeit bleibt. Föderation wird nur als ADR beschrieben, nicht gebaut. P3: Story per Playwright aufnehmen | weniger als 24 h |
| Backend | Python 3.11, FastAPI 0.115, DuckDB 1.5.6, Pydantic 2 | DuckDB 2.0 ist ein Major-Release von vor 8 Tagen, 1.5.6 ist erprobt |
| Frontend | React 19, TypeScript, Vite 8, IBM Carbon 1.119 mit IBM Plex, Themes White und G100 | barrierefreie Tabellen, Modals und Tabs sind fertig, Tastaturbedienung ebenso, seriöser Look |
| Diagramme | eigenes SVG mit d3-scale, Karte mit d3-geo und lokalem GeoJSON | volle Kontrolle über die Schraffur verborgener Werte |
| Auslieferung | `web/dist` wird committet und von FastAPI ausgeliefert. Start mit `python3 start.py`: legt bei Bedarf `.venv` an, wählt einen freien Port (8000 ist belegt) und öffnet den Browser | Die Jury braucht nur Python |
| KI | optional über Claude (Anthropic SDK). Gesendet wird nur der Anfragetext, die Antworten werden pro Hash gecacht. Ohne Key gibt es einen sauberen Fallback | Die Metriken hängen nie von der KI ab |
| Installationen | nur projektlokal (`.venv`, `node_modules`). Playwright nutzt das installierte Chrome. Pakete müssen mindestens 7 Tage alt sein | nichts Globales |
| Deployment | keins, alles lokal | Daten bleiben lokal |

## 3. Architektur

```
request.json ──► FastAPI (accessdesk/api.py) ──► pipeline.py  (eine Anfrage, alle fünf Safes)
                                                   │
  Safe People    safes/people.py    eID, Register, Vollmacht, Ärztekammer (Ed25519, Fallback in reinem Python), Plausibilität
  Safe Projects  safes/projects.py  Art.-54-/Art.-53-Merkmale mit Belegstellen → feste Entscheidungsreihenfolge → Artikel
  Safe Data      plan/parser.py     Definitionen → QueryPlan (Pydantic, typisierte kleine Sprache)
                 plan/terminology.py  Begriff → ICD-10/ATC/LOINC (nur Codes, die in den Daten vorkommen)
                 plan/compiler.py   QueryPlan → DuckDB-SQL (Whitelists, Opt-out-Filter immer gesetzt)
                 safes/data.py      Opt-outs schon beim Laden entfernt, Kohorten-Trichter, Datenminimierung
  Safe Settings  safes/settings.py  SPE: eigene DuckDB-Datei pro Genehmigung, nur Kohorte und genannte Datenarten,
                                    SQL-Konsole nur lesend, Download → 403 und Protokolleintrag
  Safe Outputs   safes/outputs.py   Schleuse (einzige Funktion, die Zahlen freigibt), Leck-Prüfung,
                                    Ausgabeprüfung für SPE-Exporte, Differenz-Schutz (P2)
  audit.py   Prüfprotokoll als Hash-Kette (SHA-256 des vorigen Eintrags), Prüf-Endpunkt
  cases.py   Eingang: Status, Filter, Prüf-Aktionen mit Pflicht-Begründung
  letter.py  Bescheid-Daten DE/EN (Template, geprüfte Texte)
  ai.py      optional: Entwurf der Definitionen, Zweitmeinung zum Zweck, Begriff → Code (Enum)
web/  React + Carbon → dist/
```

Datenhaltung: Die CSVs werden beim Start in eine In-Memory-DuckDB geladen. Opt-outs (839) kommen dort gar nicht erst hinein, und jede Abfrage filtert zusätzlich auf `opted_out = false`. Messwerte werden exakt als Ganzzahl ×10 gespeichert, gerundet wird mit `Decimal` und ROUND_HALF_UP. Jede SPE ist eine eigene `runtime/spe/<Genehmigung>/workspace.duckdb`. Sie wird nur lesend geöffnet, mit `enable_external_access=false`, gesperrter Konfiguration und einer Whitelist für Anweisungen (nur SELECT/WITH).

## 4. Oberfläche (Carbon, DE/EN, hell/dunkel, ab 390 px)

- **Behörde**
  - Eingang mit Status (automatisch entschieden, Prüfung nötig, wegen Identität zurückgehalten, freigegeben), Filtern und Tastaturbedienung (j/k, Enter)
  - Fallansicht mit Five-Safes-Übersicht: markierte Textstellen, Ablauf der Regeln, Codes mit Zeilenanzahl, SQL und Protokoll der Schleuse
  - Prüf-Aktion mit Pflicht-Begründung, die ins Protokoll geht
  - Ausgabeprüfung, Prüfprotokoll mit Prüf-Knopf und die Auswertung der Metriken (live)
- **Antragsteller**
  - Antrags-Builder mit Live-Vorabprüfung: Begriff → Code mit Zeilenanzahl, geschützte Kohortengröße, Warnungen nach Art. 54, erwartetes Ergebnis
  - Meine Anträge mit Ergebnis: Österreich-Karte, Altersbalken und Trichter, verborgene Werte schraffiert
  - Bescheid, druckbar als PDF
  - SPE-Arbeitsbereich
- **Öffentlich:** Transparenzregister ohne sensible Details. Welcher Artikel die Veröffentlichung verlangt, wird gegen EUR-Lex geprüft, vermutlich Art. 57.
- **KI-Kennzeichnung:** Überall, wo KI beteiligt war, steht ein Hinweis, dazu was danach regelbasiert geprüft wurde.

## 5. Tests und Metriken

1. TDD in dieser Reihenfolge: Schleuse → Compiler → Parser, danach Entscheidung, Identität, SPE, Hash-Kette.
2. Regression, immer grün:
   - R01–R10 gegen `expected.json` (Zielwerte)
   - Golden-Test gegen die eingefrorenen Ausgaben des Prototyps für R01–R10 und D01–D04 (identische Zahlen)
   - eigene Anfragen T01–T12 gegen ein unabhängiges pandas-Orakel
3. Sicherheit: SQL-Injection über Codes, Dateizugriff aus der SPE-Konsole (`read_csv`, `COPY`, `ATTACH`, `INSTALL`), Schreibversuche, Download → 403.
4. E2E und Design: Playwright-Screenshots in 1440 und 390 px, jeweils hell und dunkel, dazu axe-Prüfung auf WCAG AA.

Eigene Testanfragen (Sollwerte unabhängig mit pandas berechnet):

| ID | Erwartet | Prüft |
|---|---|---|
| T01 | Statistik | stationäre Aufenthalte mit Hauptdiagnose Pneumonie (primary_icd10 J18) 2025, nach Klinikum |
| T02 | Statistik | Herzinsuffizienz nach Klinikum: Anzahl und mittlere eGFR |
| T03 | Statistik | Typ-2-Diabetes mit HbA1c-Wert, davon letzter HbA1c über 8, Anteil nach Bundesland |
| T04 | Statistik | Begriff ohne Code („a documented stroke diagnosis"), nach Altersgruppe |
| T05–T07 | REJECT | getarnte verbotene Zwecke: Markenkampagne, Kreditangebote, Personalauswahl |
| T08 | Statistik (53, 66, 69) | Zugangsantrag ohne Begründung (COPD, Inhalativa nach Altersgruppe) |
| T09 | SPE | Zugangsantrag mit Begründung, exakte Kohorte, nur die genannten Datenarten |
| T10 | Statistik | zwei Dimensionen: Vorhofflimmern nach Klinikum × Geschlecht |
| T11 | Statistik | viele kleine Zellen (fast alles „<10") |
| T12 | Statistik | Negation und aktive Medikation, Aufenthalte nach Jahr |

## 6. Meilensteine

Jeder Meilenstein endet mit grünen Tests, der Evaluation auf Zielwert, geprüften Screenshots (bei UI) und einem lokalen Commit.

| # | Inhalt |
|---|---|
| M1 | Gerüst, Golden-Daten und Orakel; Backend-Kern (Store, QueryPlan, Parser, Compiler, Schleuse, Entscheidung, Identität, SPE, Hash-Kette, Evaluation); identische Zahlen |
| M2 | FastAPI, Fall-Workflow, Bescheid-Daten, Register, SPE-Konsole mit Ausgabeprüfung, `start.py` |
| M3 | Design-Tokens und Komponenten, App-Shell, Eingang, Fallansicht |
| M4 | Antragsteller: Builder mit Vorabprüfung, Ergebnis mit Karte/Balken/Trichter, Bescheid mit Print-CSS |
| M5 | SPE-Arbeitsbereich, Ausgabeprüfung, Protokoll mit Prüf-Knopf, Register, Auswertung |
| M6 | 2 Runden Design-Critique und A11y, UX-Copy, DE/EN vollständig |
| M7 | Differenz-Schutz (P2, wenn Zeit bleibt); KI-Funktionen (live, sobald ein Key da ist) |
| M8 | README (Architekturdiagramm, Komponenten, Modelle/Dienste, Metriken, was geht und was nicht), DEMO.md, ADRs, Rechtsabgleich, Code- und Security-Review, Video-Aufnahme |

## 7. Risiken

- **Neue Formulierungen der Jury:** Dagegen stehen die Orakel-Tests T01–T12. Versteht der Parser etwas nicht, gibt es eine sichtbare Warnung und der Fall geht auf „Prüfung nötig". Mit Key schlägt die KI Codes aus der Enum vor.
- **Dateizugriff aus der DuckDB-Konsole:** Externer Zugriff ist aus, die Konfiguration gesperrt, die Datei nur lesend geöffnet, dazu eine Whitelist für Anweisungen und eigene Tests.
- **Windows-Dateisperren:** SPE-Verbindungen werden immer geschlossen, eine SPE wird pro Anfrage-Hash wiederverwendet.
- **Zeit:** Die Föderation ist gestrichen. Die Begründung steht im ADR: Alle Maße lassen sich zerlegen, und es gibt 0 Kontakte über Klinikgrenzen.

## 8. Offen

- Claude-Key: optional, bis dahin Fallback.
- Voiceover: eigene Stimme oder ElevenLabs, nur nach Zusage.
- Öffentliches GitHub-Repo: nur nach OK.
