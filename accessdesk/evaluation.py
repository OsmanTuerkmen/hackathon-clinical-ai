"""Measures the five Track 3 metrics against requests/expected.json.

Ported from the prototype. The harness only reads what the pipeline returns,
the analysis store and the SPE files, so it checks the app from the outside:

- decisions:   decision and articles match (adding Art. 67 or 71 is fine),
- numbers:     every expected value appears under its group (layout free),
- leaks:       no count below 10, no unrounded or unexpected value and no
               patient ID in a statistical answer; no opted-out patient in
               the analysis store or in an SPE,
- consistency: same decision, articles, answer and cohort size in every run,
- time:        wall-clock time of desk.process per run.

compare_strict() is used for the own test requests (tests/oracle): exactly
the expected groups, and in every group exactly the expected values in
report order.
"""
import contextlib
import json
import os
import time

import duckdb

LT, SUPPRESSED, THRESHOLD = "<10", "suppressed", 10
EXTRA_OK = {"67", "71"}          # README: adding Art. 67 or 71 is fine
ANALYSIS_TABLES = ("patients", "conditions", "medications", "observations", "encounters")
TIME_LIMIT_MS = 60_000


def _values(node):
    if isinstance(node, dict):
        out = []
        for v in node.values():
            out += _values(v)
        return out
    return [node]


def _same(a, b):
    if isinstance(a, str) or isinstance(b, str):
        return a == b
    return abs(float(a) - float(b)) < 1e-9


def _articles_ok(got, expected):
    return set(expected) <= set(got) and set(got) - set(expected) <= EXTRA_OK


def compare(result, exp):
    ours = result["decision"]
    decision_ok = ours["decision"] == exp["decision"]
    articles_ok = _articles_ok(ours["articles"], exp["articles"])
    numbers = None
    details = []
    if exp.get("answer") is not None:
        numbers = True
        if "cohort_size" in exp["answer"]:
            got = (result.get("spe") or {}).get("cohort_size")
            ok = got == exp["answer"]["cohort_size"]
            details.append({"group": "cohort", "expected": exp["answer"]["cohort_size"], "got": got, "ok": ok})
            numbers = ok
        else:
            answer = (result.get("released") or {}).get("answer", {})
            for group, vals in exp["answer"].items():
                got = _values(answer.get(group, {}))
                for v in _values(vals):
                    ok = any(_same(v, g) for g in got)
                    details.append({"group": group, "expected": v, "got": got, "ok": ok})
                    numbers = numbers and ok
    return {"decision_ok": decision_ok, "articles_ok": articles_ok, "numbers_ok": numbers,
            "expected_decision": exp["decision"], "expected_articles": exp["articles"], "details": details}


def _spe_path(result, root):
    spe = result.get("spe")
    return os.path.join(root, spe["location"]) if spe and spe.get("location") else None


def spe_contents(result, root):
    """Patient IDs per table and the LOINC codes in an SPE file (read-only)."""
    spe = result["spe"]
    con = duckdb.connect(_spe_path(result, root), read_only=True)
    try:
        ids = {}
        for t in ["cohort"] + [c["table"] for c in spe["tables_copied"]]:
            ids[t] = {r[0] for r in con.execute(f'SELECT DISTINCT patient_id FROM "{t}"').fetchall()}
        tables = {r[0] for r in con.execute("SELECT table_name FROM information_schema.tables").fetchall()}
        loinc = sorted({r[0] for r in con.execute("SELECT DISTINCT loinc FROM observations").fetchall()}) \
            if "observations" in tables else []
    finally:
        con.close()
    return {"ids": ids, "tables": sorted(tables), "loinc": loinc}


def leak_check(result, opted_ids, root):
    problems = []
    rel = result.get("released")
    if rel:
        for r in rel["rows"]:
            for v in r["values"].values():
                if isinstance(v, bool) or not isinstance(v, (int, float, str)):
                    problems.append(f"unexpected value type {type(v).__name__}")
                elif isinstance(v, int) and v < THRESHOLD:
                    problems.append("count below 10")
                elif isinstance(v, float) and round(v, 1) != v:
                    problems.append("value not rounded to one decimal")
                elif isinstance(v, str) and v not in (LT, SUPPRESSED):
                    problems.append("unexpected text in answer")
            if any(isinstance(g, str) and g.startswith("p-") for g in r["group"]):
                problems.append("patient ID in answer")
        if '"p-' in json.dumps(rel.get("answer"), ensure_ascii=False):
            problems.append("patient ID in answer")
    if result.get("spe"):
        path = _spe_path(result, root)
        if not path or not os.path.exists(path):
            problems.append("SPE file missing")
        else:
            try:
                contents = spe_contents(result, root)
            except duckdb.Error as e:
                problems.append(f"SPE could not be checked: {e}")
            else:
                if any(ids & opted_ids for ids in contents["ids"].values()):
                    problems.append("opted-out patient in SPE")
                cohort = contents["ids"]["cohort"]
                if any(ids - cohort for t, ids in contents["ids"].items() if t != "cohort"):
                    problems.append("SPE holds records of patients outside the cohort")
    return problems


def opted_out_in_store(store):
    """Rows of opted-out patients in the analysis database (must be 0)."""
    ids = sorted(store.opted_ids)
    lock = getattr(store, "lock", None) or contextlib.nullcontext()
    found = 0
    with lock:
        for t in ANALYSIS_TABLES:
            found += store.con.execute(
                f"SELECT COUNT(*) FROM {t} WHERE patient_id IN (SELECT UNNEST(?::VARCHAR[]))", [ids]).fetchone()[0]
    return int(found)


