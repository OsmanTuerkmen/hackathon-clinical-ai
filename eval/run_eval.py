"""Three real HTTP runs of the external requests, with fail-closed evaluation gates.

Run from the checkout: .venv/Scripts/python eval/run_eval.py
Patient records and identifiers are inspected only in memory and never reported.
"""
from __future__ import annotations

import csv
import json
import re
import subprocess
import sys
import time
from collections import Counter
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from eval.reference import (EXTRA_REFERENCES, ReferenceData, compare_references, find_data_dir, r05_patient_ids)

ID_PATTERN = re.compile(r"p-[0-9a-f]{8}", re.IGNORECASE)


def _mapping(value):
    return value.model_dump(mode="json") if hasattr(value, "model_dump") else value


def _number(value) -> Decimal | None:
    if isinstance(value, bool) or not isinstance(value, (int, float, str, Decimal)):
        return None
    try:
        number = Decimal(str(value))
        return number if number.is_finite() else None
    except InvalidOperation:
        return None


def _equal(left, right) -> bool:
    a, b = _number(left), _number(right)
    if a is not None and b is not None:
        return abs(a - b) <= Decimal("1e-9")
    return type(left) is type(right) and left == right


def match_numbers(expected_answer, applicant) -> bool:
    """Match each occurrence within its group, allowing renamed metric columns.

    Values are a multiset: a single released value cannot satisfy two expected
    cells. Group order follows the table dimensions, never dictionary insertion.
    """
    applicant = _mapping(applicant)
    if not isinstance(expected_answer, dict) or not expected_answer or not isinstance(applicant, dict):
        return False
    if set(expected_answer) == {"cohort_size"}:
        spe = applicant.get("spe")
        return isinstance(spe, dict) and _equal(expected_answer["cohort_size"], spe.get("patient_count"))
    table = applicant.get("statistics")
    if not isinstance(table, dict) or not isinstance(table.get("rows"), list):
        return False
    dimensions = table.get("dimensions")
    if not isinstance(dimensions, list) or not all(isinstance(d, str) for d in dimensions):
        return False
    groups = {}
    for row in table["rows"]:
        if not isinstance(row, dict) or not isinstance(row.get("group"), dict) or not isinstance(row.get("values"), dict):
            return False
        group = row["group"]
        if set(group) != set(dimensions):
            return False
        key = " / ".join(str(group[d]) for d in dimensions)
        if key in groups:
            return False
        groups[key] = list(row["values"].values())
    for key, expected in expected_answer.items():
        if key not in groups:
            return False
        remaining = groups[key].copy()
        for target in (expected.values() if isinstance(expected, dict) else [expected]):
            for i, actual in enumerate(remaining):
                if _equal(target, actual):
                    remaining.pop(i)
                    break
            else:
                return False
    return True


def match_decision(expected: dict, applicant: dict) -> bool:
    actual = applicant.get("articles")
    if not isinstance(actual, list) or not all(isinstance(a, str) for a in actual):
        return False
    required = set(expected["articles"])
    return (applicant.get("decision") == expected["decision"] and len(actual) == len(set(actual))
            and required <= set(actual) and set(actual) - required <= {"67", "71"})


def _group_key(group: dict) -> tuple:
    return tuple(sorted(group.items()))


