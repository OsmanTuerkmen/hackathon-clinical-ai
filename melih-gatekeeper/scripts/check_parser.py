"""Parser vs expected.json for the 10 official requests (dev helper)."""
import json, pathlib, sys
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "backend"))
from app import compiler, privacy
from app.parser import parse

ROOT = pathlib.Path(__file__).resolve().parents[1]
exp = json.loads((ROOT / "track/requests/expected.json").read_text())

def values_match(expected, got):
    """Official rule: every expected value appears under its group; layout does not matter."""
    if isinstance(expected, dict):
        if isinstance(got, dict):
            if all(k in got for k in expected) and any(isinstance(v, dict) for v in expected.values()):
                return all(values_match(v, got[k]) for k, v in expected.items())
            flat = list(got.values()) if all(not isinstance(v, dict) for v in got.values()) else None
            if flat is not None and all(not isinstance(v, dict) for v in expected.values()):
                return all(v in flat for v in expected.values())
            return all(k in got and values_match(v, got[k]) for k, v in expected.items())
        return False
    return expected == got if not isinstance(got, dict) else expected in got.values()

for f in sorted((ROOT / "track/requests").glob("R*.json")):
    req = json.loads(f.read_text())
    r = parse(req)
    e = exp[req["id"]]["answer"]
    if r.plan is None:
        print(req["id"], "NO PLAN", r.notes); continue
    raw = compiler.run(r.plan)
    pub = privacy.publish(raw, {m.name for m in r.plan.measures if m.hidden})
    ok = values_match(e, pub) if e is not None else "(rejected; plan built)"
    print(req["id"], ok, "unparsed:", r.unparsed, r.notes)
    if ok is False or "-v" in sys.argv:
        print("   plan:", r.plan.model_dump_json(exclude_defaults=True))
        print("   got :", json.dumps(pub, ensure_ascii=False)[:600])
        print("   exp :", json.dumps(e, ensure_ascii=False)[:600])
