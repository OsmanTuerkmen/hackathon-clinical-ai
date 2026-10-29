"""Independent pandas oracle for AccessDesk 2.

Computes the expected decision, articles and numbers of every test request
directly from the CSV files with pandas. It shares no code with the app (no
parser, compiler or privacy gate), so a bug in the app cannot hide in both.
Each request's numbers are written out by hand from its definitions, the way
a careful analyst would read them. This is test code: the app itself never
contains per-request logic.

The oracle first checks itself against the official requests/expected.json
(R01-R10) and stops if anything differs. Then it writes
tests/oracle/expected.json for R01-R10, D01-D04 and T01-T15.

Run: python tests/oracle/oracle.py --data ../TRACK-3-ehds/data
"""
import argparse
import json
import os
import sys
from decimal import ROUND_HALF_UP, Decimal

import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
REF = "2025-12-31"
REGIONS = ["Burgenland", "Kärnten", "Niederösterreich", "Oberösterreich", "Salzburg",
           "Steiermark", "Tirol", "Vorarlberg", "Wien"]
HOLDERS = ["Klinikum Nord", "Klinikum Süd", "Klinikum West"]
SEXES = ["female", "male"]
STAT = ["53", "69"]
STAT_ACCESS = ["53", "66", "69"]
SPE = ["53", "66", "68", "73"]
REJECT = ["54"]


# ---------- small-cell rule, written independently of the app ----------
def r1(x):
    return float(x.quantize(Decimal("0.1"), rounding=ROUND_HALF_UP))


def count(n):
    return "<10" if n < 10 else int(n)


def pct(num, den):
    return "suppressed" if num < 10 or den < 10 else r1(Decimal(int(num)) * 100 / Decimal(int(den)))


def mean(values10, patients):
    """values10: the values x 10; patients: distinct patients behind them."""
    if patients < 10 or not values10:
        return "suppressed"
    return r1(Decimal(sum(values10)) / 10 / Decimal(len(values10)))


def band(age, bands):
    for label in bands:
        if label.endswith("+"):
            if age >= int(label[:-1]):
                return label
        else:
            lo, hi = map(int, label.split("-"))
            if lo <= age <= hi:
                return label
    return None


# ---------- data ----------
class Data:
    def __init__(self, data_dir):
        def rd(name):
            return pd.read_csv(os.path.join(data_dir, name + ".csv"), dtype=str, keep_default_na=False,
                               encoding="utf-8")
        p, c, m, o, e = (rd(n) for n in ("patients", "conditions", "medications", "observations", "encounters"))
        self.total = len(p)
        self.opted = set(p.loc[p.opted_out.str.lower() == "true", "patient_id"])
        assert len(self.opted) == 839, len(self.opted)

        def keep(df):
            return df[~df.patient_id.isin(self.opted)].copy()
        self.p, self.c, self.m, self.o, self.e = map(keep, (p, c, m, o, e))
        self.p["age"] = 2025 - self.p.birth_date.str[:4].astype(int)
        v10 = self.o.value.map(lambda s: Decimal(s) * 10)
        assert all(v == v.to_integral_value() for v in v10), "a value has more than one decimal"
        self.o["v10"] = v10.map(int)

    def with_condition(self, *prefixes):
        return set(self.c.loc[self.c.icd10.map(lambda x: x.startswith(prefixes)), "patient_id"])

    def with_active_med(self, *prefixes):
        m = self.m
        ok = (m.atc.map(lambda x: x.startswith(prefixes)) & (m.start_date <= REF)
              & ((m.end_date == "") | (m.end_date >= REF)))
        return set(m.loc[ok, "patient_id"])

    def with_observation(self, loinc):
        return set(self.o.loc[self.o.loinc == loinc, "patient_id"])

    def latest(self, loinc):
        """patient_id -> latest value x 10 (at most one value per patient, test and day)."""
        o = self.o[self.o.loinc == loinc].sort_values(["patient_id", "date"])
        return o.groupby("patient_id").v10.last().to_dict()

    def encounters(self, enc_type, primary_prefixes=None, years=None):
        e = self.e[self.e.type == enc_type]
        if primary_prefixes:
            e = e[e.primary_icd10.map(lambda x: x.startswith(primary_prefixes))]
        if years:
            e = e[e.start_date.str[:4].isin([str(y) for y in years])]
        return e

    def patients_in(self, ids):
        return self.p[self.p.patient_id.isin(ids)]


