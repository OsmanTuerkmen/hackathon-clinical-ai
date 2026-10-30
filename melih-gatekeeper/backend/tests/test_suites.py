"""Hidden-style (C*) and adversarial (A*) fixtures; expected values come from the independent oracle SQL."""
import pytest
from conftest import ROOT, load

from app import metrics, pipeline

CASES = sorted(p.stem for d in ("custom", "adversarial") for p in (ROOT / "fixtures" / d).glob("*.json") if not p.name.endswith(".expected.json"))


@pytest.mark.parametrize("cid", CASES)
def test_case(cid):
    folder = "custom" if cid.startswith("C") else "adversarial"
    req, exp = load(f"fixtures/{folder}/{cid}.json"), load(f"fixtures/{folder}/{cid}.expected.json")
    if exp["decision"] == "INVALID":
        with pytest.raises(pipeline.RequestError):
            pipeline.run_sync(req)
        return
    d = pipeline.run_sync({**req, "id": "t" + cid})
    dec = d["decision"]
    assert dec["outcome"] == exp["decision"], dec["review_reasons"]
    assert metrics.articles_ok(exp["articles"], dec["articles"])
    if "needs_review" in exp:
        assert dec["needs_review"] == exp["needs_review"], dec["review_reasons"]
    if exp.get("answer"):
        assert metrics.values_match(exp["answer"], d["result"]["answer"])
    elif "answer" in exp and dec["outcome"] == "APPROVE_STATISTICAL":
        assert d["result"] is None  # held: no numbers without a confident translation
    if d.get("result") and d["result"].get("kind") == "table":
        from app.privacy import leak_check
        assert leak_check(d["result"]["answer"]) == []
