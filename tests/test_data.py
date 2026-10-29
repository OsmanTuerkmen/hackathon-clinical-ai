from datetime import date

from ehds_desk import config
from ehds_desk.config import load_settings
from ehds_desk.data import REGIONS, SEXES


def scalar(db, sql, params=None):
    return db.cursor().execute(sql, params or []).fetchone()[0]


def test_constants():
    assert config.REFERENCE_DATE == date(2025, 12, 31)
    assert config.SMALL_CELL_THRESHOLD == 10
    assert SEXES == ("female", "male")
    assert len(REGIONS) == 9
    assert list(REGIONS) == sorted(REGIONS)


def test_raw_and_consented_counts(db):
    assert scalar(db, "SELECT count(*) FROM raw_patients") == 20000
    assert scalar(db, "SELECT count(*) FROM pat") == 19161
    assert scalar(db, "SELECT count(*) FROM pat_all") == 20000


def test_age_and_region(db):
    n = scalar(db, "SELECT count(*) FROM pat WHERE age >= 18 AND region = 'Burgenland'")
    assert n == 532


def test_child_views_exclude_opt_out(db):
    hba1c = "WHERE loinc = '4548-4'"
    with_opt_out = scalar(db, f"SELECT count(DISTINCT patient_id) FROM obs_all {hba1c}")
    consented = scalar(db, f"SELECT count(DISTINCT patient_id) FROM obs {hba1c}")
    assert consented < with_opt_out
    leaked = scalar(
        db,
        "SELECT count(*) FROM obs o JOIN raw_patients p USING (patient_id) WHERE p.opted_out",
    )
    assert leaked == 0
    for view in ("cond", "med", "enc"):
        n = scalar(
            db,
            f"SELECT count(*) FROM {view} v JOIN raw_patients p USING (patient_id) WHERE p.opted_out",
        )
        assert n == 0, view


def test_typed_columns(db):
    def types(table):
        rows = db.cursor().execute(f"DESCRIBE {table}").fetchall()
        return {r[0]: r[1] for r in rows}

    assert types("raw_observations")["value"] == "DECIMAL(10,2)"
    assert types("raw_observations")["date"] == "DATE"
    assert types("raw_patients")["opted_out"] == "BOOLEAN"
    # empty end_date / primary_icd10 become NULL
    assert scalar(db, "SELECT count(*) FROM raw_medications WHERE end_date IS NULL") > 0
    assert scalar(db, "SELECT count(*) FROM raw_encounters WHERE primary_icd10 = ''") == 0
    assert scalar(db, "SELECT count(*) FROM raw_encounters WHERE primary_icd10 IS NOT NULL") > 0


def test_data_holders(db):
    assert db.data_holders == ("Klinikum Nord", "Klinikum Süd", "Klinikum West")


def test_loads_from_unicode_path(db, settings):
    # On machines whose data path contains non-ASCII characters (e.g. "ü") the `db` fixture
    # loading at all proves such paths work; on other machines this is a plain load check.
    assert settings.data_dir.is_dir()
    assert "Kärnten" in REGIONS
    regions = {r[0] for r in db.cursor().execute("SELECT DISTINCT region FROM pat").fetchall()}
    assert "Kärnten" in regions
    assert regions == set(REGIONS)


def test_settings_find_track3_from_worktree(monkeypatch):
    monkeypatch.delenv("TRACK3_DATA", raising=False)
    s = load_settings()
    assert (s.data_dir / "requests" / "expected.json").is_file()
    assert (s.data_dir / "data" / "patients.csv").is_file()


def test_settings_env_override(monkeypatch, tmp_path):
    monkeypatch.setenv("TRACK3_DATA", str(tmp_path))
    monkeypatch.setenv("EHDS_VAR_DIR", str(tmp_path / "v"))
    monkeypatch.setenv("EHDS_LLM", "off")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    s = load_settings()
    assert s.data_dir == tmp_path
    assert s.var_dir == tmp_path / "v"
    assert s.llm_mode == "off"