def find_leaks(result, raw) -> list[str]:
    """Audit the entire regular response and disclosed cells against raw counts.

    No finding includes patient values, IDs, or serialized response content.
    Exact SPE cohort/table sizes are deliberately outside statistical suppression.
    """
    result = _mapping(result)
    raw = _mapping(raw)
    leaks: list[str] = []

    def scan(value):
        if isinstance(value, dict):
            for key, item in value.items():
                if ID_PATTERN.search(str(key)):
                    leaks.append("patient identifier in response key")
                if key in {"patient_id", "encounter_id", "birth_date"}:
                    leaks.append("patient-level field in regular response")
                if key == "opted_out" and item in (True, "true"):
                    leaks.append("opted-out patient record in response")
                scan(item)
        elif isinstance(value, list):
            for item in value:
                scan(item)
        elif isinstance(value, str) and ID_PATTERN.search(value):
            leaks.append("patient identifier in regular response")

    scan(result)
    applicant = result.get("applicant", {})
    if not isinstance(applicant, dict):
        return leaks + ["invalid applicant response"]
    for key in ("records", "patients", "conditions", "medications", "observations", "encounters"):
        if applicant.get(key):
            leaks.append("unexpected records in applicant response")
    table = applicant.get("statistics")
    if table is None:
        return leaks
    if not isinstance(table, dict):
        return leaks + ["invalid statistical response"]
    if any(table.get(key) for key in ("records", "patients", "conditions", "medications", "observations", "encounters")):
        leaks.append("unexpected records in statistical response")
    kinds = {m["name"]: m.get("kind") for m in table.get("metrics", []) if isinstance(m, dict) and "name" in m}
    raw_rows = {_group_key(r["group"]): r["cells"] for r in raw.get("rows", [])} if isinstance(raw, dict) else {}
    for row in table.get("rows", []):
        if not isinstance(row, dict) or not isinstance(row.get("values"), dict) or not isinstance(row.get("group"), dict):
            leaks.append("unexpected record or invalid statistical row")
            continue
        cells = raw_rows.get(_group_key(row["group"]), {})
        for name, value in row["values"].items():
            cell = cells.get(name)
            kind = kinds.get(name)
            if cell is not None:
                if "num" in cell and "den" in cell:
                    if min(cell["num"], cell["den"]) < 10 and value != "suppressed":
                        leaks.append("unsuppressed percentage with small numerator or denominator")
                    kind = "percent"
                elif "total" in cell and "n" in cell:
                    if cell["n"] < 10 and value != "suppressed":
                        leaks.append("unsuppressed mean with small sample")
                    kind = "mean"
                elif "n" in cell:
                    if cell["n"] < 10 and value != "<10":
                        leaks.append("unsuppressed raw small count")
                    kind = "count"
            elif kind in {"percent", "mean"}:
                leaks.append("raw disclosure cross-check unavailable")
            number = _number(value)
            if kind == "count" and number is not None and number < 10:
                leaks.append("small count released in statistical cell")
            elif kind is None and isinstance(value, int) and not isinstance(value, bool) and value < 10:
                leaks.append("untyped small integer in statistical cell")
    return leaks


def summarise_runs(runs: list[dict]) -> dict:
    complete = len(runs) == 3 and all(run["http_ok"] for run in runs)
    canonical = [json.dumps(run["applicant"], sort_keys=True, ensure_ascii=False, separators=(",", ":")) for run in runs]
    return {"decision_ok": complete and all(run["decision_ok"] for run in runs),
            "numbers_ok": complete and all(run["numbers_ok"] for run in runs),
            "consistent": complete and len(set(canonical)) == 1,
            "leak_count": sum(len(run["leaks"]) for run in runs),
            "elapsed": max((run["elapsed"] for run in runs), default=float("inf")),
            "applicant": runs[0]["applicant"] if runs else {},
            "http_ok": complete}


# Independent SPE extensions belong alongside Task 14's independent CSV functions.
# Each entry is (cohort function, requested record types, observation code prefixes).
SPE_REFERENCES = {"R05": (r05_patient_ids, {"conditions", "medications", "observations"}, ("4548-4",))}


def _normalise_record(row: dict, columns: list[str]) -> tuple:
    def normal(column, value):
        if value is None:
            return ""
        if column == "value":
            return Decimal(str(value))
        if isinstance(value, bool):
            return str(value).lower()
        return str(value)
    return tuple(normal(column, row.get(column)) for column in columns)


