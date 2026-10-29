"""Compiles validated query plans into parameter-free, whitelisted DuckDB SQL."""
import itertools
import re
from decimal import Decimal

from ..store import REFERENCE_DATE
from .model import QueryPlan

SAFE_CODE = re.compile(r"^[A-Z0-9][A-Z0-9.\-]{0,9}$")
SAFE_VALUE = re.compile(r"^[A-Za-zÄÖÜäöüß \-]{1,40}$")
SAFE_BAND = re.compile(r"^<?\d{1,3}(?:-\d{1,3}|\+)?$")


class PlanError(ValueError):
    pass


def _code(value):
    value = str(value).upper().strip()
    if not SAFE_CODE.fullmatch(value):
        raise PlanError(f"Unsafe code in plan: {value!r}")
    return value


def _text(value):
    value = str(value)
    if not SAFE_VALUE.fullmatch(value):
        raise PlanError(f"Unsafe value in plan: {value!r}")
    return value


def _like_any(column, prefixes):
    if not prefixes:
        raise PlanError(f"Empty code list for {column}")
    return "(" + " OR ".join(f"{column} LIKE '{_code(prefix)}%'" for prefix in prefixes) + ")"


def _age_case(bands, column):
    if not bands:
        raise PlanError("Age-band grouping requires at least one band")
    parts = []
    for band in bands:
        if not SAFE_BAND.fullmatch(band["label"]):
            raise PlanError(f"Unsafe age band label {band['label']!r}")
        low, high = int(band["min"]), band.get("max")
        condition = f"{column} >= {low}"
        if high is not None:
            condition += f" AND {column} <= {int(high)}"
        parts.append(f"WHEN {condition} THEN '{band['label']}'")
    return "CASE " + " ".join(parts) + " END"


