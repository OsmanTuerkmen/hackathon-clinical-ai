import json
import re
import threading

import duckdb
import pytest
import specs

from ehds_desk import spe
from ehds_desk.engine import cohort_patient_ids
from ehds_desk.models import AccessRequest, Applicant, QuerySpec


def make_request(rid: str = "R05", purpose: str = "Research on diabetes") -> AccessRequest:
    return AccessRequest(
        id=rid,
        applicant=Applicant(name="Dr. Test", organisation="Test University"),
        requested_as="data access application",
        purpose=purpose,
        question="Provide pseudonymised records.",
        definitions=[],
    )


def _query(var_dir, permit_id, sql):
    con = duckdb.connect(str(var_dir / "spe" / permit_id / "spe.duckdb"), read_only=True)
    try:
        return con.execute(sql).fetchall()
    finally:
        con.close()


@pytest.fixture
def r05_manifest(db, tmp_path):
    return spe.provision_spe(make_request(), specs.r05(), db, tmp_path)


def test_r05_spe_contents(db, tmp_path, r05_manifest):
    m = r05_manifest
    cohort = set(cohort_patient_ids(specs.r05(), db))
    assert m.patient_count == 1152
    assert set(m.tables) == {"cohort", "conditions", "medications", "observations"}
    assert "encounters" not in m.tables
    assert "patients" not in m.tables
    assert m.tables["cohort"] == 1152
    assert {r[0] for r in _query(tmp_path, m.permit_id, "SELECT DISTINCT loinc FROM observations")} == {"4548-4"}
    for table in m.tables:
        ids = {r[0] for r in _query(tmp_path, m.permit_id, f"SELECT DISTINCT patient_id FROM {table}")}
        assert ids <= cohort, table
        assert m.tables[table] == _query(tmp_path, m.permit_id, f"SELECT count(*) FROM {table}")[0][0]
    assert m.articles == ["53", "66", "68", "73", "71"]
    assert m.observation_codes == ["4548-4"]
    assert m.record_types == ["conditions", "medications", "observations"]


def test_patients_table_has_no_opted_out_or_age(db, tmp_path):
    spec = QuerySpec(population=specs.r05().population, output="cohort_size", record_types=["patients"])
    m = spe.provision_spe(make_request("R98"), spec, db, tmp_path)
    assert set(m.tables) == {"cohort", "patients"}
    assert m.tables["patients"] == m.patient_count
    cols = [r[0] for r in _query(tmp_path, m.permit_id, "DESCRIBE patients")]
    assert cols == ["patient_id", "sex", "birth_date", "region", "data_holder"]


def test_spe_contains_no_opted_out_patients(db, tmp_path):
    # population without a condition filter so that opted-out patients would match if not filtered
    spec = QuerySpec(
        population=[specs.ADULT],
        output="cohort_size",
        record_types=["patients", "conditions", "medications", "observations", "encounters"],
    )
    m = spe.provision_spe(make_request("R97"), spec, db, tmp_path)
    opted_out = {r[0] for r in db.cursor().execute("SELECT patient_id FROM raw_patients WHERE opted_out").fetchall()}
    assert opted_out
    assert set(m.tables) == {"cohort", "patients", "conditions", "medications", "observations", "encounters"}
    for table in m.tables:
        ids = {r[0] for r in _query(tmp_path, m.permit_id, f"SELECT DISTINCT patient_id FROM {table}")}
        assert not (ids & opted_out), table


def test_encounters_record_type_copies_encounters(db, tmp_path):
    spec = QuerySpec(population=specs.r05().population, output="cohort_size", record_types=["encounters"])
    m = spe.provision_spe(make_request("R99"), spec, db, tmp_path)
    assert set(m.tables) == {"cohort", "encounters"}
    assert m.tables["encounters"] > 0
    assert m.observation_codes == []
    cohort = set(cohort_patient_ids(spec, db))
    ids = {r[0] for r in _query(tmp_path, m.permit_id, "SELECT DISTINCT patient_id FROM encounters")}
    assert ids <= cohort


