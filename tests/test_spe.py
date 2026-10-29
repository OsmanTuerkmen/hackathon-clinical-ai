import json
from pathlib import Path

import pytest

from accessdesk.safes import settings


def _request(data_dir):
    path = Path(data_dir).parent / "requests" / "R05.json"
    with path.open(encoding="utf-8") as stream:
        return json.load(stream)


def _spe_result(data_dir, desk):
    return desk.process(_request(data_dir), use_cache=False)


def test_spe_contains_only_r05_cohort_and_named_records(data_dir, desk):
    result = _spe_result(data_dir, desk)
    manifest = result["spe"]
    assert manifest["cohort_size"] == 1152
    assert [item["table"] for item in manifest["tables_copied"]] == [
        "conditions", "medications", "observations",
    ]
    assert manifest["tables_not_copied"] == ["encounters", "patients"]
    assert manifest["tables_copied"][-1]["note"] == "only 4548-4"

    connection = settings.open_readonly(
        Path(desk.root) / manifest["location"]
    )
    try:
        cohort = {
            row[0] for row in connection.execute("SELECT patient_id FROM cohort").fetchall()
        }
        assert len(cohort) == 1152
        for table in ("conditions", "medications", "observations"):
            ids = {
                row[0] for row in connection.execute(
                    f"SELECT DISTINCT patient_id FROM {table}"
                ).fetchall()
            }
            assert ids <= cohort
            assert ids.isdisjoint(desk.store.opted_ids)
        assert connection.execute(
            "SELECT DISTINCT loinc FROM observations"
        ).fetchall() == [("4548-4",)]
    finally:
        connection.close()


def test_spe_manifest_is_reused_for_the_same_request(data_dir, desk):
    first = _spe_result(data_dir, desk)["spe"]
    second = _spe_result(data_dir, desk)["spe"]
    assert second == first
    assert first["permit_id"].startswith("DP-R05-")
    assert first["location"].replace("\\", "/").endswith("/workspace.duckdb")
    assert len(first["request_hash"]) == 64


def test_read_only_console_can_query_the_cohort(data_dir, desk):
    result = _spe_result(data_dir, desk)
    answer = settings.console_query(
        desk.root, result["spe"]["permit_id"], "SELECT patient_id FROM cohort", limit=4,
    )
    assert answer["columns"] == ["patient_id"]
    assert len(answer["rows"]) == 4
    assert answer["row_count"] == 4
    assert answer["truncated"]


def test_preview_and_blocked_download_audit(data_dir, desk):
    result = _spe_result(data_dir, desk)
    preview = settings.preview(desk.root, result["spe"]["permit_id"], limit=2)
    assert preview["manifest"]["permit_id"] == result["spe"]["permit_id"]
    assert list(preview["tables"]) == ["conditions", "medications", "observations"]
    assert all(len(table["rows"]) == 2 for table in preview["tables"].values())

    settings.log_blocked_download(desk.audit, result["id"])
    entry = desk.audit.tail(1)[0]
    assert entry["action"] == "download_blocked"
    assert entry["request_id"] == result["id"]


def test_read_only_console_rejects_filesystem_and_mutating_sql(data_dir, desk):
    result = _spe_result(data_dir, desk)
    permit_id = result["spe"]["permit_id"]
    patient_csv = (Path(data_dir) / "patients.csv").resolve().as_posix().replace("'", "''")
    rejected = [
        f"SELECT * FROM read_csv('{patient_csv}')",
        f"WITH source AS (SELECT * FROM read_csv('{patient_csv}')) SELECT * FROM source",
        "COPY cohort TO 'outside.csv'",
        "ATTACH 'outside.duckdb' AS other",
        "CREATE TABLE other (id INTEGER)",
        "INSERT INTO cohort VALUES ('p-test')",
        "DROP TABLE cohort",
        "INSTALL httpfs",
        "LOAD httpfs",
        "SET enable_external_access=true",
        "SELECT 1; DROP TABLE cohort",
        "PRAGMA database_list",
        "CALL read_csv('patients.csv')",
        "SELECT * FROM read_text('secret.txt')",
        "SELECT * FROM glob('*')",
    ]
    for sql in rejected:
        with pytest.raises(settings.ConsoleError, match="."):
            settings.console_query(desk.root, permit_id, sql)