def row(group, *values):
    return {"group": list(group), "values": list(values)}


def stat(rows, articles=STAT, funnel=None):
    out = {"decision": "APPROVE_STATISTICAL", "articles": articles, "rows": rows}
    if funnel is not None:
        out["funnel"] = funnel
    return out


def spe(n, tables, loinc, funnel):
    return {"decision": "APPROVE_SPE", "articles": SPE, "rows": None, "cohort_size": n,
            "spe_tables": tables, "spe_observation_loinc": loinc, "funnel": funnel}


def reject(_d=None):
    return {"decision": "REJECT", "articles": REJECT, "rows": None}


def in_band(df, bands, label):
    return df[df.age.map(lambda a: band(a, bands)) == label]


# ---------- official requests ----------
def R01(d):
    adults = d.p[d.p.age >= 18]
    t2d = d.with_condition("E11")
    rows = []
    for g in REGIONS:
        a = adults[adults.region == g]
        n_t = int(a.patient_id.isin(t2d).sum())
        rows.append(row([g], count(len(a)), count(n_t), pct(n_t, len(a))))
    return stat(rows, funnel=[d.total, d.total - len(d.opted), len(adults)])


def R03(d):
    bands = ["65-74", "75-84", "85+"]
    af = d.patients_in(d.with_condition("I48"))
    oac = d.with_active_med("B01AA", "B01AF")
    rows = []
    for b in bands:
        grp = in_band(af, bands, b)
        without = int((~grp.patient_id.isin(oac)).sum())
        rows.append(row([b], count(len(grp)), count(without), pct(without, len(grp))))
    in_bands = int(af.age.map(lambda a: band(a, bands) is not None).sum())
    return stat(rows, funnel=[d.total, d.total - len(d.opted), len(af), in_bands])


def R05(d):
    adults = set(d.p.loc[d.p.age >= 18, "patient_id"])
    t2d = d.with_condition("E11")
    cohort = adults & t2d & d.with_observation("4548-4")
    return spe(len(cohort), ["conditions", "medications", "observations"], ["4548-4"],
               [d.total, d.total - len(d.opted), len(adults), len(adults & t2d), len(cohort)])


def R07(d):
    e = d.encounters("inpatient", years=[2025])
    region = e.patient_id.map(d.p.set_index("patient_id").region)
    rows = [row([g], count(int((region == g).sum()))) for g in REGIONS]
    return stat(rows, funnel=[len(d.e), int((d.e.type == "inpatient").sum()), len(e)])


def R08(d):
    women = d.p[(d.p.sex == "female") & d.p.patient_id.isin(d.with_condition("C50"))]
    bmi = d.latest("39156-5")
    rows = []
    for g in REGIONS:
        ids = [i for i in women.loc[women.region == g, "patient_id"] if i in bmi]
        rows.append(row([g], count(len(ids)), mean([bmi[i] for i in ids], len(ids))))
    return stat(rows)


def R09(d):
    bands = ["18-49", "50-64", "65+"]
    htn = d.p[(d.p.age >= 18) & d.p.patient_id.isin(d.with_condition("I10"))]
    ace, arb = d.with_active_med("C09AA"), d.with_active_med("C09CA")
    rows = []
    for b in bands:
        grp = in_band(htn, bands, b)
        n = len(grp)
        rows.append(row([b], count(n), pct(int(grp.patient_id.isin(ace).sum()), n),
                        pct(int(grp.patient_id.isin(arb).sum()), n)))
    return stat(rows, articles=STAT_ACCESS)