class Compiler:
    def __init__(self, plan, store):
        if not isinstance(plan, QueryPlan):
            raise PlanError("Compiler requires a validated QueryPlan")
        self.plan = plan.model_dump(mode="python")
        self.store = store
        self.concepts = self.plan["concepts"]
        self.ctes = {}
        self.joins = {}
        self._validate_domains()

    def _validate_domains(self):
        for concept in self.concepts.values():
            domain = {"sex": "sex", "region": "region"}.get(concept["kind"])
            if domain and concept.get("value") not in self.store.domains[domain]:
                raise PlanError(f"Value outside the {domain} domain")
        for group in self.plan["groups"]:
            dim = group["dim"]
            if dim in ("region", "data_holder", "sex") and dim not in self.store.domains:
                raise PlanError(f"Unknown grouping dimension {dim}")

    def set_cte(self, term):
        concept = self.concepts[term["concept"]]
        kind = concept["kind"]
        if kind == "condition":
            name = f"s_{concept['id']}"
            sql = f"SELECT DISTINCT patient_id FROM conditions WHERE {_like_any('icd10', concept['prefixes'])}"
        elif kind == "medication":
            active = bool(term.get("active"))
            name = f"s_{concept['id']}_{'active' if active else 'any'}"
            sql = f"SELECT DISTINCT patient_id FROM medications WHERE {_like_any('atc', concept['prefixes'])}"
            if active:
                sql += (
                    f" AND start_date <= DATE '{REFERENCE_DATE}'"
                    f" AND (end_date IS NULL OR end_date >= DATE '{REFERENCE_DATE}')"
                )
        elif kind == "observation":
            comparison = term.get("cmp")
            if comparison:
                op = comparison["op"]
                if op not in (">", ">=", "<", "<="):
                    raise PlanError(f"Unsafe comparator {op!r}")
                try:
                    value10 = int(Decimal(str(comparison["value"])) * 10)
                except Exception as exc:
                    raise PlanError("Invalid observation comparison value") from exc
                suffix = {">": "gt", ">=": "ge", "<": "lt", "<=": "le"}[op]
                name = f"s_{concept['id']}_{suffix}{value10}"
                sql = f"SELECT patient_id FROM {self.latest_cte(concept)} WHERE value10 {op} {value10}"
            else:
                name = f"s_{concept['id']}"
                sql = f"SELECT DISTINCT patient_id FROM observations WHERE loinc = '{_code(concept['loinc'])}'"
        elif kind == "encounter":
            years = term.get("years")
            name = f"s_{concept['id']}" + ("_" + "_".join(self._year(year) for year in years) if years else "")
            sql = (
                "SELECT DISTINCT patient_id FROM encounters WHERE "
                f"{self.enc_cond(concept, years, alias=None)}"
            )
        else:
            raise PlanError(f"Concept kind {kind} cannot form a patient set")
        self.ctes.setdefault(name, sql)
        return name

    def latest_cte(self, concept):
        name = f"v_{concept['id']}"
        self.ctes.setdefault(
            name,
            "SELECT patient_id, value10 FROM (SELECT patient_id, value10, ROW_NUMBER() OVER "
            "(PARTITION BY patient_id ORDER BY date DESC) AS rn "
            f"FROM observations WHERE loinc = '{_code(concept['loinc'])}') WHERE rn = 1",
        )
        return name

    @staticmethod
    def _year(year):
        try:
            value = int(year)
        except (TypeError, ValueError) as exc:
            raise PlanError(f"Invalid year {year!r}") from exc
        if value < 1900 or value > 2100:
            raise PlanError(f"Invalid year {year!r}")
        return str(value)

    def enc_cond(self, concept, years=None, alias="e"):
        prefix = f"{alias}." if alias else ""
        conditions = []
        if concept.get("enc_type"):
            value = _text(concept["enc_type"])
            if value not in self.store.domains["encounter_type"]:
                raise PlanError("Encounter type outside the store domain")
            conditions.append(f"{prefix}type = '{value}'")
        if concept.get("primary_prefixes"):
            conditions.append(_like_any(f"{prefix}primary_icd10", concept["primary_prefixes"]))
        if years:
            year_values = ", ".join(self._year(year) for year in years)
            conditions.append(f"year({prefix}start_date) IN ({year_values})")
        return " AND ".join(conditions) or "1 = 1"

    def cond(self, terms, skip=(), where=False):
        patient_col = (lambda col: f"p.{col}") if where else (lambda col: f"b.{col}")
        patient_id = "p.patient_id" if where else "b.patient_id"
        encounter_alias = "e" if where else "b"
        parts = []
        for term in terms:
            if term["concept"] in skip:
                continue
            concept = self.concepts[term["concept"]]
            kind = concept["kind"]
            if kind == "age":
                bounds = []
                if concept.get("min") is not None:
                    bounds.append(f"{patient_col('age')} >= {int(concept['min'])}")
                if concept.get("max") is not None:
                    bounds.append(f"{patient_col('age')} <= {int(concept['max'])}")
                expression = "(" + " AND ".join(bounds) + ")" if bounds else "1 = 1"
            elif kind in ("sex", "region"):
                domain = self.store.domains[kind]
                value = _text(concept["value"])
                if value not in domain:
                    raise PlanError(f"Value outside the {kind} domain")
                expression = f"{patient_col(kind)} = '{value}'"
            elif kind == "encounter" and self.plan["unit"] == "encounter":
                expression = "(" + self.enc_cond(concept, term.get("years"), encounter_alias) + ")"
            elif kind in ("los", "composite"):
                continue
            else:
                expression = f"{patient_id} IN (SELECT patient_id FROM {self.set_cte(term)})"
            parts.append(f"NOT {expression}" if term.get("neg") else expression)
        return " AND ".join(parts)

    def compile(self):
        plan = self.plan
        unit = plan["unit"]
        population_ids = {term["concept"] for term in plan["population"]}
        group_columns = []
        for group in plan["groups"]:
            dim = group["dim"]
            if dim == "region":
                group_columns.append(("g_region", "p.region"))
            elif dim == "data_holder":
                group_columns.append(("g_data_holder", "e.data_holder" if unit == "encounter" else "p.data_holder"))
            elif dim == "sex":
                group_columns.append(("g_sex", "p.sex"))
            elif dim == "age_band":
                group_columns.append(("g_age_band", _age_case(group["bands"], "p.age")))
            elif dim == "year":
                if unit != "encounter":
                    raise PlanError("Grouping by year is only supported for stays/encounters")
                group_columns.append(("g_year", "CAST(year(e.start_date) AS VARCHAR)"))

        if unit == "encounter":
            encounter = self.concepts.get(plan.get("encounter_concept") or "", {})
            select = [
                "e.encounter_id", "e.patient_id", "e.los_days", "e.type", "e.primary_icd10",
                "e.start_date", "e.data_holder AS enc_holder", "p.age", "p.sex", "p.region",
            ]
            from_clause = "FROM encounters e JOIN patients p ON p.patient_id = e.patient_id"
            where = ["p.opted_out = false"]
            if encounter:
                where.append(self.enc_cond(encounter, plan.get("unit_years")))
            elif plan.get("unit_years"):
                where.append(self.enc_cond({}, plan["unit_years"]))
            population_ids.add(plan.get("encounter_concept"))
        else:
            select = ["p.patient_id", "p.age", "p.sex", "p.region", "p.data_holder"]
            from_clause = "FROM patients p"
            where = ["p.opted_out = false"]
        select.extend(f"{expression} AS {name}" for name, expression in group_columns)
        population = self.cond(plan["population"], skip={plan.get("encounter_concept")}, where=True)
        if population:
            where.append(population)
        for name, expression in group_columns:
            if name == "g_age_band":
                where.append(f"{expression} IS NOT NULL")

        columns, layout = [], []
        cell_expressions, cell_fields = [], []
        unit_id = "b.encounter_id" if unit == "encounter" else "b.patient_id"
        for index, measure in enumerate(plan["measures"]):
            if measure["type"] == "count":
                condition = self.cond(measure["set"], skip=population_ids)
                cell_expressions.append(
                    f"CASE WHEN {condition or '1 = 1'} THEN {unit_id} END"
                )
                cell_fields.append((measure["key"], "value"))
                columns.append(
                    f"SUM(CASE WHEN {condition} THEN 1 ELSE 0 END) AS m{index}"
                    if condition else f"COUNT(*) AS m{index}"
                )
                layout.append((measure["key"], "count", [f"m{index}"]))
            elif measure["type"] == "pct":
                numerator = self.cond(measure["num_set"], skip=population_ids) or "1 = 1"
                denominator = self.cond(measure["den_set"], skip=population_ids) or "1 = 1"
                cell_expressions.extend([
                    f"CASE WHEN {numerator} THEN {unit_id} END",
                    f"CASE WHEN {denominator} THEN {unit_id} END",
                ])
                cell_fields.extend([(measure["key"], "num"), (measure["key"], "den")])
                columns.extend([
                    f"SUM(CASE WHEN {numerator} THEN 1 ELSE 0 END) AS m{index}_num",
                    f"SUM(CASE WHEN {denominator} THEN 1 ELSE 0 END) AS m{index}_den",
                ])
                layout.append((measure["key"], "pct", [f"m{index}_num", f"m{index}_den"]))
            elif measure["type"] == "mean":
                value_concept = self.concepts[measure["value"]]
                condition = self.cond(measure["set"], skip=population_ids) or "1 = 1"
                if value_concept["kind"] == "los":
                    value = "b.los_days * 10"
                else:
                    latest = self.latest_cte(value_concept)
                    self.joins[latest] = f"LEFT JOIN {latest} ON {latest}.patient_id = b.patient_id"
                    value = f"{latest}.value10"
                cell_expressions.append(
                    f"CASE WHEN ({condition}) AND {value} IS NOT NULL THEN b.patient_id END"
                )
                cell_fields.append((measure["key"], "patients"))
                columns.extend([
                    f"SUM(CASE WHEN {condition} THEN {value} END) AS m{index}_sum10",
                    f"COUNT(CASE WHEN {condition} THEN {value} END) AS m{index}_n",
                    f"COUNT(DISTINCT CASE WHEN {condition} AND {value} IS NOT NULL "
                    f"THEN b.patient_id END) AS m{index}_patients",
                ])
                layout.append((measure["key"], "mean", [
                    f"m{index}_sum10", f"m{index}_n", f"m{index}_patients",
                ]))
            else:
                raise PlanError(f"Unknown measure type {measure['type']!r}")

        ctes = [f"{name} AS (\n    {sql}\n)" for name, sql in self.ctes.items()]
        ctes.append(
            "base AS (\n    SELECT " + ",\n           ".join(select) + f"\n    {from_clause}\n    WHERE "
            + "\n      AND ".join(where) + "\n)"
        )
        group_names = [name for name, _ in group_columns]
        sql = (
            "-- Opted-out patients are excluded at ingestion and checked again.\n"
            "WITH " + ",\n".join(ctes) + "\nSELECT " + ", ".join(group_names + columns)
            + "\nFROM base b" + "".join("\n" + join for join in self.joins.values())
            + (f"\nGROUP BY {', '.join(group_names)}" if group_names else "")
        )
        self.cell_fields = cell_fields
        self.cell_group_names = group_names
        self.cell_sql = (
            "WITH " + ",\n".join(ctes) + "\nSELECT "
            + ", ".join([*(f"b.{name}" for name in group_names), *cell_expressions])
            + "\nFROM base b" + "".join("\n" + join for join in self.joins.values())
        )
        return sql, group_names, layout

    def cohort_sql(self):
        plan = self.plan
        population_ids = {term["concept"] for term in plan["population"]}
        population = self.cond(plan["population"], where=True)
        cohort = self.cond(plan["cohort"], skip=population_ids)
        ctes = [f"{name} AS ({sql})" for name, sql in self.ctes.items()]
        where = ["p.opted_out = false"] + ([population] if population else [])
        base = (
            "base AS (SELECT p.patient_id, p.age, p.sex, p.region FROM patients p WHERE "
            + " AND ".join(where) + ")"
        )
        return (
            "WITH " + ", ".join(ctes + [base]) + " SELECT b.patient_id FROM base b"
            + (f" WHERE {cohort}" if cohort else "")
        )


