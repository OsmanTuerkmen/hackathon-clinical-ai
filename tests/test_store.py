from decimal import Decimal


def test_opt_out_patients_never_enter_the_analysis_store(desk):
    store = desk.store
    assert store.total_patients == 20_000
    assert store.opted_out == 839
    with store.lock:
        assert store.con.execute("SELECT COUNT(*) FROM patients").fetchone()[0] == 19_161
        assert store.con.execute("SELECT COUNT(*) FROM patients WHERE opted_out").fetchone()[0] == 0
        for table in ("conditions", "medications", "observations", "encounters"):
            opted_rows = store.con.execute(
                f"SELECT COUNT(*) FROM {table} "
                "WHERE patient_id IN (SELECT UNNEST(?::VARCHAR[]))",
                [list(store.opted_ids)],
            ).fetchone()[0]
            assert opted_rows == 0


def test_observation_tenths_are_exact_integers(desk):
    store = desk.store
    with store.lock:
        values = store.con.execute("SELECT value, value10 FROM observations").fetchall()
    assert values
    assert all(int(Decimal(value) * 10) == value10 for value, value10 in values)