# ---------- demo cases ----------
def D01(d):
    ckd = d.p[(d.p.age >= 18) & d.p.patient_id.isin(d.with_condition("N18"))]
    egfr = d.latest("62238-1")
    rows = []
    for h in HOLDERS:
        ids = [i for i in ckd.loc[ckd.data_holder == h, "patient_id"] if i in egfr]
        rows.append(row([h], count(len(ids)), mean([egfr[i] for i in ids], len(ids))))
    return stat(rows)


def D02(d):
    e = d.encounters("inpatient", ("S72",), years=[2023, 2024, 2025])
    los = (pd.to_datetime(e.end_date) - pd.to_datetime(e.start_date)).dt.days
    rows = []
    for h in HOLDERS:
        sel = e.data_holder == h
        rows.append(row([h], count(int(sel.sum())),
                        mean([int(x) * 10 for x in los[sel]], e.loc[sel, "patient_id"].nunique())))
    return stat(rows)


def D03(d):
    a = d.p[(d.p.age >= 18) & d.p.patient_id.isin(d.with_condition("J45"))]
    return stat([row([s], count(int((a.sex == s).sum()))) for s in SEXES])


def D04(d):
    adults = d.p[d.p.age >= 18]
    obese = d.with_condition("E66")
    rows = []
    for g in REGIONS:
        a = adults[adults.region == g]
        n_o = int(a.patient_id.isin(obese).sum())
        rows.append(row([g], count(len(a)), count(n_o), pct(n_o, len(a))))
    return stat(rows)


# ---------- own jury-style requests ----------
def T01(d):
    e = d.encounters("inpatient", ("J18",), years=[2025])
    return stat([row([h], count(int((e.data_holder == h).sum()))) for h in HOLDERS])


def T02(d):
    hf = d.p[(d.p.age >= 18) & d.p.patient_id.isin(d.with_condition("I50"))]
    sbp = d.latest("8480-6")
    rows = []
    for h in HOLDERS:
        ids = [i for i in hf.loc[hf.data_holder == h, "patient_id"] if i in sbp]
        rows.append(row([h], count(len(ids)), mean([sbp[i] for i in ids], len(ids))))
    return stat(rows)


def T03(d):
    hb = d.latest("4548-4")
    t2d = d.p[(d.p.age >= 18) & d.p.patient_id.isin(d.with_condition("E11"))]
    rows = []
    for g in REGIONS:
        ids = [i for i in t2d.loc[t2d.region == g, "patient_id"] if i in hb]
        high = sum(1 for i in ids if hb[i] > 80)          # latest HbA1c above 8.0 %
        rows.append(row([g], count(len(ids)), count(high), pct(high, len(ids))))
    return stat(rows)


def T04(d):
    bands = ["0-49", "50-64", "65-79", "80+"]
    stroke = d.patients_in(d.with_condition("I63"))       # "stroke" = ICD-10 I63 (cerebral infarction)
    return stat([row([b], count(len(in_band(stroke, bands, b)))) for b in bands])


def T08(d):
    bands = ["0-64", "65-79", "80+"]
    copd = d.patients_in(d.with_condition("J44"))
    inhaler = d.with_active_med("R03")
    rows = []
    for b in bands:
        grp = in_band(copd, bands, b)
        rows.append(row([b], count(len(grp)), pct(int(grp.patient_id.isin(inhaler).sum()), len(grp))))
    return stat(rows, articles=STAT_ACCESS)


def T09(d):
    adults = set(d.p.loc[d.p.age >= 18, "patient_id"])
    hf = d.with_condition("I50")
    cohort = adults & hf & d.with_observation("62238-1")
    return spe(len(cohort), ["conditions", "observations"], ["62238-1"],
               [d.total, d.total - len(d.opted), len(adults), len(adults & hf), len(cohort)])