def test_download_is_blocked_and_audited(r05_manifest, tmp_path):
    pid = r05_manifest.permit_id
    event = spe.attempt_download(pid, "conditions", tmp_path)
    assert event.action == "download_blocked"
    assert event.table == "conditions"
    assert event.actor == "applicant"
    assert "Art. 73(2)" in event.detail
    actions = [e.action for e in spe.audit_log(pid, tmp_path)]
    assert "provisioned" in actions
    assert "download_blocked" in actions


def test_preview_returns_limited_rows_and_is_logged(r05_manifest, tmp_path):
    pid = r05_manifest.permit_id
    rows = spe.preview(pid, "conditions", tmp_path)
    assert 0 < len(rows) <= 20
    assert "patient_id" in rows[0]
    assert len(spe.preview(pid, "conditions", tmp_path, limit=3)) == 3
    assert [e.action for e in spe.audit_log(pid, tmp_path)].count("preview") == 2


def test_preview_limit_is_bounded(r05_manifest, tmp_path):
    rows = spe.preview(r05_manifest.permit_id, "cohort", tmp_path, limit=10_000)
    assert len(rows) <= 20


def test_invalid_permit_id_rejected(tmp_path):
    for bad in ("../x", "a/b", "a\\b", "", "x y", ".."):
        with pytest.raises(spe.InvalidPermitId):
            spe.load_manifest(bad, tmp_path)
        with pytest.raises(spe.InvalidPermitId):
            spe.attempt_download(bad, "cohort", tmp_path)
        with pytest.raises(spe.InvalidPermitId):
            spe.audit_log(bad, tmp_path)


def test_unknown_permit_not_found(tmp_path):
    with pytest.raises(spe.SpeNotFound):
        spe.load_manifest("R05-deadbeef", tmp_path)


def test_unknown_table_rejected(r05_manifest, tmp_path):
    pid = r05_manifest.permit_id
    for bad in ("raw_patients", "conditions; DROP TABLE cohort", "../x", "pat_all"):
        with pytest.raises(ValueError):
            spe.preview(pid, bad, tmp_path)
        with pytest.raises(ValueError):
            spe.attempt_download(pid, bad, tmp_path)
    # whitelisted but not part of this SPE's manifest
    with pytest.raises(ValueError):
        spe.preview(pid, "encounters", tmp_path)
    with pytest.raises(ValueError):
        spe.attempt_download(pid, "encounters", tmp_path)


def test_provision_twice_is_idempotent(db, tmp_path):
    first = spe.provision_spe(make_request(), specs.r05(), db, tmp_path)
    second = spe.provision_spe(make_request(), specs.r05(), db, tmp_path)
    assert first == second
    assert spe.load_manifest(first.permit_id, tmp_path) == first
    # the audit log is append-only: both runs are recorded
    assert [e.action for e in spe.audit_log(first.permit_id, tmp_path)].count("provisioned") == 2


def test_manifest_json_has_no_timestamps(r05_manifest, tmp_path):
    raw = (tmp_path / "spe" / r05_manifest.permit_id / "manifest.json").read_text(encoding="utf-8")
    assert set(json.loads(raw)) == {
        "permit_id",
        "request_id",
        "patient_count",
        "tables",
        "record_types",
        "observation_codes",
        "articles",
    }


def test_permit_id_format_and_stability():
    a = spe.permit_id_for(make_request())
    assert a == spe.permit_id_for(make_request())
    assert a != spe.permit_id_for(make_request(purpose="Something else"))
    assert re.fullmatch(r"R05-[0-9a-f]{8}", a)
    assert re.fullmatch(r"[A-Za-z0-9_-]+", spe.permit_id_for(make_request("a/../b")))


def test_audit_event_fields(r05_manifest, tmp_path):
    ev = spe.audit_log(r05_manifest.permit_id, tmp_path)[0]
    assert ev.action == "provisioned"
    assert ev.permit_id == r05_manifest.permit_id
    assert ev.timestamp.endswith("+00:00")


