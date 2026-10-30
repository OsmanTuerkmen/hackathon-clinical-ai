# Evaluation results

Datum: 2026-10-30T03:25:08+01:00 (Europe/Vienna)
Git-Commit: `0e9ebf086547e384d15745764261c8ffac88d1e8`

LLM-Modus: **off**, API-Key ausdrücklich **None**. Originaldaten/Requests/expected bleiben extern.
Runtime: eigener Unterordner `settings.var_dir/eval`; FastAPI TestClient, Service vor Messbeginn initialisiert.
Drei vollständige Läufe, 30 POSTs. Entscheidungen, Zahlen und Leaks prüfen alle drei Läufe; Konsistenz vergleicht ausschließlich das vollständige Applicant-JSON. Zeiten messen POST bis Antwort einschließlich SPE-Provisionierung.

| Metrik | Ergebnis | Ziel | Status |
|---|---|---|---|
| Correct decisions | 10/10 | 10/10 | ✅ |
| Correct numbers | 6/6 | 6/6 | ✅ |
| Privacy leaks (all runs) | 0 | 0 | ✅ |
| Consistency (applicant JSON) | 10/10 | 10/10 | ✅ |
| Time to answer (slowest HTTP run) | 0.506 s | < 60 s | ✅ |

## Je Antrag

| Request | Decision expected / actual | Articles expected / actual | Numbers (3/3) | Leaks (3 runs) | Consistent | Max HTTP ms |
|---|---|---|---|---:|---|---:|
| R01 | APPROVE_STATISTICAL / APPROVE_STATISTICAL | 53, 69 / 53, 69, 71 | PASS | 0 | PASS | 43.3 |
| R02 | REJECT / REJECT | 54 / 54 | — | 0 | PASS | 6.6 |
| R03 | APPROVE_STATISTICAL / APPROVE_STATISTICAL | 53, 69 / 53, 69, 71 | PASS | 0 | PASS | 34.6 |
| R04 | REJECT / REJECT | 54 / 54 | — | 0 | PASS | 5.5 |
| R05 | APPROVE_SPE / APPROVE_SPE | 53, 66, 68, 73 / 53, 66, 68, 73, 71 | PASS | 0 | PASS | 506.2 |
| R06 | REJECT / REJECT | 54 / 54 | — | 0 | PASS | 6.5 |
| R07 | APPROVE_STATISTICAL / APPROVE_STATISTICAL | 53, 69 / 53, 69, 71 | PASS | 0 | PASS | 35.3 |
| R08 | APPROVE_STATISTICAL / APPROVE_STATISTICAL | 53, 69 / 53, 69, 71 | PASS | 0 | PASS | 43.5 |
| R09 | APPROVE_STATISTICAL / APPROVE_STATISTICAL | 53, 66, 69 / 53, 66, 69, 71 | PASS | 0 | PASS | 50.4 |
| R10 | REJECT / REJECT | 54 / 54 | — | 0 | PASS | 6.7 |

## Unabhängige Referenz

`eval/reference.py` liest die fünf Original-CSVs nur mit der Standardbibliothek. Eigene Kohorten, aktive Medikation, letzte Messung, ROUND_HALF_UP und Suppression; keine App-/DuckDB-/Pydantic-Imports.

| Request | CSV-Referenz vs. externes expected.json |
|---|---|
| R01 | PASS |
| R03 | PASS |
| R05 | PASS |
| R07 | PASS |
| R08 | PASS |
| R09 | PASS |

Datenschutz-Gegenprobe: Patientenkennungen in Schlüsseln und Werten der gesamten regulären Antwort; Patientenfelder/unerwartete Records; kleine Countzellen auch als Float/String; Prozent/Mittelwerte gegen Rohzähler, -nenner und n aus `run_statistics(staff.spec)`. Alle consented Views werden gegen die unabhängige Opt-out-Menge geprüft. SPE-Kohorte und sämtliche kopierten Records werden mit der unabhängigen CSV-Auswahl einschließlich Multiplizität verglichen. Dabei werden keine Patientenzeilen oder IDs ausgegeben.

## Eigene Anträge (Task 14)

Noch nicht vorhanden; keine erfundenen Ergebnisse. Hooks: `EXTRA_REFERENCES`, `SPE_REFERENCES` und automatisches Laden von `requests/extra/expected.json` samt Requests. Fehlende Referenzen genehmigter Extra-Anträge führen nach Hinzufügen zum Fehlschlag.

## Grenzen

Offline-TestClient-Messung auf dem lokalen synthetischen Datensatz; keine Live-LLM-, Netzwerk-, Authentifizierungs- oder Produktionslastmessung. Primäre Small-Cell-Regel; sekundäre Unterdrückung bleibt außerhalb des App-Umfangs. Exakte SPE-Patienten-/Tabellenzahlen sind gemäß Projektregel von statistischer Small-Cell-Unterdrückung ausgenommen.
