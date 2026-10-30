"""Reproduce expected.json by hand to pin down semantics (opt-out, age, latest value, active meds)."""
import duckdb, json, sys
D = sys.argv[1]
con = duckdb.connect()
for t in ["patients", "conditions", "medications", "observations", "encounters"]:
    con.execute(f"create view {t} as select * from read_csv_auto('{D}/data/{t}.csv', all_varchar=true)")
exp = json.load(open(f"{D}/requests/expected.json"))

def q(sql): return con.execute(sql).fetchall()

for optout in (True, False):
    P = "select *, 2025-cast(substr(birth_date,1,4) as int) age from patients" + (" where opted_out='false'" if optout else "")
    con.execute(f"create or replace view P as {P}")
    r01 = q("""select region, count(*), count(*) filter (where patient_id in (select patient_id from conditions where icd10 like 'E11%'))
               from P where age>=18 group by 1 order by 1""")
    r05 = q("""select count(*) from P where age>=18 and patient_id in (select patient_id from conditions where icd10 like 'E11%')
               and patient_id in (select patient_id from observations where loinc='4548-4')""")
    r07 = q("""select p.region, count(*) from encounters e join P p using(patient_id)
               where e.type='inpatient' and e.start_date like '2025%' group by 1 order by 1""")
    print("excl opt-out" if optout else "incl opt-out", "R01 Burgenland", r01[0], "exp", exp["R01"]["answer"]["Burgenland"],
          "| R05", r05, "exp", exp["R05"]["answer"], "| R07 Burgenland", r07[0], "exp", exp["R07"]["answer"]["Burgenland"])

# with opt-out excluded, check R03, R08, R09 semantics
con.execute("create or replace view P as select *, 2025-cast(substr(birth_date,1,4) as int) age from patients where opted_out='false'")
active = "start_date<='2025-12-31' and (end_date is null or end_date='' or end_date>='2025-12-31')"
print("R03", q(f"""with af as (select * from P where age>=65 and patient_id in (select patient_id from conditions where icd10 like 'I48%'))
 select case when age<75 then '65-74' when age<85 then '75-84' else '85+' end b, count(*),
 count(*) filter (where patient_id not in (select patient_id from medications where (atc like 'B01AA%' or atc like 'B01AF%') and {active}))
 from af group by 1 order by 1"""), exp["R03"]["answer"])
print("R08", q("""with w as (select p.region, o.value::double v, row_number() over (partition by o.patient_id order by o.date desc) rn
 from P p join observations o using(patient_id) where p.sex='female' and o.loinc='39156-5'
 and p.patient_id in (select patient_id from conditions where icd10 like 'C50%'))
 select region, count(*), round(avg(v),2) from w where rn=1 group by 1 order by 1"""))
print("R08 exp", exp["R08"]["answer"])
print("R09", q(f"""with h as (select * from P where age>=18 and patient_id in (select patient_id from conditions where icd10 like 'I10%'))
 select case when age<50 then '18-49' when age<65 then '50-64' else '65+' end b, count(*),
 100.0*count(*) filter (where patient_id in (select patient_id from medications where atc like 'C09AA%' and {active}))/count(*),
 100.0*count(*) filter (where patient_id in (select patient_id from medications where atc like 'C09CA%' and {active}))/count(*)
 from h group by 1 order by 1"""), exp["R09"]["answer"])
# exact-half rounding cases matter?
print("R01 raw prevalences", [(r, round(100*d/a, 4)) for r, a, d in q("""select region, count(*), count(*) filter (where patient_id in (select patient_id from conditions where icd10 like 'E11%')) from P where age>=18 group by 1 order by 1""")])
# age by exact birthday vs year-diff: does it change R01?
print("ties in latest obs same date:", q("select count(*) from (select patient_id, loinc, date, count(*) c from observations group by all having c>1)"))
