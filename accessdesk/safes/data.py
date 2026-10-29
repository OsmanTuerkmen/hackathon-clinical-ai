"""Data minimisation, code mappings, and applicant-safe cohort funnel."""
from .outputs import protect_count
from ..plan import compiler, terminology

TABLES = ("conditions", "medications", "observations", "encounters", "patients")


def mappings(plan, store):
    result = []
    with store.lock:
        for concept in plan.concepts.values():
            entry = {
                "name": concept.name,
                "kind": concept.kind,
                "source": concept.source,
                "ai": concept.source.startswith("AI mapping:"),
                "codes": [],
            }
            if concept.kind == "condition":
                for prefix in concept.prefixes:
                    rows = store.con.execute(
                        "SELECT icd10, MAX(description), COUNT(*) FROM conditions "
                        "WHERE icd10 LIKE ? GROUP BY icd10",
                        [prefix + "%"],
                    ).fetchall()
                    entry["codes"].extend({
                        "system": "ICD-10", "prefix": prefix, "code": code,
                        "label": description, "rows": protect_count(count),
                    } for code, description, count in rows)
                    if not any(code["prefix"] == prefix for code in entry["codes"]):
                        entry["codes"].append({
                            "system": "ICD-10", "prefix": prefix, "code": prefix,
                            "label": terminology.label_for("icd10", prefix), "rows": protect_count(0),
                        })
            elif concept.kind == "medication":
                for prefix in concept.prefixes:
                    rows = store.con.execute(
                        "SELECT atc, MAX(name), COUNT(*) FROM medications "
                        "WHERE atc LIKE ? GROUP BY atc",
                        [prefix + "%"],
                    ).fetchall()
                    entry["codes"].extend({
                        "system": "ATC", "prefix": prefix, "code": code,
                        "label": name, "rows": protect_count(count),
                    } for code, name, count in rows)
                    if not any(code["prefix"] == prefix for code in entry["codes"]):
                        entry["codes"].append({
                            "system": "ATC", "prefix": prefix, "code": prefix,
                            "label": terminology.label_for("atc", prefix), "rows": protect_count(0),
                        })
            elif concept.kind == "observation":
                count, name = store.con.execute(
                    "SELECT COUNT(*), MAX(name) FROM observations WHERE loinc = ?",
                    [concept.loinc],
                ).fetchone()
                entry["codes"].append({
                    "system": "LOINC", "prefix": concept.loinc, "code": concept.loinc,
                    "label": name, "rows": protect_count(count),
                })
            elif concept.kind == "encounter":
                conditions, args = [], []
                if concept.enc_type:
                    conditions.append("type = ?")
                    args.append(concept.enc_type)
                for prefix in concept.primary_prefixes:
                    conditions.append("primary_icd10 LIKE ?")
                    args.append(prefix + "%")
                where = " AND ".join(conditions) or "true"
                count = store.con.execute(
                    f"SELECT COUNT(*) FROM encounters WHERE {where}", args
                ).fetchone()[0]
                label = f"type = {concept.enc_type or 'any'}"
                if concept.primary_prefixes:
                    label += f", main diagnosis {', '.join(concept.primary_prefixes)}"
                entry["codes"].append({
                    "system": "Encounter", "prefix": "", "code": label,
                    "label": "", "rows": protect_count(count),
                })
            elif concept.kind == "age":
                low = concept.min if concept.min is not None else 0
                value = f"{low}–{concept.max}" if concept.max is not None else f"≥ {low}"
                entry["codes"].append({
                    "system": "Age on 31 Dec 2025", "prefix": "", "code": value,
                    "label": "", "rows": None,
                })
            elif concept.kind in ("sex", "region"):
                entry["codes"].append({
                    "system": concept.kind.title(), "prefix": "", "code": concept.value,
                    "label": "", "rows": None,
                })
            elif concept.kind == "los":
                entry["codes"].append({
                    "system": "Computed", "prefix": "", "code": "end_date − start_date (days)",
                    "label": "", "rows": None,
                })
            elif concept.kind == "composite":
                entry["codes"].append({
                    "system": "Combination", "prefix": "", "code": concept.phrase,
                    "label": "", "rows": None,
                })
            result.append(entry)
    return result


def applicant_funnel(plan, store):
    return compiler.funnel(plan, store)


def minimisation_summary(decision, plan, manifest=None):
    if decision == "APPROVE_STATISTICAL":
        en = "Only reviewed, small-cell-gated aggregates leave the access body."
        de = "Nur geprüfte, gegen kleine Zellen geschützte Aggregate verlassen die Behörde."
        tables = []
    elif decision == "APPROVE_SPE":
        copied = [table["table"] for table in (manifest or {}).get("tables_copied", [])]
        en = "Only the selected cohort and requested record types are copied to a separate workspace."
        de = "Nur die ausgewählte Kohorte und angefragte Datentypen werden in eine getrennte Umgebung kopiert."
        tables = copied
    else:
        en = "No patient query is run for a rejected request."
        de = "Für abgelehnte Anträge wird keine Patientenabfrage ausgeführt."
        tables = []
    requested = [record.table for record in plan.record_types]
    return {
        "summary_en": en,
        "summary_de": de,
        "requested_record_types": requested,
        "copied_record_types": tables,
        "not_copied_record_types": [table for table in TABLES if table not in tables],
    }
