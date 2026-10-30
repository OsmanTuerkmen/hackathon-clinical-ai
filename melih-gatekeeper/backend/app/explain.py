"""Template back-translation of a QueryPlan into plain English (no model): what staff and applicants confirm."""
from __future__ import annotations

from . import db
from .catalog import catalog
from .plan import Criterion, QueryPlan


def _titles() -> dict[str, str]:
    cat = catalog()
    t = {}
    for c in cat["conditions_icd10"] + cat["encounter_primary_icd10_prefixes"]:
        t.setdefault(c["code"][:3], c.get("description", ""))
    for c in cat["medications_atc"]:
        t[c["code"]] = c["name"]
    for c in cat["observations_loinc"]:
        t[c["code"]] = c["name"]
    return t


def _code_label(source: str, codes: list[str]) -> str:
    titles = _titles()
    sysname = {"condition": "ICD-10", "medication": "ATC", "observation": "LOINC", "encounter": "main diagnosis ICD-10"}[source]
    parts = []
    for c in codes:
        if source == "medication":
            names = sorted({v for k, v in titles.items() if k.startswith(c) and not k[:1].isdigit()})
            parts.append(f"{c}* ({', '.join(names[:3])})" if names else f"{c}*")
        elif source == "observation":
            parts.append(f"{c} ({titles.get(c, '')})")
        else:
            parts.append(f"{c}* ({titles.get(c[:3], '')})".replace(" ()", ""))
    return f"{sysname} " + " or ".join(parts)


def criterion_text(c: Criterion) -> str:
    if c.source == "condition":
        s = f"has a diagnosis {_code_label('condition', c.codes)}"
    elif c.source == "medication":
        s = f"has a prescription {_code_label('medication', c.codes)}" + (f" active on {c.active_on}" if c.active_on else "")
    elif c.source == "observation":
        if c.value_op:
            s = f"latest {_code_label('observation', c.codes)} {c.value_op} {c.value:g}"
        else:
            s = f"has at least one {_code_label('observation', c.codes)} value"
    else:
        bits = [("/".join(c.encounter_types) or "any") + " encounter"]
        if c.codes:
            bits.append(f"with {_code_label('encounter', c.codes)}")
        s = "had an " + " ".join(bits)
    return ("NOT " if c.negate else "") + s


def readable(plan: QueryPlan) -> list[dict]:
    out = [{"label": "Population", "text": "All patients of Klinikum Nord, Süd and West, opted-out patients (Art. 71) removed"
            if plan.unit == "patients" else "All encounters of patients who did not opt out (Art. 71)"}]
    p = plan.population
    if p.age_min is not None or p.age_max is not None:
        rng = f"aged {p.age_min}+" if p.age_max is None else f"aged {p.age_min or 0}–{p.age_max}"
        out.append({"label": "Filter", "text": f"{rng} on {db.REFERENCE_DATE} (2025 minus birth year)"})
    if p.sex:
        out.append({"label": "Filter", "text": f"sex = {p.sex}"})
    if p.regions:
        out.append({"label": "Filter", "text": "region in " + ", ".join(p.regions)})
    if p.data_holders:
        out.append({"label": "Filter", "text": "hospital in " + ", ".join(p.data_holders)})
    for c in p.criteria:
        out.append({"label": "Cohort", "text": criterion_text(c)})
    if plan.unit == "encounters" and plan.encounter_filter:
        f = plan.encounter_filter
        bits = []
        if f.types:
            bits.append("type " + "/".join(f.types))
        if f.start_from or f.start_to:
            bits.append(f"started {f.start_from or '…'} to {f.start_to or '…'}")
        if f.end_from or f.end_to:
            bits.append(f"ended {f.end_from or '…'} to {f.end_to or '…'}")
        if f.primary_icd10:
            bits.append("main diagnosis " + _code_label("encounter", f.primary_icd10))
        out.append({"label": "Encounters", "text": "Counting stays/visits (not patients): " + ", ".join(bits)})
    for m in plan.measures:
        if m.hidden:
            continue
        if m.kind == "count":
            what = "stays" if plan.unit == "encounters" else "patients"
            out.append({"label": "Measure", "text": f"{m.name}: number of {what}" + (" who " + " and ".join(criterion_text(c) for c in m.criteria) if m.criteria else "")})
        elif m.kind == "pct":
            out.append({"label": "Measure", "text": f"{m.name}: {m.numerator} / {m.denominator} × 100, one decimal, halves rounded up"})
        else:
            out.append({"label": "Measure", "text": f"{m.name}: mean of each patient's latest {_code_label('observation', [m.loinc])}, one decimal"})
    for g in plan.group_by:
        if g.dim == "age_band":
            out.append({"label": "Group by", "text": "age band " + ", ".join(g.bands) + " (empty groups shown)"})
        else:
            n = len(db.domain(g.dim))
            out.append({"label": "Group by", "text": f"{g.dim.replace('_', ' ')} ({n} groups, empty groups shown)"})
    out.append({"label": "Privacy", "text": "counts below 10 shown as <10; percentages and means from fewer than 10 patients suppressed"})
    return out


def catalog_matches(plan: QueryPlan) -> list[dict]:
    titles = _titles()
    seen, out = set(), []
    crits = list(plan.population.criteria) + [c for m in plan.measures for c in m.criteria]
    for c in crits:
        for code in c.codes:
            if (c.source, code) in seen:
                continue
            seen.add((c.source, code))
            sysname = {"condition": "ICD-10", "medication": "ATC", "observation": "LOINC", "encounter": "ICD-10 (main)"}[c.source]
            label = titles.get(code) or titles.get(code[:3]) or next((v for k, v in titles.items() if k.startswith(code)), "")
            out.append({"system": sysname, "code": code, "label": label, "ok": bool(label)})
    for m in plan.measures:
        if m.loinc and ("observation", m.loinc) not in seen:
            seen.add(("observation", m.loinc))
            out.append({"system": "LOINC", "code": m.loinc, "label": titles.get(m.loinc, ""), "ok": m.loinc in titles})
    if plan.encounter_filter:
        for code in plan.encounter_filter.primary_icd10:
            out.append({"system": "ICD-10 (main)", "code": code, "label": titles.get(code[:3], ""), "ok": bool(titles.get(code[:3]))})
    return out
