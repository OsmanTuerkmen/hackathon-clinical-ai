# DuckDB instead of SQLite

The prototype used an in-memory SQLite database. AccessDesk 2 uses DuckDB (1.5.6, not the 8-day-old 2.0) for the analysis store and for every secure processing environment. There are three reasons:

1. DuckDB loads the CSVs with explicit types, and it runs the analytical, CTE-heavy queries the compiler generates.
2. A permit's workspace is a single file. It is built inside the analysis connection with `ATTACH`, so no data passes through Python.
3. The workspace can be opened read-only with `enable_external_access=false`, no extension loading and `lock_configuration=true`.

Point 3 decides it. The SPE SQL console runs queries the applicant wrote, and DuckDB's file readers (`read_csv`, `COPY … TO`, `ATTACH`) would otherwise let a query reach the source CSVs. SQLite has no comparable switch.

## Consequences

- Within one process, DuckDB refuses a second connection to the same file with a different configuration, and Windows locks open files. Every SPE connection is therefore opened through `settings.readonly()` and closed right away. Workspaces are created once per request hash and then reused.
- Numbers stay identical to the prototype. Values are stored as exact integers ×10, and rounding is done in Python with `Decimal` and ROUND_HALF_UP. The golden test against the frozen prototype output enforces this.