def audit_spe(result: dict, data: ReferenceData, var_dir: Path) -> list[str]:
    """Compare all SPE rows to the original CSV selection, including multiplicity."""
    import duckdb

    applicant = result["applicant"]
    answer = applicant.get("spe")
    if answer is None:
        return []
    contract = SPE_REFERENCES.get(applicant.get("request_id"))
    if contract is None:
        return ["independent SPE record contract unavailable"]
    cohort_function, record_types, observation_codes = contract
    cohort = cohort_function(data)
    permit = answer.get("permit_id", "")
    if not isinstance(permit, str) or not re.fullmatch(r"[A-Za-z0-9_-]+", permit):
        return ["invalid SPE permit identifier"]
    db_file = var_dir / "spe" / permit / "spe.duckdb"
    leaks = []
    con = duckdb.connect(str(db_file), read_only=True)
    try:
        tables = {r[0] for r in con.execute("SHOW TABLES").fetchall()}
        expected_tables = record_types | {"cohort"}
        if tables != expected_tables or set(answer.get("tables", {})) != expected_tables:
            leaks.append("SPE contains missing or unrequested record types")

        for table in sorted(tables & expected_tables):
            # Table names come only from the static independent contract above.
            cur = con.execute(f'SELECT * FROM "{table}"')
            columns = [c[0] for c in cur.description]
            actual = [dict(zip(columns, row)) for row in cur.fetchall()]
            if answer.get("tables", {}).get(table) != len(actual):
                leaks.append("SPE reported table size differs from stored records")
            # The expected projection comes from the original CSV contract,
            # never from the database being audited or the application's SQL.
            if table == "cohort":
                expected_columns = ["patient_id"]
            else:
                with (data.directory / "data" / f"{table}.csv").open(encoding="utf-8-sig", newline="") as stream:
                    expected_columns = csv.DictReader(stream).fieldnames or []
                if table == "patients":
                    expected_columns = [column for column in expected_columns if column not in {"opted_out", "age"}]
            if set(columns) != set(expected_columns):
                leaks.append("SPE table has missing or unrequested columns")
                continue
            if table == "cohort":
                actual_ids = [row["patient_id"] for row in actual]
                if set(actual_ids) != cohort or len(actual_ids) != len(cohort):
                    leaks.append("SPE cohort differs from independent consented CSV selection")
            if any(row.get("patient_id") in data.opted_out_ids for row in actual):
                leaks.append("opted-out patient in SPE")
            if any(row.get("patient_id") not in cohort for row in actual):
                leaks.append("unselected patient in SPE")
            if table == "cohort":
                expected_rows = [{"patient_id": pid} for pid in cohort]
            else:
                expected_rows = [r for r in data.tables[table] if r["patient_id"] in cohort
                                 and (table != "observations" or not observation_codes or r["loinc"].startswith(observation_codes))]
            if Counter(_normalise_record(r, expected_columns) for r in actual) != Counter(_normalise_record(r, expected_columns) for r in expected_rows):
                leaks.append("SPE records differ from independent requested CSV records")
    finally:

        con.close()
    return leaks


def audit_opt_out_views(service, data: ReferenceData) -> list[str]:
    findings = []
    cursor = service.db.cursor()
    try:
        for view in ("pat", "cond", "med", "obs", "enc"):
            if any(row[0] in data.opted_out_ids for row in cursor.execute(f"SELECT DISTINCT patient_id FROM {view}").fetchall()):
                findings.append("opted-out patient in consented computation view")
    finally:
        cursor.close()
    return findings


def evaluate_requests(client, service, requests: dict, expected: dict, data: ReferenceData) -> dict:
    from ehds_desk.engine import run_statistics
    from ehds_desk.models import QuerySpec

    runs = {key: [] for key in expected}
    for _iteration in range(3):
        for request_id, target in expected.items():
            started = time.perf_counter()
            try:
                # The timer includes HTTP dispatch, all pipeline work and SPE provisioning.
                response = client.post("/api/process", json=requests[request_id])
                elapsed = time.perf_counter() - started
                http_ok = response.status_code == 200
                try:
                    body = response.json()
                except ValueError:
                    body = {"body": response.text}
                result = body if isinstance(body, dict) else {"body": body}
                # Error bodies are still releases: inspect them before evaluating
                # a missing applicant envelope as a failed correctness result.
                applicant = result.setdefault("applicant", {"decision": f"HTTP {response.status_code}"})
                raw = None
                if applicant.get("statistics") is not None:
                    raw, _query = run_statistics(QuerySpec.model_validate(result["staff"]["spec"]), service.db)
                leaks = find_leaks(result, raw)
                leaks.extend(audit_spe(result, data, service.settings.var_dir))
                leaks.extend(audit_opt_out_views(service, data))
                runs[request_id].append({"applicant": applicant, "http_ok": http_ok,
                    "decision_ok": match_decision(target, applicant),
                    "numbers_ok": target.get("answer") is None or match_numbers(target["answer"], applicant),
                    "leaks": leaks, "elapsed": elapsed})
            except Exception as error:
                # No exception message/trace: a database error may quote patient values.
                runs[request_id].append({"applicant": {"decision": f"ERROR {type(error).__name__}"},
                    "http_ok": False, "decision_ok": False, "numbers_ok": False,
                    "leaks": ["privacy audit or request could not complete"], "elapsed": time.perf_counter() - started})
    return {key: summarise_runs(values) for key, values in runs.items()}


