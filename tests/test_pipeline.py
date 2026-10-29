import json
from pathlib import Path


def _request(data_dir, request_id):
    path = Path(data_dir).parent / "requests" / f"{request_id}.json"
    with path.open(encoding="utf-8") as stream:
        return json.load(stream)


def test_pipeline_returns_five_safes_funnel_and_inbox_status(data_dir, desk):
    statistical = desk.process(_request(data_dir, "R01"), use_cache=False)
    assert statistical["ai"] == {
        "status": {"enabled": False, "model": "claude-opus-5-5", "reason": "disabled"},
        "opinion": None,
        "agrees": None,
        "model": "claude-opus-5-5",
        "cached": False,
    }
    assert set(statistical["five_safes"]) == {
        "people", "projects", "data", "settings", "outputs",
    }
    assert statistical["funnel"][-1]["count"] == 14_716
    assert statistical["status"] == "auto_decided"

    spe = desk.process(_request(data_dir, "R05"), use_cache=False)
    assert spe["five_safes"]["settings"]["status"] == "pass"
    assert spe["five_safes"]["outputs"]["status"] == "pass"
    assert spe["data_minimisation"]["copied_record_types"] == [
        "conditions", "medications", "observations",
    ]

    rejected = desk.process(_request(data_dir, "R04"), use_cache=False)
    assert rejected["five_safes"]["projects"]["status"] == "fail"
    assert rejected["five_safes"]["settings"]["status"] == "na"
    assert rejected["five_safes"]["outputs"]["status"] == "na"
    assert rejected["status"] == "auto_decided"