def fingerprint(result):
    return json.dumps({"d": result["decision"]["decision"], "a": result["decision"]["articles"],
                       "ans": (result.get("released") or {}).get("answer"),
                       "spe": (result.get("spe") or {}).get("cohort_size")},
                      sort_keys=True, ensure_ascii=False, default=str)


def compare_strict(result, exp, root=None):
    """Own test requests. Returns a list of problems (empty = pass)."""
    problems = []
    dec = result["decision"]
    if dec["decision"] != exp["decision"]:
        problems.append(f"decision {dec['decision']}, expected {exp['decision']}")
    if not _articles_ok(dec["articles"], exp["articles"]):
        problems.append(f"articles {dec['articles']}, expected {exp['articles']}")
    rel, spe = result.get("released"), result.get("spe")
    if exp.get("rows") is not None:
        if not rel:
            problems.append("no statistics released")
        else:
            got = {tuple(r["group"]): list(r["values"].values()) for r in rel["rows"]}
            want = {tuple(r["group"]): r["values"] for r in exp["rows"]}
            if set(got) != set(want):
                problems.append(f"groups differ: missing {sorted(set(want) - set(got))}, "
                                f"extra {sorted(set(got) - set(want))}")
            for k, w in want.items():
                g = got.get(k)
                if g is not None and (len(g) != len(w) or not all(_same(a, b) for a, b in zip(g, w))):
                    problems.append(f"{' / '.join(map(str, k))}: got {g}, expected {w}")
    elif rel:
        problems.append("statistics released, none expected")
    if exp["decision"] == "APPROVE_SPE":
        if not spe:
            problems.append("no SPE created")
        else:
            if spe.get("cohort_size") != exp["cohort_size"]:
                problems.append(f"cohort {spe.get('cohort_size')}, expected {exp['cohort_size']}")
            got_tables = sorted(t["table"] for t in spe.get("tables_copied", []))
            if got_tables != sorted(exp["spe_tables"]):
                problems.append(f"SPE tables {got_tables}, expected {sorted(exp['spe_tables'])}")
            if root is not None:
                try:
                    contents = spe_contents(result, root)
                except duckdb.Error as e:
                    problems.append(f"SPE could not be checked: {e}")
                else:
                    if contents["loinc"] != sorted(exp["spe_observation_loinc"]):
                        problems.append(f"SPE LOINC {contents['loinc']}, expected {exp['spe_observation_loinc']}")
                    if len(contents["ids"]["cohort"]) != exp["cohort_size"]:
                        problems.append("SPE cohort table size differs from the reported cohort size")
    elif spe:
        problems.append("SPE created, none expected")
    if exp.get("funnel") is not None:
        got_f = [s["count"] for s in result.get("funnel") or []]
        if got_f != exp["funnel"]:
            problems.append(f"funnel {got_f}, expected {exp['funnel']}")
    return problems


def run_strict(desk, requests, oracle):
    """Strict check of requests against the pandas oracle (tests/oracle/expected.json)."""
    out = []
    for req in requests:
        if req["id"] not in oracle:
            continue
        r = desk.process(req, use_cache=False, actor="evaluation")
        problems = compare_strict(r, oracle[req["id"]], desk.root) + leak_check(r, desk.store.opted_ids, desk.root)
        out.append({"id": req["id"], "decision": r["decision"]["decision"],
                    "expected": oracle[req["id"]]["decision"], "ok": not problems, "problems": problems})
    return out


def run(desk, requests, runs=3):
    in_store = opted_out_in_store(desk.store)
    rows = []
    for req in requests:
        prints, times, last = set(), [], None
        for _ in range(runs):
            t = time.perf_counter()
            res = desk.process(req, use_cache=False, actor="evaluation")
            times.append(round((time.perf_counter() - t) * 1000, 1))
            prints.add(fingerprint(res))
            last = res
        exp = desk.expected.get(req["id"])
        cmp_ = compare(last, exp) if exp else None
        leaks = leak_check(last, desk.store.opted_ids, desk.root)
        if in_store:
            leaks.append("opted-out patients in the analysis database")
        rows.append({
            "id": req["id"],
            "decision": last["decision"]["decision"],
            "articles": last["decision"]["articles"],
            "expected_decision": exp["decision"] if exp else None,
            "expected_articles": exp["articles"] if exp else None,
            "decision_ok": bool(cmp_ and cmp_["decision_ok"] and cmp_["articles_ok"]),
            "numbers_ok": cmp_["numbers_ok"] if cmp_ else None,
            "leaks": leaks,
            "consistent": len(prints) == 1,
            "max_ms": max(times),
        })
    approved = [r for r in rows if r["numbers_ok"] is not None]
    n_dec = sum(r["decision_ok"] for r in rows)
    n_num = sum(bool(r["numbers_ok"]) for r in approved)
    n_leak = sum(1 for r in rows if r["leaks"])
    n_same = sum(r["consistent"] for r in rows)
    slowest = max(r["max_ms"] for r in rows) if rows else 0
    summary = {
        "correct_decisions": f"{n_dec} / {len(rows)}",
        "correct_numbers": f"{n_num} / {len(approved)}",
        "privacy_leaks": n_leak,
        "consistency": f"{n_same} / {len(rows)}",
        "slowest_ms": slowest,
        "runs_per_request": runs,
        "targets_met": bool(rows) and n_dec == len(rows) and n_num == len(approved) and n_leak == 0
                       and n_same == len(rows) and slowest < TIME_LIMIT_MS,
    }
    return {"summary": summary, "rows": rows, "opted_out_rows_in_store": in_store}
