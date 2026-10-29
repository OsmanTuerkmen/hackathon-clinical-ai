import json

from accessdesk.audit import Audit


def test_audit_chain_verifies_after_append_and_restart(tmp_path):
    path = tmp_path / "audit.jsonl"
    first = Audit(str(path))
    first.log("received", "R01", actor="applicant", note="Kärnten")
    Audit(str(path)).log("approved", "R01", articles=["53", "69"])

    audit = Audit(str(path))
    assert audit.verify() == {
        "ok": True, "entries": 2, "first_bad_seq": None, "reason": None,
    }
    assert [entry["seq"] for entry in audit.tail(2)] == [2, 1]


def test_audit_detects_an_edited_entry(tmp_path):
    path = tmp_path / "audit.jsonl"
    audit = Audit(str(path))
    audit.log("received", "R01", detail="original")
    entry = json.loads(path.read_text(encoding="utf-8"))
    entry["details"]["detail"] = "edited"
    path.write_text(json.dumps(entry) + "\n", encoding="utf-8")

    result = Audit(str(path)).verify()
    assert not result["ok"]
    assert result["first_bad_seq"] == 1
    assert result["reason"] == "entry hash mismatch"


def test_audit_detects_a_deleted_middle_entry(tmp_path):
    path = tmp_path / "audit.jsonl"
    audit = Audit(str(path))
    for number in range(3):
        audit.log("event", str(number))
    lines = path.read_text(encoding="utf-8").splitlines()
    path.write_text("\n".join((lines[0], lines[2])) + "\n", encoding="utf-8")

    result = Audit(str(path)).verify()
    assert not result["ok"]
    assert result["first_bad_seq"] == 3
