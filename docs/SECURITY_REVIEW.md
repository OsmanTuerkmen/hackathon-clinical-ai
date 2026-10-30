# Sicherheitsreview – EHDS Access Desk

Stand: 2026-10-30. Lokaler synthetischer Demo-Umfang; keine Produktionszertifizierung.

## Prüfstand und Verfahren

- Offizieller Anthropic-security-review-Workflow: statische Unteraufgabe über main..ab49365dc25dd931944c58af44935eabc56cec11 sowie abschließender Review des Task-14-Deltas (in c00827d committet). App- und UI-Code wurden durch Task 14 nicht geändert.
- Fokus auf konkret ausnutzbare High-/Medium-Befunde mit Confidence mindestens 0,8; Quellen/Senken und erreichbare Angriffswege. Keine aktiven Angriffe, Live-API-Aufrufe oder Patientenzeilen im Audit.
- Keine qualifizierten Kandidaten verblieben; deshalb waren keine separaten False-Positive-Filterunteraufgaben nötig.
- Testdateien und ausdrücklich dokumentierte Demo-Grenzen sind nach Workflowvorgaben von Sicherheitsbefunden ausgeschlossen. Funktionale Tests und Eval sind separat in WORKLOG/STATUS dokumentiert.

## Ergebnis

Keine konkret ausnutzbare High-/Medium-Schwachstelle im geprüften Stand festgestellt.

| Grenze | Geprüfter Schutz |
|---|---|
| SQL | Werte parametrisiert; Tabellen/Views/Aliase aus Whitelists oder interner Erzeugung |
| Pfade und SPE | eingeschränkte Permit-IDs; Vorschautabellen gegen Whitelist und Manifest; statische Dateien ausschließlich unter web/ |
| Download | keine Datensatzausgabe; protokollierter HTTP-403-Block |
| Browser | dynamische Texte als DOM-Textknoten/textContent, keine unsicheren HTML-Senken |
| Externer LLM | Payload nur freigegebener Antragstext, Codekatalog und Schema; kein Patientenzeilen-Pfad zum SDK |
| Opt-out/Disclosure | gefilterte Views für Statistik/SPE; zentrale Unterdrückung statistischer Ergebniszellen und Opt-out-Kennzahl |
| Codeausführung/Deserialisierung | keine erreichbare Command-, eval-, Pickle- oder unsichere YAML-Senke |
| Geheimnisse | keine eingebetteten Zugangsdaten im geprüften App-Code festgestellt |
| Extra-Evaluation | lokale stdlib-Referenzen und aggregierte Ausgaben, keine neue externe Übertragungsgrenze |

Ein Verdacht auf kleine Terminologie-Zeilenzahlen ließ sich für den gegebenen Datensatz nicht bestätigen. Eine ergänzende lokale Prüfung gab ausschließlich den Bool-Wert aus, dass keine positiven Code-Zeilenzahlen unter der Schwelle vorhanden sind; keine Codes, Zeilenzahlen oder Patientenkennungen wurden ausgegeben. Das ersetzt keine Prüfung anderer Datensätze.

## Grenzen

Die App ist eine lokale Demo ohne echte Authentifizierung, produktionsgehärtete SPE, sekundäre Unterdrückung oder vollständige rechtliche Einzelfallprüfung. Die ausdrücklich erlaubte SPE-Vorschau zeigt ausgewählte pseudonymisierte Datensätze innerhalb der App; ein blockierter Download-Endpunkt ist kein Schutz vor Kopieren aus einer realen Browser-/Betriebssystemumgebung. Bekannte Regex-Verneinungsfälle und ein konservativer englischer Parser sind im README zu benennen. Keine Aussage zu Produktionslast, Netzwerkhärtung oder Live-Claude-Verhalten. Ausschließlich synthetische Daten verwenden.

## Nachtrag zum Zwischenstand

Nach der oben beschriebenen statischen Sichtung hat der abschließende funktionale Gesamt-Review zwei konkrete SPE-Datenminimierungsfehler reproduziert: ausdrücklich verneinte Recordtypen blieben auswählbar; nachgestellte Messartenbeschränkungen konnten ohne LOINC-Filter bleiben. Beide sind in diesem Zwischenstand noch offen und verhindern den Projektabschluss. Nach der gebündelten Korrektur werden Regressionen und ein gezielter Sicherheits-/Funktionsnachreview dokumentiert. Die frühere Sichtung ist keine Entwarnung für diese später gefundenen Fälle.