def domains_for(plan, store):
    result = []
    for group in plan.groups:
        if group.dim == "age_band":
            result.append([band.label for band in group.bands])
        elif group.dim == "year":
            result.append([str(year) for year in (group.years or [2023, 2024, 2025])])
        else:
            result.append(list(store.domains[group.dim]))
    return result


def run(plan, store):
    compiler = Compiler(plan, store)
    sql, group_names, layout = compiler.compile()
    with store.lock:
        cursor = store.con.execute(sql)
        names = [description[0] for description in cursor.description]
        rows = {}
        for row in cursor.fetchall():
            record = dict(zip(names, row))
            key = tuple(record[group] for group in group_names)
            rows[key] = record
    combinations = list(itertools.product(*domains_for(plan, store))) if group_names else [()]
    for key in rows:
        if key not in combinations and all(value is not None for value in key):
            combinations.append(key)
    raw = {}
    for key in combinations:
        record = rows.get(key, {})
        raw[key] = {
            measure: {
                "type": measure_type,
                **{
                    column.split("_", 1)[1] if "_" in column else "value": (record.get(column) or 0)
                    for column in columns
                },
            }
            for measure, measure_type, columns in layout
        }
    return {"sql": sql, "group_names": group_names, "raw": raw, "layout": layout}


def cell_sets(plan, store):
    compiled = Compiler(plan, store)
    compiled.compile()
    with store.lock:
        rows = store.con.execute(compiled.cell_sql).fetchall()
    result = {}
    group_count = len(compiled.cell_group_names)
    for row in rows:
        group = tuple(row[:group_count])
        for index, field in enumerate(compiled.cell_fields):
            unit_id = row[group_count + index]
            if unit_id is not None:
                result.setdefault((group, *field), set()).add(unit_id)
    return result