def test_concurrent_provisions_of_different_permits(db, tmp_path):
    results: dict[str, object] = {}

    def run(rid: str) -> None:
        try:
            results[rid] = spe.provision_spe(make_request(rid), specs.r05(), db, tmp_path)
        except Exception as exc:  # noqa: BLE001 - surfaced by the assertion below
            results[rid] = exc

    threads = [threading.Thread(target=run, args=(rid,)) for rid in ("C1", "C2", "C3", "C4")]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert all(isinstance(m, spe.SpeManifest) for m in results.values()), results
    assert len({m.permit_id for m in results.values()}) == 4
    assert all(m.patient_count == 1152 for m in results.values())


def test_concurrent_provisions_of_same_permit(db, tmp_path):
    errors: list[Exception] = []

    def run() -> None:
        try:
            spe.provision_spe(make_request("SAME"), specs.r05(), db, tmp_path)
        except Exception as exc:  # noqa: BLE001
            errors.append(exc)

    threads = [threading.Thread(target=run) for _ in range(3)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert not errors


def test_failed_reprovision_leaves_no_stale_manifest(db, tmp_path, monkeypatch):
    m = spe.provision_spe(make_request(), specs.r05(), db, tmp_path)

    def boom(*args, **kwargs):
        raise RuntimeError("cohort failure")

    monkeypatch.setattr(spe, "cohort_patient_ids", boom)
    with pytest.raises(RuntimeError):
        spe.provision_spe(make_request(), specs.r05(), db, tmp_path)
    with pytest.raises(spe.SpeNotFound):
        spe.load_manifest(m.permit_id, tmp_path)


def test_download_of_unknown_table_is_audited_and_raises(r05_manifest, tmp_path):
    pid = r05_manifest.permit_id
    for bad in ("raw_patients", "encounters"):
        with pytest.raises(ValueError):
            spe.attempt_download(pid, bad, tmp_path)
    events = [e for e in spe.audit_log(pid, tmp_path) if e.action == "download_blocked"]
    assert len(events) == 2
    assert all(e.table is None or e.table in spe.TABLE_WHITELIST for e in events)
    assert all("blocked" in e.detail for e in events)


def test_copy_filters_opted_out_even_if_cohort_contains_them(db, tmp_path, monkeypatch):
    opted_out = [
        r[0] for r in db.cursor().execute("SELECT patient_id FROM raw_patients WHERE opted_out LIMIT 5").fetchall()
    ]
    consented = cohort_patient_ids(specs.r05(), db)[:5]
    assert opted_out
    monkeypatch.setattr(spe, "cohort_patient_ids", lambda spec, database: consented + opted_out)
    spec = QuerySpec(
        population=[specs.ADULT],
        output="cohort_size",
        record_types=["patients", "conditions", "medications", "observations", "encounters"],
    )
    m = spe.provision_spe(make_request("OPT"), spec, db, tmp_path)
    assert m.patient_count == len(consented)
    for table in m.tables:
        ids = {r[0] for r in _query(tmp_path, m.permit_id, f"SELECT DISTINCT patient_id FROM {table}")}
        assert not (ids & set(opted_out)), table
        assert ids <= set(consented), table


def test_r05_row_counts_equal_source_counts(db, tmp_path, r05_manifest):
    cohort = cohort_patient_ids(specs.r05(), db)
    cur = db.cursor()
    try:
        cur.execute("CREATE TEMP TABLE t_cohort (patient_id VARCHAR)")
        cur.executemany("INSERT INTO t_cohort VALUES (?)", [[p] for p in cohort])
        sub = "patient_id IN (SELECT patient_id FROM t_cohort)"
        expected = {
            "conditions": cur.execute(f"SELECT count(*) FROM cond WHERE {sub}").fetchone()[0],
            "medications": cur.execute(f"SELECT count(*) FROM med WHERE {sub}").fetchone()[0],
            "observations": cur.execute(f"SELECT count(*) FROM obs WHERE loinc = '4548-4' AND {sub}").fetchone()[0],
        }
    finally:
        cur.close()
    for table, n in expected.items():
        assert n > 0
        assert r05_manifest.tables[table] == n, table