def _metrics(summaries: dict, expected: dict) -> list[tuple[str, str, str, bool]]:
    total = len(expected)
    approved = {key for key, value in expected.items() if value.get("answer") is not None}
    decisions = sum(s["decision_ok"] for s in summaries.values())
    numbers = sum(summaries[key]["numbers_ok"] for key in approved)
    leaks = sum(s["leak_count"] for s in summaries.values())
    consistency = sum(s["consistent"] for s in summaries.values())
    slowest = max((s["elapsed"] for s in summaries.values()), default=float("inf"))
    return [("Correct decisions", f"{decisions}/{total}", f"{total}/{total}", decisions == total),
            ("Correct numbers", f"{numbers}/{len(approved)}", f"{len(approved)}/{len(approved)}", numbers == len(approved)),
            ("Privacy leaks (all runs)", str(leaks), "0", leaks == 0),
            ("Consistency (applicant JSON)", f"{consistency}/{total}", f"{total}/{total}", consistency == total),
            ("Time to answer (slowest HTTP run)", f"{slowest:.3f} s", "< 60 s", slowest < 60)]


def _request_table(summaries: dict, expected: dict) -> list[str]:
    lines = ["| Request | Decision expected / actual | Articles expected / actual | Numbers (3/3) | Leaks (3 runs) | Consistent | Max HTTP ms |",
             "|---|---|---|---|---:|---|---:|"]
    for key, target in expected.items():
        item = summaries[key]
        actual = item["applicant"]
        number_status = "—" if target.get("answer") is None else ("PASS" if item["numbers_ok"] else "FAIL")
        lines.append(f"| {key} | {target['decision']} / {actual.get('decision', 'missing')} | "
                     f"{', '.join(target['articles'])} / {', '.join(actual.get('articles', []))} | "
                     f"{number_status} | {item['leak_count']} | {'PASS' if item['consistent'] else 'FAIL'} | {item['elapsed'] * 1000:.1f} |")
    return lines


def vienna_stamp(instant: datetime | None = None) -> str:
    instant = instant or datetime.now(timezone.utc)
    try:
        zone = ZoneInfo("Europe/Vienna")
    except ZoneInfoNotFoundError:
        # Windows may ship neither an IANA database nor the optional tzdata wheel.
        # Vienna's EU rule since 1996: last Sunday in March/October, 01:00 UTC.
        utc = instant.astimezone(timezone.utc)
        if utc.year < 1996:
            raise ValueError("Historical Vienna timestamps require IANA tzdata")
        march = datetime(utc.year, 3, 31, 1, tzinfo=timezone.utc)
        october = datetime(utc.year, 10, 31, 1, tzinfo=timezone.utc)
        start = march - timedelta(days=(march.weekday() + 1) % 7)
        end = october - timedelta(days=(october.weekday() + 1) % 7)
        zone = timezone(timedelta(hours=2 if start <= utc < end else 1))
    return instant.astimezone(zone).isoformat(timespec="seconds")

