# Evaluation results

Datum: 2026-10-30T03:53:18+01:00 (Europe/Vienna)
Git-Commit: `c00827ddef6946ef1b6b8c1db2dba8f71feea8bd`

LLM-Modus: **off**, API-Key ausdrücklich **None**. Originaldaten/Requests/expected bleiben extern.
Runtime: eigener Unterordner `settings.var_dir/eval`; FastAPI TestClient, Service vor Messbeginn initialisiert.
Drei vollständige Läufe, 30 POSTs. Entscheidungen, Zahlen und Leaks prüfen alle drei Läufe; Konsistenz vergleicht ausschließlich das vollständige Applicant-JSON. Zeiten messen POST bis Antwort einschließlich SPE-Provisionierung.

| Metrik | Ergebnis | Ziel | Status |
|---|---|---|---|
| Correct decisions | 10/10 | 10/10 | ✅ |
| Correct numbers | 6/6 | 6/6 | ✅ |
| Privacy leaks (all runs) | 0 | 0 | ✅ |
| Consistency (applicant JSON) | 10/10 | 10/10 | ✅ |
| Time to answer (slowest HTTP run) | 0.527 s | < 60 s | ✅ |

## Je Antrag

| Request | Decision expected / actual | Articles expected / actual | Numbers (3/3) | Leaks (3 runs) | Consistent | Max HTTP ms |
|---|---|---|---|---:|---|---:|
| R01 | APPROVE_STATISTICAL / APPROVE_STATISTICAL | 53, 69 / 53, 69, 71 | PASS | 0 | PASS | 43.0 |
| R02 | REJECT / REJECT | 54 / 54 | — | 0 | PASS | 6.4 |
| R03 | APPROVE_STATISTICAL / APPROVE_STATISTICAL | 53, 69 / 53, 69, 71 | PASS | 0 | PASS | 37.1 |
| R04 | REJECT / REJECT | 54 / 54 | — | 0 | PASS | 6.5 |
| R05 | APPROVE_SPE / APPROVE_SPE | 53, 66, 68, 73 / 53, 66, 68, 73, 71 | PASS | 0 | PASS | 527.4 |
| R06 | REJECT / REJECT | 54 / 54 | — | 0 | PASS | 6.0 |
| R07 | APPROVE_STATISTICAL / APPROVE_STATISTICAL | 53, 69 / 53, 69, 71 | PASS | 0 | PASS | 33.7 |
| R08 | APPROVE_STATISTICAL / APPROVE_STATISTICAL | 53, 69 / 53, 69, 71 | PASS | 0 | PASS | 45.8 |
| R09 | APPROVE_STATISTICAL / APPROVE_STATISTICAL | 53, 66, 69 / 53, 66, 69, 71 | PASS | 0 | PASS | 45.9 |
| R10 | REJECT / REJECT | 54 / 54 | — | 0 | PASS | 6.9 |

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

Drei vollständige Läufe, 30 Extra-POSTs.

| Metrik | Ergebnis | Ziel | Status |
|---|---|---|---|
| Correct decisions | 10/10 | 10/10 | ✅ |
| Correct numbers | 8/8 | 8/8 | ✅ |
| Privacy leaks (all runs) | 0 | 0 | ✅ |
| Consistency (applicant JSON) | 10/10 | 10/10 | ✅ |
| Time to answer (slowest HTTP run) | 0.202 s | < 60 s | ✅ |

| Request | Decision expected / actual | Articles expected / actual | Numbers (3/3) | Leaks (3 runs) | Consistent | Max HTTP ms |
|---|---|---|---|---:|---|---:|
| N01 | APPROVE_STATISTICAL / APPROVE_STATISTICAL | 53, 69 / 53, 69, 71 | PASS | 0 | PASS | 29.9 |
| N02 | APPROVE_STATISTICAL / APPROVE_STATISTICAL | 53, 69 / 53, 69, 71 | PASS | 0 | PASS | 39.2 |
| N03 | APPROVE_STATISTICAL / APPROVE_STATISTICAL | 53, 69 / 53, 69, 71 | PASS | 0 | PASS | 34.1 |
| N04 | REJECT / REJECT | 54 / 54 | — | 0 | PASS | 5.2 |
| N05 | APPROVE_STATISTICAL / APPROVE_STATISTICAL | 53, 69 / 53, 69, 71 | PASS | 0 | PASS | 24.8 |
| N06 | APPROVE_SPE / APPROVE_SPE | 53, 66, 68, 73 / 53, 66, 68, 73, 71 | PASS | 0 | PASS | 202.0 |
| N07 | APPROVE_STATISTICAL / APPROVE_STATISTICAL | 53, 69 / 53, 69, 71 | PASS | 0 | PASS | 86.9 |
| N08 | APPROVE_STATISTICAL / APPROVE_STATISTICAL | 53, 66, 69 / 53, 66, 69, 71 | PASS | 0 | PASS | 35.7 |
| N09 | REJECT / REJECT | 54 / 54 | — | 0 | PASS | 4.3 |
| N10 | APPROVE_STATISTICAL / APPROVE_STATISTICAL | 53, 69 / 53, 69, 71 | PASS | 0 | PASS | 41.4 |

| Request | Unabhängige Extra-CSV-Referenz |
|---|---|
| N01 | PASS |
| N02 | PASS |
| N03 | PASS |
| N05 | PASS |
| N06 | PASS |
| N07 | PASS |
| N08 | PASS |
| N10 | PASS |

## Grenzen

Offline-TestClient-Messung auf dem lokalen synthetischen Datensatz; keine Live-LLM-, Netzwerk-, Authentifizierungs- oder Produktionslastmessung. Primäre Small-Cell-Regel; sekundäre Unterdrückung bleibt außerhalb des App-Umfangs. Exakte SPE-Patienten-/Tabellenzahlen sind gemäß Projektregel von statistischer Small-Cell-Unterdrückung ausgenommen.
