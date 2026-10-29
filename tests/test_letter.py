import json
from pathlib import Path

from accessdesk.cases import CaseRegistry
from accessdesk.letter import build


def _letters(data_dir, desk):
    return CaseRegistry(desk, data_dir)


def test_letters_use_reviewed_templates_for_request_and_application_cases(data_dir, desk):
    registry = _letters(data_dir, desk)
    templates_path = Path(__file__).resolve().parents[1] / "accessdesk" / "templates" / "letter_texts.json"
    templates = json.loads(templates_path.read_text(encoding="utf-8"))

    r01 = build(registry.get("R01"), "de")
    assert r01["operative"] == templates["operative"]["APPROVE_STATISTICAL_request"]["de"]
    assert len(r01["conditions"]) == len(templates["conditions"]["statistics"])
    assert r01["annex"]["type"] == "statistics"
    assert r01["signature"][-1].startswith("Prüfsumme")

    r02 = build(registry.get("R02"), "en")
    assert r02["operative"] == templates["operative"]["REJECT_request"]["en"]
    assert any("insurance premiums" in paragraph for paragraph in r02["reasoning"])
    assert r02["annex"] is None
    assert r02["conditions"] == []

    r05 = build(registry.get("R05"), "en")
    assert r05["annex"]["type"] == "permit"
    assert r05["annex"]["cohort_size"] == 1152
    assert "Art. 73(2)" in "\n".join(r05["conditions"])
    assert any(table.startswith("measurements (LOINC 4548-4)") for table in r05["annex"]["tables"])

    r09 = build(registry.get("R09"), "en")
    assert any("second subparagraph of Art. 68(3)" in paragraph for paragraph in r09["reasoning"])

    d03 = build(registry.get("D03"), "de")
    assert d03["header"]["draft"]
    assert "ENTWURF" in d03["header"]["draft_notice"]
    assert d03["annex"] is None