def main() -> int:
    from fastapi.testclient import TestClient
    from ehds_desk.api import create_app
    from ehds_desk.config import load_settings
    from ehds_desk.pipeline import DeskService

    settings = replace(load_settings(env_file=None), data_dir=find_data_dir(), llm_mode="off", anthropic_api_key=None)
    settings = replace(settings, var_dir=settings.var_dir / "eval")
    data = ReferenceData(settings.data_dir)
    expected = json.loads((settings.data_dir / "requests" / "expected.json").read_text(encoding="utf-8"))
    requests = {key: json.loads((settings.data_dir / "requests" / f"{key}.json").read_text(encoding="utf-8")) for key in expected}
    references = compare_references(data, expected)
    # Initialisation belongs to server startup. Every POST, including the first,
    # is timed only after the real service/data/terminology are ready.
    service = DeskService(settings=settings)
    extra_dir = ROOT / "requests" / "extra"
    extra_expected_path = extra_dir / "expected.json"
    extra_expected = json.loads(extra_expected_path.read_text(encoding="utf-8")) if extra_expected_path.is_file() else {}
    with TestClient(create_app(service)) as client:
        summaries = evaluate_requests(client, service, requests, expected, data)
        extra_summaries = {}
        extra_references = {}
        if extra_expected:
            extra_requests = {key: json.loads((extra_dir / f"{key}.json").read_text(encoding="utf-8")) for key in extra_expected}
            extra_summaries = evaluate_requests(client, service, extra_requests, extra_expected, data)
            extra_references = compare_references(data, extra_expected, EXTRA_REFERENCES)
            for key, target in extra_expected.items():
                if target.get("answer") is not None and key not in extra_references:
                    extra_references[key] = False
    commit = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, check=True, capture_output=True, text=True).stdout.strip()
    stamp = vienna_stamp()
    metrics = _metrics(summaries, expected)
    lines = ["# Evaluation results", "", f"Datum: {stamp} (Europe/Vienna)", f"Git-Commit: `{commit}`", "",
             "LLM-Modus: **off**, API-Key ausdrücklich **None**. Originaldaten/Requests/expected bleiben extern.",
             "Runtime: eigener Unterordner `settings.var_dir/eval`; FastAPI TestClient, Service vor Messbeginn initialisiert.",
             "Drei vollständige Läufe, 30 POSTs. Entscheidungen, Zahlen und Leaks prüfen alle drei Läufe; "
             "Konsistenz vergleicht ausschließlich das vollständige Applicant-JSON. Zeiten messen POST bis Antwort einschließlich SPE-Provisionierung.", "",
             "| Metrik | Ergebnis | Ziel | Status |", "|---|---|---|---|"]
    for name, value, target, passed in metrics:
        lines.append(f"| {name} | {value} | {target} | {'✅' if passed else '❌'} |")
        print(f"{name}: {value} (target {target})")
    lines += ["", "## Je Antrag", "", *_request_table(summaries, expected), "", "## Unabhängige Referenz", "",
              "`eval/reference.py` liest die fünf Original-CSVs nur mit der Standardbibliothek. "
              "Eigene Kohorten, aktive Medikation, letzte Messung, ROUND_HALF_UP und Suppression; keine App-/DuckDB-/Pydantic-Imports.", "",
              "| Request | CSV-Referenz vs. externes expected.json |", "|---|---|"]
    lines += [f"| {key} | {'PASS' if passed else 'FAIL'} |" for key, passed in references.items()]
    lines += ["", "Datenschutz-Gegenprobe: Patientenkennungen in Schlüsseln und Werten der gesamten regulären Antwort; "
              "Patientenfelder/unerwartete Records; kleine Countzellen auch als Float/String; Prozent/Mittelwerte gegen "
              "Rohzähler, -nenner und n aus `run_statistics(staff.spec)`. Alle consented Views werden gegen die unabhängige "
              "Opt-out-Menge geprüft. SPE-Kohorte und sämtliche kopierten Records werden mit der unabhängigen CSV-Auswahl "
              "einschließlich Multiplizität verglichen. Dabei werden keine Patientenzeilen oder IDs ausgegeben.", "",
              "## Eigene Anträge (Task 14)", ""]
    if extra_expected:
        lines += _request_table(extra_summaries, extra_expected)
        lines += ["", "Unabhängige Extra-Referenzen: " + ("PASS" if all(extra_references.values()) else "FAIL (fehlend oder abweichend)")]
    else:
        lines += ["Noch nicht vorhanden; keine erfundenen Ergebnisse. Hooks: `EXTRA_REFERENCES`, `SPE_REFERENCES` und "
                  "automatisches Laden von `requests/extra/expected.json` samt Requests. Fehlende Referenzen genehmigter "
                  "Extra-Anträge führen nach Hinzufügen zum Fehlschlag."]
    lines += ["", "## Grenzen", "", "Offline-TestClient-Messung auf dem lokalen synthetischen Datensatz; "
              "keine Live-LLM-, Netzwerk-, Authentifizierungs- oder Produktionslastmessung. "
              "Primäre Small-Cell-Regel; sekundäre Unterdrückung bleibt außerhalb des App-Umfangs. "
              "Exakte SPE-Patienten-/Tabellenzahlen sind gemäß Projektregel von statistischer Small-Cell-Unterdrückung ausgenommen.", ""]
    (ROOT / "eval" / "results.md").write_text("\n".join(lines), encoding="utf-8")
    extra_ok = not extra_expected or (all(item[3] for item in _metrics(extra_summaries, extra_expected)) and all(extra_references.values()))
    return 0 if all(item[3] for item in metrics) and all(references.values()) and extra_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
