# Abschließender Sicherheitsreview

Stand: 2026-10-30. Lokaler synthetischer Demo-Umfang; keine Produktionszertifizierung.

## Prüfverfahren und Stände

Offizieller Anthropic-security-review-Workflow mit statischer Unteraufgabe, Scope- und False-Positive-Ausschlüssen. Gesamtsichtung main..ab49365dc25dd931944c58af44935eabc56cec11, Task14-Delta sowie abschließender Parser-Delta gegen44200f9cf3b4f2551d301d6532258349ffc2f89d. Die finalen Korrekturen werden mit diesem Bericht committet. Keine aktiven Angriffe, Live-API-Aufrufe oder Patientenausgaben im Sicherheitsreview. Testdateien waren nach Skillvorgabe ausgeschlossen; funktionale Tests sind separat dokumentiert.

Im abschließenden Delta wurde keine neue konkret ausnutzbare High-/Medium-Schwachstelle mit Confidence mindestens 0,8 festgestellt. Keine neuen Kandidaten verblieben für eine separate False-Positive-Unteraufgabe. Das ist eine begrenzte statische Prüfung, keine umfassende Sicherheitsgarantie.

## Später funktional entdeckte und behobene Befunde

Die erste statische Sichtung hatte die folgenden funktionalen Fehler nicht erkannt; diese Einschränkung wird ausdrücklich festgehalten.

| Befund | Priorität | Abschließender Status |
|---|---|---|
| Ausdrücklich ausgeschlossene Recordtypen wurden ausgewählt | P1 | Closed: Typen aus Teil-Spec entfernt; unaufgelöste Ausschlüsse bleiben zwingend manuell |
| Nachgestellte/parenthetische Messbeschränkungen konnten entfallen | P1 | Closed: ganze Messungsanforderung geprüft, erkannte HbA1c-Formen auf 4548-4 begrenzt; Rest manuell |
| Zusätze nach cohort-size konnten eine größere Kohorte freigeben | P1 | Closed: vollständige Größenform erforderlich; inhaltliche Restbedingungen manuell |
| Gruppierungsqualifier wurden auf bekannte Dimensionen verkürzt | P2 | Closed: vollständiger Dimensionsausdruck; unverzichtbare manuelle Prüfung im Report- und Fragepfad |

ParseReport.complete berücksichtigt manual_review_required. parse_request beendet diese Fälle vor LLM-Übersetzung und Cache-Nutzung; das bestehende Pipeline-Gate gibt nur bei vollständiger Interpretation Statistik oder SPE frei. Ein breiterer schema-valider Fake-LLM kann die Pflichtmarkierung nicht aufheben. Der abschließende Funktionsnachreview bestätigt alle vier Befunde als behoben, zuletzt sechs Gruppierungspfade ohne LLM-Aufruf oder Daten-/SQL-Freigabe.

## Geprüfte Grenzen

- SQL-Werte sind parametrisiert; Tabellen/Views/Aliase aus Whitelists oder interner Erzeugung.
- Permit-IDs eingeschränkt, Vorschautabellen gegen Whitelist und Manifest; statische Dateien ausschließlich unter web/.
- Download-Endpunkt liefert keine Datensätze, sondern HTTP 403 und Audit.
- Dynamische UI-Texte als DOM-Textknoten/textContent; keine unsichere HTML-Senke gefunden.
- LLM-Payload nur freigegebene Antragstextfelder, Codekatalog und Schema; kein Patientenzeilen-Pfad zum SDK.
- Opt-out-gefilterte Views für Statistik und SPE; zentrale Disclosure für statistische Ergebniszellen und Opt-out-Kennzahl.
- Keine neu erreichbare Command-, eval-, Pickle-, unsichere YAML- oder Netzwerksenke; keine eingebetteten Zugangsdaten im geprüften App-Code festgestellt.
- Ein Terminologie-Metadatenverdacht wurde im gegebenen Datensatz nicht als Small-Cell-Leak bestätigt. Eine ergänzende lokale Bool-Prüfung gab ausschließlich false für positiveCodeCounts<10 aus, ohne Codes, Counts oder Patientenkennungen auszugeben.

## Separate dynamische Nachweise

702 pytest-Tests bestanden; darunter 86 neue Release-Gate-Regressionen. Unabhängige CSV-Referenz 14/14; echter Drei-Lauf-Eval über 20 Requests/60 POSTs mit 0 detektierten Leaks.133 Edge-Browserchecks einschließlich Desktop/375px, beiden SPEs,403/Audit, Init-Race und XSS. Diese Nachweise ergänzen den statischen Review und sind keine von dessen Agenten wiederholten Tests.

## Verbleibende Demo-Grenzen

Keine echte Auth/Rollentrennung oder gehärtete SPE. Vorschau und lokale Dateien sind in einer realen Browser-/Betriebssystemumgebung kopierbar. Keine sekundäre Unterdrückung/Differenzsicherung. Konservativer englischer Parser, bekannte Art54-Regex-Verneinungsfälle; kein allgemeines Sprachverständnis oder vollständige rechtliche Einzelfallprüfung. Kein Live-Claude-, Produktionslast- oder Netzwerkhärtungsnachweis. Ausschließlich synthetische Daten verwenden.
