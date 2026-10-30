# Data flow and sovereignty

| What | Leaves the backend? | To whom | Where processed |
|---|---|---|---|
| Patient records (CSV, DuckDB) | Never | – | Backend host (Exoscale AT-VIE Vienna or a laptop) |
| Aggregate statistics after the small-cell rule | Yes, to the applicant | Applicant | Backend |
| Suppressed cells (`<10`, `suppressed`) | Only as `value: null` | Browser | – |
| SPE records | Never; download returns 403 | – | Per-permit DuckDB file on the backend |
| Request text: organisation, purpose, question | Only if the AI layer is on | Configured OpenAI-compatible endpoint | Self-hosted vLLM on the A1 Digital GPU in Vienna, or an EU provider |
| Code catalog (ICD-10/ATC/LOINC codes present in the data) | Only if the AI layer is on | Same endpoint | Same |
| Telemetry, fonts, CDN scripts | None | – | The UI bundles its fonts; no third-party requests |

Every model call is written to the hash-chained audit log (`cache/audit.jsonl`) with the model, endpoint host,
the fields sent and a SHA-256 of the payload. `tests/test_boundary.py` and the API tests assert that no
patient identifiers appear in outbound payloads or in client-visible suppressed cells.

With `EHDS_LLM_BASE_URL` unset, the whole system runs offline with rules only and still meets every track metric.
