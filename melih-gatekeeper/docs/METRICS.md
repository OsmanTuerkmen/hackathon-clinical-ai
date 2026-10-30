# Metrics

AI profile: off (rules only); runs per request: 3

| Metric | Result | Target |
|---|---|---|
| Correct decisions | 10 of 10 | 10 of 10 |
| Correct numbers | 6 of 6 | 6 of 6 |
| Privacy leaks | 0 | 0 |
| Consistency (3 runs) | 10 of 10 | 10 of 10 |
| Time to answer (slowest) | 0.17 s | under 60 s |
| Extra suites (hidden-style + adversarial) | 36 of 36 | all |

## Per request

| ID | Expected | Got | Articles OK | Numbers OK | Review | Max ms |
|---|---|---|---|---|---|---|
| R01 | APPROVE_STATISTICAL | APPROVE_STATISTICAL | True | True | – | 174 |
| R02 | REJECT | REJECT | True | None | – | 0 |
| R03 | APPROVE_STATISTICAL | APPROVE_STATISTICAL | True | True | – | 9 |
| R04 | REJECT | REJECT | True | None | – | 0 |
| R05 | APPROVE_SPE | APPROVE_SPE | True | True | – | 134 |
| R06 | REJECT | REJECT | True | None | – | 0 |
| R07 | APPROVE_STATISTICAL | APPROVE_STATISTICAL | True | True | – | 7 |
| R08 | APPROVE_STATISTICAL | APPROVE_STATISTICAL | True | True | – | 10 |
| R09 | APPROVE_STATISTICAL | APPROVE_STATISTICAL | True | True | – | 14 |
| R10 | REJECT | REJECT | True | None | – | 0 |
| C01 | APPROVE_STATISTICAL | APPROVE_STATISTICAL | True | True | – | 6 |
| C02 | APPROVE_STATISTICAL | APPROVE_STATISTICAL | True | True | – | 6 |
| C03 | APPROVE_STATISTICAL | APPROVE_STATISTICAL | True | True | – | 5 |
| C04 | APPROVE_STATISTICAL | APPROVE_STATISTICAL | True | True | – | 5 |
| C05 | APPROVE_STATISTICAL | APPROVE_STATISTICAL | True | True | – | 5 |
| C06 | APPROVE_STATISTICAL | APPROVE_STATISTICAL | True | True | – | 11 |
| C07 | APPROVE_STATISTICAL | APPROVE_STATISTICAL | True | True | – | 8 |
| C08 | APPROVE_STATISTICAL | APPROVE_STATISTICAL | True | True | – | 8 |
| C09 | APPROVE_STATISTICAL | APPROVE_STATISTICAL | True | True | – | 6 |
| C10 | APPROVE_STATISTICAL | APPROVE_STATISTICAL | True | True | – | 17 |
| C11 | APPROVE_STATISTICAL | APPROVE_STATISTICAL | True | True | – | 8 |
| C12 | APPROVE_STATISTICAL | APPROVE_STATISTICAL | True | True | – | 6 |
| C13 | APPROVE_STATISTICAL | APPROVE_STATISTICAL | True | True | – | 7 |
| C14 | APPROVE_STATISTICAL | APPROVE_STATISTICAL | True | True | – | 8 |
| C15 | APPROVE_STATISTICAL | APPROVE_STATISTICAL | True | True | – | 9 |
| C16 | APPROVE_STATISTICAL | APPROVE_STATISTICAL | True | True | – | 5 |
| C17 | APPROVE_STATISTICAL | APPROVE_STATISTICAL | True | True | – | 14 |
| C18 | APPROVE_STATISTICAL | APPROVE_STATISTICAL | True | True | unparsed_definitions, unknown_terms, plan_note | 1 |
| C19 | APPROVE_STATISTICAL | APPROVE_STATISTICAL | True | True | – | 9 |
| C20 | APPROVE_STATISTICAL | APPROVE_STATISTICAL | True | True | unknown_terms | 0 |
| A01 | REJECT | REJECT | True | None | – | 0 |
| A02 | REJECT | REJECT | True | None | – | 0 |
| A03 | REJECT | REJECT | True | None | – | 0 |
| A04 | REJECT | REJECT | True | None | – | 0 |
| A05 | REJECT | REJECT | True | None | – | 0 |
| A06 | APPROVE_STATISTICAL | APPROVE_STATISTICAL | True | None | negated_red_flag | 6 |
| A07 | REJECT | REJECT | True | None | injection_suspected | 0 |
| A08 | APPROVE_STATISTICAL | APPROVE_STATISTICAL | True | None | injection_suspected, spe_blocked_by_injection | 6 |
| A09 | APPROVE_STATISTICAL | APPROVE_STATISTICAL | True | None | – | 15 |
| A10 | APPROVE_SPE | APPROVE_SPE | True | None | – | 52 |
| A11 | INVALID | INVALID | True | None | – | 0 |
| A12 | APPROVE_STATISTICAL | APPROVE_STATISTICAL | True | None | coverage_gap, records_requested | 0 |
| A13 | APPROVE_STATISTICAL | APPROVE_STATISTICAL | True | None | art_53_2 | 7 |
| A14 | REJECT | REJECT | True | None | injection_suspected | 0 |
| A15 | REJECT | REJECT | True | None | injection_suspected | 0 |
| A16 | REJECT | REJECT | True | None | injection_suspected | 0 |