def T10(d):
    af = d.patients_in(d.with_condition("I48"))
    return stat([row([h, s], count(int(((af.data_holder == h) & (af.sex == s)).sum())))
                 for h in HOLDERS for s in SEXES])


def T11(d):
    w = d.p[(d.p.sex == "female") & d.p.age.between(18, 39) & d.p.patient_id.isin(d.with_condition("I50"))]
    return stat([row([g], count(int((w.region == g).sum()))) for g in REGIONS])


def T12(d):
    bands = ["18-64", "65-79", "80+"]
    hf = d.p[(d.p.age >= 18) & d.p.patient_id.isin(d.with_condition("I50"))]
    bb = d.with_active_med("C07")
    rows = []
    for b in bands:
        grp = in_band(hf, bands, b)
        without = int((~grp.patient_id.isin(bb)).sum())
        rows.append(row([b], count(len(grp)), count(without), pct(without, len(grp))))
    return stat(rows)


def T13(d):
    e = d.encounters("inpatient", ("S72",), years=[2023, 2024, 2025])
    year = e.start_date.str[:4]
    return stat([row([y], count(int((year == y).sum()))) for y in ("2023", "2024", "2025")])


def T14(d):
    e = d.encounters("emergency", years=[2024])
    return stat([row([h], count(int((e.data_holder == h).sum()))) for h in HOLDERS])


def T15(d):
    kids = d.p[(d.p.age <= 17) & d.p.patient_id.isin(d.with_condition("J45"))]
    return stat([row([g], count(int((kids.region == g).sum()))) for g in REGIONS])


ORACLE = {
    "R01": R01, "R02": reject, "R03": R03, "R04": reject, "R05": R05,
    "R06": reject, "R07": R07, "R08": R08, "R09": R09, "R10": reject,
    "D01": D01, "D02": D02, "D03": D03, "D04": D04,
    "T01": T01, "T02": T02, "T03": T03, "T04": T04,
    "T05": reject,   # advertising disguised as "awareness" for a brand (Art. 54)
    "T06": reject,   # credit limits and repayment terms (Art. 54)
    "T07": reject,   # deciding which staff to keep (Art. 54)
    "T08": T08, "T09": T09, "T10": T10, "T11": T11, "T12": T12, "T13": T13, "T14": T14, "T15": T15,
}


def check_official(results, official):
    """The oracle must reproduce the official expected.json exactly."""
    problems = []
    for rid, exp in official.items():
        got = results[rid]
        if got["decision"] != exp["decision"] or sorted(got["articles"]) != sorted(exp["articles"]):
            problems.append(f"{rid}: decision/articles {got['decision']} {got['articles']}")
        ans = exp["answer"]
        if ans is None:
            continue
        if "cohort_size" in ans:
            if got.get("cohort_size") != ans["cohort_size"]:
                problems.append(f"{rid}: cohort {got.get('cohort_size')} != {ans['cohort_size']}")
            continue
        want = {(g,): (list(v.values()) if isinstance(v, dict) else [v]) for g, v in ans.items()}
        have = {tuple(r["group"]): r["values"] for r in got["rows"]}
        if want != have:
            problems.append(f"{rid}: {have} != {want}")
    return problems


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default=os.path.join(HERE, "..", "..", "..", "TRACK-3-ehds", "data"))
    ap.add_argument("--out", default=os.path.join(HERE, "expected.json"))
    args = ap.parse_args()
    d = Data(args.data)
    results = {rid: fn(d) for rid, fn in ORACLE.items()}
    with open(os.path.join(args.data, "..", "requests", "expected.json"), encoding="utf-8") as f:
        official = json.load(f)
    problems = check_official(results, official)
    if problems:
        print("ORACLE DOES NOT MATCH expected.json:")
        print("\n".join(problems))
        sys.exit(1)
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=1)
    print(f"oracle matches expected.json for {len(official)} official requests; "
          f"wrote {len(results)} requests to {os.path.relpath(args.out)}")


if __name__ == "__main__":
    main()