def funnel(plan, store):
    compiler = Compiler(plan, store)
    result = []

    def add(key, label_en, label_de, count):
        result.append({"key": key, "label_en": label_en, "label_de": label_de, "count": int(count)})

    if plan.unit == "encounter":
        with store.lock:
            count = store.con.execute(
                "SELECT COUNT(*) FROM encounters e JOIN patients p ON p.patient_id = e.patient_id "
                "WHERE p.opted_out = false"
            ).fetchone()[0]
        add("eligible_encounters", "Stays of non-opted-out patients", "Aufenthalte nicht widersprechender Personen", count)
        encounter = compiler.concepts.get(plan.encounter_concept or "", {})
        condition = compiler.enc_cond(encounter, alias="e") if encounter else "1 = 1"
        if encounter and (encounter.get("enc_type") or encounter.get("primary_prefixes")):
            with store.lock:
                filtered = store.con.execute(
                    "SELECT COUNT(*) FROM encounters e JOIN patients p ON p.patient_id = e.patient_id "
                    f"WHERE p.opted_out = false AND {condition}"
                ).fetchone()[0]
            add("encounter_filter", "After encounter filter", "Nach Aufenthaltsfilter", filtered)
        if plan.unit_years:
            year_condition = compiler.enc_cond({}, plan.unit_years, alias="e")
            with store.lock:
                filtered = store.con.execute(
                    "SELECT COUNT(*) FROM encounters e JOIN patients p ON p.patient_id = e.patient_id "
                    f"WHERE p.opted_out = false AND {condition} AND {year_condition}"
                ).fetchone()[0]
            add("unit_years", "After requested years", "Nach den angefragten Jahren", filtered)
        return result

    add("all_patients", "All people in the data set", "Alle Personen im Datensatz", store.total_patients)
    with store.lock:
        count = store.con.execute(
            "SELECT COUNT(*) FROM patients WHERE opted_out = false"
        ).fetchone()[0]
    add("not_opted_out", "Without opt-out (Art. 71)", "Ohne Widerspruch (Art. 71)", count)

    selected = []
    seen = set()

    def count_terms(terms, age_filter=None):
        condition = compiler.cond(terms, where=True)
        ctes = [f"{name} AS ({sql})" for name, sql in compiler.ctes.items()]
        statement = ("WITH " + ", ".join(ctes) + " " if ctes else "")
        statement += "SELECT COUNT(*) FROM patients p WHERE p.opted_out = false"
        if condition:
            statement += f" AND {condition}"
        if age_filter:
            statement += f" AND {age_filter}"
        with store.lock:
            return store.con.execute(statement).fetchone()[0]

    for term in [*plan.population, *plan.cohort]:
        identity = (
            term.concept, term.neg, term.active,
            (term.cmp.op, term.cmp.value) if term.cmp else None,
            tuple(term.years) if term.years is not None else None,
        )
        if identity in seen:
            continue
        seen.add(identity)
        selected.append(term.model_dump(mode="python"))
        concept = compiler.concepts[term.concept]
        after = f"+ {concept['name']}"
        add(
            f"term_{len(seen)}_{term.concept}",
            after,
            after,
            count_terms(selected),
        )

    age_groups = [group for group in plan.groups if group.dim == "age_band"]
    if age_groups:
        age_filter = " AND ".join(
            f"({_age_case([band.model_dump(mode='python') for band in group.bands], 'p.age')} IS NOT NULL)"
            for group in age_groups
        )
        age_count = count_terms(selected, age_filter)
        previous_count = count_terms(selected)
        if age_count != previous_count:
            add(
                "age_bands",
                "Within the requested age bands",
                "Innerhalb der angefragten Altersgruppen",
                age_count,
            )
    return result
