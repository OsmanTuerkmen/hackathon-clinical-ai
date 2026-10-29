# EHDS Access Desk – Implementierungsplan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Every task runs with superpowers:test-driven-development.

**Goal:** Eine Web-App mit CLI, die EHDS-Anträge (JSON) automatisch entscheidet, Statistik mit Small-Cell-Regel aus 20.000 synthetischen Patienten berechnet und für SPE-Anträge eine abgeschottete Kopie mit Download-Sperre anlegt.

**Architecture:** Deterministischer Regelparser übersetzt `definitions` in eine typisierte `QuerySpec`; ein Compiler erzeugt parametrisiertes DuckDB-SQL auf Opt-out-gefilterten Views; ein zentrales Disclosure-Modul erzwingt Small-Cell-Regel und Leak-Guard. Entscheidungsleiter ist reiner Code; Claude ist optional und sieht nur Antragstext.

**Tech Stack:** Python 3.14, DuckDB 2.0, Pydantic 2, FastAPI + Uvicorn, python-dotenv, pytest, httpx (TestClient), optional `anthropic`. Frontend: statisches HTML/CSS/Vanilla-JS.

**Spec:** `docs/superpowers/specs/2026-10-29-ehds-access-desk-design.md` (mitlesen!). Gesetz: `docs/LAW.md`.

## Global Constraints

- Paketname `ehds_desk` unter `src/ehds_desk/`; Tests unter `tests/`; Python ≥ 3.12, entwickelt auf 3.14.
- Datenpfad: ENV `TRACK3_DATA`; sonst erster Vorfahr des Repo-Wurzelverzeichnisses, der `track3/requests/expected.json` enthält (funktioniert aus `.claude/worktrees/…`). CSVs nie ins Repo kopieren.
- Laufzeitdaten nur unter `EHDS_VAR_DIR` (Default `<repo>/var`); `var/`, `.env`, `*.duckdb`, `*.csv` sind gitignored.
- Referenzdatum `date(2025, 12, 31)`; Alter = `2025 − Geburtsjahr`; Medikament aktiv ⇔ `start_date ≤ 2025-12-31 AND (end_date IS NULL OR end_date ≥ 2025-12-31)`.
- Opt-out-Patienten fehlen in allen Views ohne `_all`-Suffix; nur Staff-Kennzahl „opt-out exclusions“ nutzt `_all`-Views.
- Small-Cell: Schwelle `10`; Count `< 10` → `"<10"`; Prozent mit Zähler oder Nenner `< 10` → `"suppressed"`; Mittelwert mit `n < 10` → `"suppressed"`; Rundung `Decimal.quantize(Decimal("0.1"), ROUND_HALF_UP)`; kein Float vor der Rundung.
- Antworten (Applicant und Staff) enthalten nie Patienten-IDs (`p-[0-9a-f]{8}`) außerhalb der SPE-Vorschau und nie rohe Counts `< 10`.
- An externe Dienste geht nur der Antrag (JSON-Felder) plus Code-Katalog (Codes + Beschreibungen, keine Zeilen).
- SQL-Werte (Codes, Daten, Labels) nur als Parameter, nie per String-Konkatenation; Tabellennamen nur aus Whitelist.
- UI-Texte, Begründungen, README: Englisch. Doku in `docs/`: Deutsch.
- Befehle (Git Bash, aus dem Worktree): `.venv/Scripts/python -m pytest -q`; Server `.venv/Scripts/python -m ehds_desk serve`.
- Commits: klein, Conventional Commits, enden mit `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`. Vor jedem Commit `git status` prüfen (keine CSV, keine `var/`, keine `.env`). Kein Push.
- Doku-Pflege (WORKLOG, STATUS, TODO, DECISIONS) macht der Controller nach jedem Task, nicht die Implementer-Subagents.

## Review Focus

1. Jury-Formulierungen für Gruppen („by hospital“, „per data holder“, „by sex/gender“, „for each hospital and age band“) müssen auf die richtige Dimension fallen – Test in Task 7 (`test_group_by_synonyms`).
2. Antrags-JSON ohne optionale Felder (`submitted`, `requested_format`, `country`) oder mit Zusatzfeldern darf nicht 500 werfen – Test in Task 11 (`test_process_minimal_request`).
3. Begriff ohne Code, der nicht abbildbar ist (z. B. „Gout = any diagnosis of gout“), liefert Staff-Warnung + „needs manual review“ statt erfundener Zahl – Test in Task 9 (`test_unmappable_term_needs_review`).
4. Gleicher SPE-Antrag zweimal hintereinander (Windows-Dateisperren, Idempotenz) liefert identisches Manifest ohne Fehler – Test in Task 8 (`test_provision_twice_is_idempotent`).
5. Umlaute/Sonderzeichen in Pfad (`BüsraTürkmen`), Regionen (`Kärnten`) und Namen (`Hadžić`) – Tests in Task 1 (`test_loads_from_unicode_path`) und Task 11 (`test_process_r05_unicode`).

---

### Task 1: Gerüst, Konfiguration, Datenschicht, Start-Doku

**Files:**
- Create: `pyproject.toml`, `.env.example`, `src/ehds_desk/__init__.py`, `src/ehds_desk/config.py`, `src/ehds_desk/data.py`, `tests/conftest.py`, `tests/test_data.py`
- Create (Doku-Gerüst, kurz): `CLAUDE.md`, `AGENTS.md` (nur Verweis auf CLAUDE.md), `docs/STATUS.md`, `docs/TODO.md`, `docs/DECISIONS.md` (ADR-001…005 aus Spec §2), `docs/WORKLOG.md`

**Interfaces:**
- Produces:
  - `config.REFERENCE_DATE: date`, `config.SMALL_CELL_THRESHOLD = 10`
  - `@dataclass(frozen=True) class Settings: data_dir: Path; var_dir: Path; llm_mode: Literal["auto","off"]; anthropic_api_key: str | None; llm_model: str`
  - `config.load_settings() -> Settings` (liest `.env` via python-dotenv, ENV `TRACK3_DATA`, `EHDS_VAR_DIR`, `EHDS_LLM`, `ANTHROPIC_API_KEY`, `EHDS_LLM_MODEL`)
  - `data.REGIONS: tuple[str, ...]` = die 9 Bundesländer alphabetisch (`Burgenland, Kärnten, Niederösterreich, Oberösterreich, Salzburg, Steiermark, Tirol, Vorarlberg, Wien`); `data.SEXES = ("female", "male")`
  - `class Database: __init__(self, data_dir: Path)`; Attribute `data_holders: tuple[str, ...]` (sortiert, aus Daten); Methode `cursor() -> duckdb.DuckDBPyConnection`
  - `data.get_database(settings: Settings | None = None) -> Database` (prozessweit gecacht)
  - Tabellen `raw_patients|raw_conditions|raw_medications|raw_observations|raw_encounters` (typisiert: DATE, BOOLEAN, `value DECIMAL(10,2)`), Views `pat, cond, med, obs, enc` (nur nicht-opted-out; `pat` hat Spalte `age INTEGER`) und `pat_all, cond_all, med_all, obs_all, enc_all`.

- [ ] **Step 1: `pyproject.toml`** mit Abhängigkeiten `duckdb>=2.0`, `pydantic>=2.10`, `fastapi`, `uvicorn`, `python-dotenv`; Extras `dev = [pytest, httpx]`, `llm = [anthropic]`; Script-Entry nicht nötig (`python -m ehds_desk`). Venv anlegen: `python -m venv .venv && .venv/Scripts/pip install -e ".[dev,llm]"`.
- [ ] **Step 2: Failing tests** in `tests/test_data.py` (Fixture `db` session-scoped in `conftest.py`):
  - `test_raw_and_consented_counts`: `raw_patients` 20000 Zeilen, `pat` 19161.
  - `test_age_and_region`: `SELECT count(*) FROM pat WHERE age >= 18 AND region = 'Burgenland'` = 532.
  - `test_child_views_exclude_opt_out`: Anzahl Patienten mit HbA1c in `obs` < in `obs_all`; kein `patient_id` aus `obs` hat `opted_out = true`.
  - `test_data_holders`: `db.data_holders == ("Klinikum Nord", "Klinikum Süd", "Klinikum West")`.
  - `test_loads_from_unicode_path`: `settings.data_dir` enthält auf dieser Maschine `ü`; Laden klappt (implizit), zusätzlich `"Kärnten" in REGIONS` und in `SELECT DISTINCT region FROM pat`.
  - `test_settings_find_track3_from_worktree`: ohne ENV `TRACK3_DATA` findet `load_settings()` ein Verzeichnis mit `requests/expected.json`.
- [ ] **Step 3: Run** `.venv/Scripts/python -m pytest tests/test_data.py -q` → FAIL (ImportError).
- [ ] **Step 4: Implementieren.** CSV-Import über `read_csv(?, header=true, columns={…})` mit expliziten Typen; leere `end_date`/`primary_icd10` → NULL. Falls DuckDB den Unicode-Pfad nicht öffnet: Datei in Python öffnen und via `read_csv` auf ein `io`-Objekt bzw. pandas-freien Fallback (`con.read_csv(file_obj)`) laden – kein Kopieren auf die Platte.
- [ ] **Step 5: Run** → PASS. Doku-Gerüst schreiben (CLAUDE.md: Überblick, Befehle, Architektur kurz, harte Regeln aus Global Constraints, Superpowers-Workflow, Verweise; AGENTS.md: „Siehe CLAUDE.md“).
- [ ] **Step 6: Commit** `feat: project scaffold, settings and DuckDB data layer with opt-out views`.

### Task 2: Modelle (Schnittstellen)

**Files:** Create `src/ehds_desk/models.py`, `tests/test_models.py`

**Interfaces:**
- Produces (Pydantic v2, alle `model_config = ConfigDict(frozen=True)` außer `AccessRequest` mit `extra="allow"`):
  - `Applicant(name: str, organisation: str, country: str | None = None)`
  - `AccessRequest(id: str, submitted: str | None = None, applicant: Applicant, requested_as: str, requested_format: str | None = None, purpose: str, question: str, definitions: list[str])`; Methode `full_text() -> str` (purpose + question + definitions, durch `\n` getrennt)
  - `CodeSet(system: Literal["icd10","atc","loinc"], prefixes: list[str] (min 1), label: str, source: Literal["explicit","lexicon","data_match","llm"])`
  - Kriterien mit Diskriminator `kind`: `AgeCriterion("age", min: int|None, max: int|None)`, `SexCriterion("sex", value: Literal["female","male"])`, `RegionCriterion("region", values: list[str])`, `DataHolderCriterion("data_holder", values: list[str])`, `ConditionCriterion("condition", codes, negate=False)`, `MedicationCriterion("medication", codes, active_only=True, negate=False)`, `ObservationCriterion("observation", codes, negate=False)`, `EncounterCriterion("encounter", types: list[Literal["inpatient","outpatient","emergency"]] = [], start_from: date|None, start_to: date|None, primary_icd10: CodeSet|None, negate=False)`; `Criterion = Annotated[Union[…], Field(discriminator="kind")]`
  - `AgeBand(label: str, min: int, max: int | None)`; `Dimension(kind: Literal["region","data_holder","sex","age_band"], bands: list[AgeBand] = [])`
  - `EncounterScope(types: list[...] = [], start_from: date|None, start_to: date|None, primary_icd10: CodeSet|None, data_holders: list[str] = [])`
  - Metriken mit Diskriminator `kind`: `CountMetric("count", name, label, where: list[Criterion] = [], display: bool = True)`, `PercentMetric("percent", name, label, numerator: str, denominator: str)`, `MeanMetric("mean", name, label, codes: CodeSet, method: Literal["latest"] = "latest")`
  - `QuerySpec(unit: Literal["patient","encounter"]="patient", population: list[Criterion]=[], encounter_scope: EncounterScope|None=None, group_by: list[Dimension]=[], metrics: list[Metric]=[], output: Literal["statistics","cohort_size"]="statistics", record_types: list[Literal["patients","conditions","medications","observations","encounters"]]=[], observation_codes: CodeSet|None=None)`; Methode `canonical_json() -> str` (sortierte Keys, kompakt)
  - Rohzellen: `RawCount(n: int)`, `RawPercent(num: int, den: int)`, `RawMean(total: Decimal, n: int)`; `RawRow(group: dict[str, str], cells: dict[str, RawCount|RawPercent|RawMean])`; `RawTable(dimensions: list[str], metrics: list[Metric], rows: list[RawRow])`
  - Entscheidung: `Evidence(source: Literal["rules","llm"], category: str, quote: str)`; `PurposeAssessment(prohibited: list[Evidence], permitted: list[Evidence], spe_justification: list[Evidence])`; `RuleStep(step: int, title: str, condition: str, status: Literal["matched","not_matched","not_evaluated"], evidence: list[Evidence])`; `Outcome = Literal["REJECT","APPROVE_STATISTICAL","APPROVE_SPE"]`; `Decision(outcome: Outcome, articles: list[str], headline: str, reasons: list[str], trace: list[RuleStep], warnings: list[str])`

- [ ] **Step 1: Failing tests:** `test_spec_rejects_percent_with_unknown_metric` (Percent auf nicht existierenden Namen → `ValidationError`), `test_spec_rejects_percent_on_mean` (Zähler ist MeanMetric → Fehler), `test_encounter_unit_requires_scope`, `test_statistics_output_requires_metric`, `test_age_band_dimension_requires_bands`, `test_mean_only_for_patient_unit`, `test_canonical_json_is_order_stable` (zwei gleich gebaute Specs → identischer String), `test_access_request_allows_extra_and_missing_optional_fields`, `test_criterion_discriminator_roundtrip` (dump → validate liefert gleiche Spec).
- [ ] **Step 2: Run** → FAIL. **Step 3:** Implementieren inkl. `model_validator`s. **Step 4:** Run → PASS.
- [ ] **Step 5: Commit** `feat: typed request, query spec, raw cell and decision models`.

### Task 3: Disclosure-Kontrolle (parallelisierbar mit 4 und 5)

**Files:** Create `src/ehds_desk/disclosure.py`, `tests/test_disclosure.py`

**Interfaces:**
- Consumes: `RawTable`, `RawCount|RawPercent|RawMean`, `CountMetric.display` (Task 2)
- Produces:
  - `SMALL = "<10"`, `SUPPRESSED = "suppressed"`, `class LeakError(Exception)`
  - `round_half_up(value: Decimal, places: int = 1) -> Decimal`
  - `disclose_cell(cell) -> int | float | str` (gerundete Werte als `float(Decimal)`)
  - `DisclosedRow(group: dict[str,str], values: dict[str, int|float|str])`; `SuppressionNote(group: dict[str,str], metric: str, reason: str)` (Grund generisch, z. B. `"numerator below 10"`, nie die Rohzahl); `DisclosedTable(dimensions, metrics: list[{name,label,kind}], rows: list[DisclosedRow], notes: list[SuppressionNote])`
  - `disclose_table(raw: RawTable) -> DisclosedTable` – nur Metriken mit `display=True` (Count) bzw. alle Percent/Mean; Postcondition: ruft `assert_no_leak`.
  - `assert_no_leak(obj: Any) -> None` – rekursiv über dict/list/Pydantic: `int` (nicht `bool`) `< 10` → `LeakError`; String mit `p-[0-9a-f]{8}` → `LeakError`.

- [ ] **Step 1: Failing tests (exakte Werte):**
  - `test_round_half_up`: `0.05→0.1`, `0.15→0.2`, `0.25→0.3`, `2.45→2.5`, `Decimal("37.037")→37.0`, `Decimal("-0.05")→-0.1`.
  - `test_counts`: `RawCount(0)→"<10"`, `RawCount(9)→"<10"`, `RawCount(10)→10`, `RawCount(3247)→3247`.
  - `test_percent`: `RawPercent(9,100)→"suppressed"`, `RawPercent(10,9)→"suppressed"`, `RawPercent(0,50)→"suppressed"`, `RawPercent(30,81)→37.0`, `RawPercent(10,10)→100.0`, `RawPercent(227,2740)→8.3`, `RawPercent(1,8)→"suppressed"`.
  - `test_mean`: `RawMean(Decimal("408.0"),15)→27.2`, `RawMean(Decimal("90.0"),9)→"suppressed"`, `RawMean(Decimal("0"),0)→"suppressed"`.
  - `test_table_keeps_every_group_and_hides_hidden_counts`: Tabelle mit 2 Gruppen (eine leer), Hidden-Count → Hidden-Metrik fehlt in `values`, leere Gruppe hat `"<10"`/`"suppressed"`, `notes` nennen keine Zahl < 10.
  - `test_assert_no_leak`: `{"a": {"x": 5}}` → LeakError; `["p-1234abcd"]` → LeakError; `{"x": 10, "y": "<10", "z": True, "w": 37.0}` → ok.
- [ ] **Step 2–4:** Run FAIL → implementieren → Run PASS.
- [ ] **Step 5: Commit** `feat: central small-cell disclosure control and leak guard`.

### Task 4: Gesetzeskatalog und Entscheidungsleiter (parallelisierbar mit 3 und 5)

**Files:** Create `src/ehds_desk/law.py`, `src/ehds_desk/decision.py`, `tests/test_decision.py`

**Interfaces:**
- Consumes: `AccessRequest`, `Evidence`, `PurposeAssessment`, `RuleStep`, `Decision` (Task 2)
- Produces:
  - `law.ARTICLES: dict[str, Article]` mit `Article(number: str, title: str, summary: str)` für `"53","54","66","67","68","69","71","73"` (Kurzfassungen englisch, aus `docs/LAW.md` übersetzt); `law.ART53_POINTS`, `law.ART54_POINTS: dict[str, str]` (Schlüssel `"53(1)(a)"…"53(1)(f)"`, `"54(a)"…"54(e)"` → Kurzbeschreibung englisch)
  - `decision.request_kind(request) -> Literal["statistics_request","access_application"]` – `requested_as` normalisiert (lowercase, trim); enthält „access application“ → access; „data request“ → statistics; sonst aus `requested_format` („record“/„pseudonym“ → access) mit Warnung.
  - `decision.assess_purpose(request, llm: PurposeAssessment | None = None) -> PurposeAssessment` – Regeln auf `purpose + question + definitions`; LLM-Evidenz nur übernehmen, wenn `quote` (whitespace-normalisiert, case-insensitive) wörtlich im Antrag steht.
  - `decision.decide(request, assessment) -> Decision`

Regelwerk (je Regel: `category`, `all_of` – alle Regexe müssen treffen, `none_of` – keiner darf treffen; Zitat = Satz, in dem der erste `all_of`-Treffer liegt; Flags `re.I`):

| Kategorie | all_of | none_of |
|---|---|---|
| `54(b)` Versicherung | `\binsur(ance|er)\b|\bpremium` · `premium|pricing|risk[- ]based|underwrit|exclu|tariff|contribution` | – |
| `54(b)` Kredit | `\b(credit|loan|mortgage)` · `scor|decision|approv|condition|terms|worth|eligib` | – |
| `54(b)` Beschäftigung | `\bemployees?\b|\bstaff list|\bHR\b|human resources|job (offer|applicant|candidate)` · `contract|hir(e|ing)|dismiss|recruit|select|promot|sick leave|absen` | – |
| `54(a)` Re-Identifizierung/Nachteil | `match\w* (the |our |these )?(records|data)?\s*with|re-?identif|identify (which|individual|specific) (patients|persons|people|employees|customers)|who has been diagnosed` | – |
| `54(c)` Werbung | `advertis|marketing|promotional|brand awareness|lead generation|sales (rep|representative|force|visit|campaign|target)|target\w* (our )?(ads|customers|prescribers|physicians)` | – |
| `54(d)` schädliche Produkte | `nicotine|tobacco|cigarette|\bvap(e|ing)\b|alcoholic|\bspirits\b|liquor|gambling|betting|weapon|firearm|illicit drug` · `product|flavou?r|brand|launch|position|sell|sales|consumer|portfolio` | `cessation|quit(ting)?\b|stop(ping)? smoking|withdrawal|replacement therapy|harms? (of|caused by)` |

Art.-53-Zwecke (nur Begründung): `(a)` `public health|prevention|surveillance|quality (programme|program|of care|in healthcare)|patient safety`; `(b)` `ministry|policy|policymaking|regulat|health authorit`; `(c)` `official statistic|statistics office|national statistic|health report`; `(d)` `teaching|education|curricul|training module`; `(e)` `research|stud(y|ies)|epidemiolog|(train|validat)\w* .{0,40}(model|algorithm)|predict`; `(f)` `improve (the )?(care|treatment|delivery)|treatment gap|optimi[sz]e treatment|intervene earlier`.

SPE-Begründung (nur bei Access-Antrag geprüft): `(aggregate[sd]?|statistics|anonymi[sz]ed (data|statistics))( data| statistics)? (are|is|would be) not (enough|sufficient)|cannot be (achieved|answered|done) with (anonymi[sz]ed|aggregate)|not possible with (anonymi[sz]ed|aggregate)|(need|needs|require|requires)\s+(individual|patient|record)[- ]level|(individual|patient|record)[- ]level (data|histories|records|trajectories) (are|is) (needed|required|necessary)`.

Leiter (Spec §3 „Entscheidung“): Artikel `REJECT → ["54"]`, Stufe 2 → `["53","69","71"]`, Stufe 3 → `["53","66","68","73","71"]`, Stufe 4 → `["53","66","69","71"]`. Trace hat immer 4 Schritte; Schritte nach dem Treffer `not_evaluated`. Ohne Art.-53-Treffer: Warnung `"No permitted purpose under Art. 53(1) recognised – manual check recommended."`. Begründungen (englisch, laienverständlich) nennen Zitat + Artikel; Stufe 4 erklärt Art. 66(2)/68(3): fehlende Darlegung, dass anonymisierte Statistik nicht reicht.

- [ ] **Step 1: Failing tests:**
  - `test_track3_requests_decide_as_expected` (parametrisiert über R01–R10 aus `settings.data_dir/requests`, gegen `expected.json`): Outcome gleich; `set(articles) - {"67","71"} == set(expected)`.
  - `test_r06_hits_employment_and_reidentification` (Kategorien `54(b)` und `54(a)`).
  - `test_smoking_cessation_research_is_not_prohibited`: Zweck „We evaluate a nicotine replacement therapy programme that helps patients with COPD quit smoking“ → kein `prohibited`.
  - `test_sales_rep_targeting_is_marketing`: „…to plan visits of our sales representatives to high-prescribing physicians“ → `54(c)`.
  - `test_credit_scoring_is_prohibited` → `54(b)`.
  - `test_access_without_justification_is_step4` und `test_access_with_justification_is_spe` (Mini-Requests).
  - `test_llm_evidence_requires_verbatim_quote`: LLM-Evidenz mit erfundenem Zitat wird verworfen, mit wörtlichem übernommen (Quelle `llm` im Trace).
  - `test_unknown_requested_as_falls_back_to_format` (+ Warnung).
  - `test_decision_is_deterministic`: `decide` zweimal → `model_dump()` gleich.
- [ ] **Step 2–4:** FAIL → implementieren → PASS.
- [ ] **Step 5: Commit** `feat: EHDS article catalogue and deterministic decision ladder`.

### Task 5: Terminologie (parallelisierbar mit 3 und 4)

**Files:** Create `src/ehds_desk/terminology.py`, `src/ehds_desk/terminology_lexicon.py`, `tests/test_terminology.py`

**Interfaces:**
- Consumes: `Database` (Task 1), `CodeSet` (Task 2)
- Produces:
  - `CodeMatch(code: str, description: str, rows: int)`; `TermMapping(term: str, codes: CodeSet, table: Literal["conditions","primary_icd10","medications","observations"], matches: list[CodeMatch], warning: str | None)`
  - `class Terminology: __init__(self, db: Database)`; `lookup(self, text: str, system: Literal["icd10","atc","loinc"] | None = None) -> CodeSet | None`; `verify(self, term: str, codes: CodeSet, table: …) -> TermMapping`; `catalogue(self) -> dict[str, list[tuple[str, str]]]` (Codes + Beschreibungen je System, für LLM-Prompt)
  - `terminology_lexicon.LEXICON: list[LexEntry]` mit `LexEntry(synonyms: tuple[str, ...], system, prefixes: tuple[str, ...], label: str)`

`lookup`: Text normalisieren (lowercase, Satzzeichen weg, „type ii“→„type 2“, Plural-s am Wortende entfernen) → längster Synonym-Treffer im Lexikon (Quelle `lexicon`) → sonst Token-Überlappung (Jaccard ≥ 0.5) mit Beschreibungen der Daten (Quelle `data_match`, Präfix = gefundener Code) → sonst `None`. Lexikon deckt mindestens ab: E11 type 2 diabetes, E10 type 1 diabetes, I10 hypertension/high blood pressure, I48 atrial fibrillation, I50 heart failure, I63 stroke/cerebral infarction, J44 COPD, J45 asthma, F32+F33 depression, C50 breast cancer, E66 obesity, N18 chronic kidney disease, J12–J18 pneumonia, S72 hip/femur fracture, K35 appendicitis, N39.0 urinary tract infection, I21 myocardial infarction; ATC: A10 antidiabetics, A10A insulin, A10BA02 metformin, A10BJ GLP-1, A10BK SGLT2, B01AA vitamin K antagonist, B01AF DOAC, B01AA+B01AF oral anticoagulant, C03C loop diuretic, C07 beta blocker, C08 calcium channel blocker, C09AA ACE inhibitor, C09CA ARB/angiotensin receptor blocker/sartan, C10AA statin, N06AB SSRI, N06A antidepressant, R03AK ICS/LABA inhaler, R03BB LAMA/tiotropium; LOINC: 4548-4 HbA1c, 39156-5 BMI, 8480-6 systolic blood pressure, 62238-1 eGFR/kidney function.

- [ ] **Step 1: Failing tests:** `test_lookup_lexicon` (parametrisiert: „type 2 diabetes“→icd10 `["E11"]`; „Type II diabetes mellitus“→`["E11"]`; „atrial fibrillation“→`["I48"]`; „breast cancer“→`["C50"]`; „hip fracture“→`["S72"]`; „oral anticoagulants“→atc `["B01AA","B01AF"]`; „ACE inhibitor“→`["C09AA"]`; „angiotensin receptor blockers“→`["C09CA"]`; „SGLT2 inhibitor“→`["A10BK"]`; „HbA1c“→loinc `["4548-4"]`; „body mass index“→`["39156-5"]`), `test_lookup_respects_system` („insulin“ mit `system="loinc"` → None), `test_lookup_data_match` („Salmeterol/fluticasone“ → atc `["R03AK06"]`, Quelle `data_match`), `test_lookup_unknown` („gout“ → None), `test_verify_reports_matches` (`E11` in conditions → Codes `E11.65`, `E11.9` mit rows 297/910), `test_verify_pneumonia_in_primary` (J12–J18 → nur `J18.9`, Tabelle `primary_icd10`), `test_verify_warns_without_matches` (`I21` → `matches == []`, `warning` gesetzt).
- [ ] **Step 2–4:** FAIL → implementieren → PASS.
- [ ] **Step 5: Commit** `feat: plain-text terminology mapping verified against codes in data`.

### Task 6: SQL-Compiler und Engine

**Files:** Create `src/ehds_desk/compiler.py`, `src/ehds_desk/engine.py`, `tests/specs.py` (handgebaute Specs als Test-Fixtures), `tests/test_engine.py`

**Interfaces:**
- Consumes: `Database`, `REGIONS`, `SEXES` (Task 1); `QuerySpec`, Raw-Typen (Task 2); `disclose_table` (Task 3, nur in Tests)
- Produces:
  - `@dataclass(frozen=True) class CompiledQuery: sql: str; params: list[Any]; dimensions: list[str]`
  - `compiler.compile_statistics(spec, *, data_holders: tuple[str, ...], scope: Literal["consented","all"] = "consented") -> CompiledQuery`
  - `compiler.compile_cohort(spec, *, scope="consented") -> CompiledQuery` (Spalte `patient_id`, DISTINCT, sortiert)
  - `engine.run_statistics(spec, db) -> tuple[RawTable, CompiledQuery]`
  - `engine.cohort_patient_ids(spec, db, scope="consented") -> list[str]`
  - `engine.opt_out_exclusions(spec, db) -> int` (Patienten der Population in `_all` minus `consented`)

SQL-Muster (für `scope="all"` Viewnamen mit `_all`):
```
WITH units AS (            -- patient: FROM pat p WHERE <population>;  encounter: FROM enc e JOIN pat p USING (patient_id) WHERE <scope> AND <population>
  SELECT p.patient_id, <dim-Ausdrücke> ...),
latest_<i> AS (SELECT patient_id, arg_max(value, date) AS v FROM obs WHERE <loinc-Präfixe> GROUP BY patient_id),
agg AS (SELECT <dims>, count(*) FILTER (WHERE <where_k>) AS c_k, sum(l_i.v) AS s_i, count(l_i.v) AS n_i
        FROM units LEFT JOIN latest_i l_i USING (patient_id) GROUP BY <dims>),
domain AS (<kartesisches Produkt der Domänen mit Ordnungsspalte>)
SELECT domain.*, coalesce(c_k, 0), coalesce(s_i, 0), coalesce(n_i, 0) FROM domain LEFT JOIN agg USING (<dims>) ORDER BY ord
```
Kriterien → `EXISTS (…)`-Subqueries mit `starts_with(code, ?)`; `negate` → `NOT EXISTS`. Altersband-Dimension = `CASE`-Ausdruck; Einheiten ohne Band fallen weg. Domänen: region → `REGIONS`, data_holder → `data_holders` (bei unit=encounter Klinikum des Aufenthalts, sonst `pat.data_holder`), sex → `SEXES`, age_band → Bandlabels in Antragsreihenfolge. Percent-Zellen berechnet die Engine aus den Counts (`RawPercent(num=c_numerator, den=c_denominator)`), Mean aus `s_i`/`n_i` als `Decimal`.

- [ ] **Step 1: Failing tests** (Specs in `tests/specs.py` handgebaut nach den Anträgen; Zahlen = `expected.json`):
  - `test_r01_raw_counts`: Burgenland `adults=RawCount(532)`, `type2=RawCount(33)`; Wien 3247/263; Prozent nach `disclose_table` 8.1.
  - `test_r03_age_bands_and_negated_active_med`: 65-74 → 81/30/37.0; 85+ → 78/22/28.2.
  - `test_r07_counts_encounters_not_patients`: Wien 245, Burgenland 28.
  - `test_r08_latest_bmi_mean`: Niederösterreich 15 / 27.2; Burgenland `"<10"`/`"suppressed"` nach Disclosure.
  - `test_r09_percent_of_active_meds`: 18-49 → 359 / 39.6 / 33.4.
  - `test_r05_cohort`: `len(cohort_patient_ids) == 1152`; `opt_out_exclusions == 55`.
  - `test_empty_groups_are_present`: COPD × Region × Band (10 Bänder) → 90 Zeilen, Band `0-9` überall `RawCount(0)`.
  - `test_group_by_data_holder`: Patienten mit I50 nach `data_holder` → genau 3 Zeilen mit den 3 Klinika.
  - `test_primary_icd10_encounter_filter`: unit=encounter, inpatient, primary S72 → Summe > 0 und = Anzahl inpatient-Encounters mit `primary_icd10 LIKE 'S72%'` in `enc`.
  - `test_sql_uses_parameters`: kein Code-String (z. B. `"E11"`) im `sql`-Text, nur in `params`.
- [ ] **Step 2–4:** FAIL → implementieren → PASS.
- [ ] **Step 5: Commit** `feat: QuerySpec to DuckDB SQL compiler and execution engine`.

### Task 7: Regelparser

**Files:** Create `src/ehds_desk/parsing/__init__.py` (vorerst nur Re-Export), `src/ehds_desk/parsing/rules.py`, `tests/test_parsing_rules.py`

**Interfaces:**
- Consumes: `AccessRequest`, `QuerySpec` & Co. (Task 2), `Terminology` (Task 5)
- Produces:
  - `ParseReport(understood: list[str], not_understood: list[str], notes: list[str], mappings: list[TermMapping])`; Property `complete: bool` (= `not not_understood`)
  - `rules.parse_rules(request: AccessRequest, terminology: Terminology) -> tuple[QuerySpec | None, ParseReport]`

Algorithmus (die Tests legen ihn nicht fest, daher hier verbindlich):
1. Normalisieren: Unicode-Anführungszeichen → `'`, `×`→`x`, Gedankenstriche → `-`, Mehrfach-Leerzeichen zusammenfassen. Definitionen an `;` splitten, wenn jeder Teil ein `=` enthält.
2. Satzklassen in dieser Reihenfolge (erste passende gewinnt; jeder Satz landet in `understood` oder `not_understood`):
   - **Begriffsdefinition** `^(?P<term>[^=]{1,80}?)\s*=\s*(?P<body>.+)$`. Body-Analysatoren: Alter (`aged (\d+) or older`, `(\d+) years or older`, `aged (under|below|younger than) (\d+)`), Geschlecht (`sex '?(female|male)'?`, `women|female` → female), ICD-10 explizit (`ICD-10 code[s]? (starting|beginning) with` + Codes `[A-Z]\d{2}(?:\.\d+)?`; mit `main diagnosis|primary diagnosis|primary_icd10` → Encounter-Primärdiagnose), ATC explizit (`ATC code[s]? (starting|beginning) with` + `[A-Z]\d{2}[A-Z]{0,2}\d{0,2}`), LOINC (`LOINC ([\d]+-\d)`), Aufenthalt (`encounter with type '?(inpatient|outpatient|emergency)'?`), Prozentformel (`(.+?) / (.+?) x 100`), Kohorte (Term `cohort` oder Body verweist auf definierte Begriffe → Nominalphrase, Schritt 3), sonst Klartext → `terminology.lookup(term)` dann `lookup(body)`; System-Hinweis aus Body (`prescription|medication|drug` → atc, `measurement|value|test|level` → loinc, `stay|admission|main diagnosis` → primary). Ergebnis: `Term(name_lower, kind, criterion | percent_def | cohort_criteria)` plus `TermMapping` via `verify`.
   - **Altersbänder** `age (bands?|groups?)[^:]*:\s*(.+)$` → Bänder aus `(\d+)\s*-\s*(\d+)`, `(\d+)\+`, `(\d+) (and|or) (older|over)`, `(under|<)\s*(\d+)` (Label wie im Text).
   - **Aktiv-Regel** `medication is active` → verstanden; weicht das Datum von 31 December 2025 ab → Note.
   - **Letzter Messwert** `use the latest (.+?) (\(LOINC [\d-]+\) )?per patient` → Messbegriff Methode latest; Zusatz `patients without (a|an )?.+ are (left out|excluded)` → Population `ObservationCriterion`.
   - **Encounter-Zählung** `count (stays|encounters|visits|admissions)` → unit encounter; Datum `in (\d{4})` → `start_from=YYYY-01-01`, `start_to=YYYY-12-31`; `between (\d{4}-\d{2}-\d{2}) and (\d{4}-\d{2}-\d{2})`.
   - **Report-Satz** `^report (per|by|for each) (?P<dims>[^:]+):\s*(?P<items>.+)$` → Dimensionen (Split an ` and `, `,`, ` x `): `region|federal state|state` → region; `hospital|data holder|data_holder|clinic|site` → data_holder; `sex|gender` → sex; `age band|band|age group` → age_band; `patient` → Note „patient-level listing is not available as statistics“ und Satz in `not_understood`. Items: Split an `, ` und ` and ` außerhalb von Klammern.
   - **Kohortengröße** `report the size of the cohort|cohort size` → `output="cohort_size"`.
   - Fallback-Gruppierung aus `question`, wenn kein Report-Satz: `by|in each|per` + Dimensionswort.
3. **Nominalphrase → Kriterien** (`_phrase_criteria(text, terms)`): Subjekt `adults`→Alter des Begriffs „adult“ (sonst ≥ 18), `women|female`→female, `men|male`→male, `children`→max 17, `stays|encounters` → Encounter-Einheit. Danach alle definierten Begriffsnamen im Text (längste zuerst); `no|without|not on` bis 3 Wörter davor → `negate=True`; Medikamente `active_only=True`, wenn eine Aktiv-Regel existiert oder „active“ davor steht. `with a|an <Messung>( value)?` oder `who have (a|an|at least one) <Messung>` → `ObservationCriterion`. Unbekannte `with <X>`-Phrasen → `terminology.lookup(X)`; scheitert das → Satz in `not_understood`.
4. **Metriken:** Item mit `%|share|percent|prevalence|proportion|rate` → Percent; mit `mean|average` → Mean (Messbegriff im Item); sonst Count (`number of`, `how many of them` entfernen). Basis = Kriterien der ersten Count-Metrik. Weitere Counts: `where` = eigene Kriterien minus Basis. „that share in %“ → Prozent(letzter Count / Basis). „% with X“ → versteckter Count (`display=False`) + Prozent / Basis. Prozentbegriff aus Definition („Prevalence = A / B x 100“) → Zähler/Nenner per Phrasenvergleich auf vorhandene Counts. Metrik-Namen deterministisch `snake_case(label)`, bei Kollision `_2`.
5. **Population** = Basis ∪ in keiner Metrik genutzte Diagnose-Begriffe ∪ „left out“-Messkriterium; bei `cohort_size` = Kriterien des Begriffs `cohort` (sonst Basis). Encounter-Begriffe → `EncounterScope` (Typen, Primärdiagnose) plus Datumsbereich.
6. **Record-Typen** (nur relevant für Access-Anträge; aus `question` + `purpose`): `conditions|diagnos` → conditions; `medication|prescription|drug` → medications; `observation|measurement|lab|<Messbegriff> values?` → observations (+ `observation_codes`, wenn bestimmte Messbegriffe genannt); `encounter|visit|stay|admission` → encounters; `demographic|birth|patient data` → patients. Ausgabe immer in der festen Reihenfolge `patients, conditions, medications, observations, encounters`.

- [ ] **Step 1: Failing tests:**
  - `test_track3_requests_parse_completely` (R01, R02, R03, R04, R05, R07, R08, R09, R10): `report.complete`.
  - `test_parsed_numbers_match_expected` (R01, R03, R07, R08, R09): `parse_rules` → `run_statistics` → `disclose_table` → für jede erwartete Gruppe sind alle erwarteten Werte in den `values` der Gruppe enthalten (R07: Skalar).
  - `test_r05_cohort_and_record_types`: `output == "cohort_size"`, `len(cohort_patient_ids) == 1152`, `record_types == ["conditions","medications","observations"]`, `observation_codes.prefixes == ["4548-4"]`.
  - `test_r08_unused_condition_joins_population` (C50 in Population).
  - `test_r06_patient_listing_not_understood`.
  - `test_group_by_synonyms` (parametrisiert: „Report per hospital: patients with heart failure.“, „Report by data holder: …“, „Report per sex and age band: …“, „Report for each hospital and age band: …“ → erwartete Dimensionen).
  - `test_primary_icd10_definition`: Definition „Pneumonia stay = inpatient encounter whose main diagnosis (primary_icd10) starts with J18.“ + „Count stays (not patients) whose start_date is in 2024.“ + „Report per hospital: pneumonia stays.“ → unit encounter, `primary_icd10.prefixes == ["J18"]`, Dimension data_holder.
  - `test_plain_text_without_codes`: „Asthma = a diagnosis of asthma.“, „Inhaler = an active prescription of salmeterol/fluticasone.“, „Report per region: patients with asthma, % with an active inhaler.“ → Codes `J45` (lexicon) und `R03AK06`, vollständig.
  - `test_unknown_term_is_not_understood`: „Gout = any diagnosis of gout.“ in Report → `not report.complete`.
- [ ] **Step 2–4:** FAIL → implementieren → PASS.
- [ ] **Step 5: Commit** `feat: deterministic rule parser from plain-English definitions to QuerySpec`.

### Task 8: SPE-Bereitstellung mit Download-Sperre

**Files:** Create `src/ehds_desk/spe.py`, `tests/test_spe.py`

**Interfaces:**
- Consumes: `Database` (1), `AccessRequest`, `QuerySpec` (2), `cohort_patient_ids` (6)
- Produces:
  - `SpeManifest(permit_id: str, request_id: str, patient_count: int, tables: dict[str, int], record_types: list[str], observation_codes: list[str], articles: list[str])` (keine Zeitstempel → reproduzierbar)
  - `AuditEvent(timestamp: str, permit_id: str, actor: str, action: Literal["provisioned","preview","download_blocked"], table: str | None, detail: str)`
  - `permit_id_for(request: AccessRequest) -> str` = `f"{request.id}-{sha256(request.model_dump_json(sort_keys)).hexdigest()[:8]}"`, nur `[A-Za-z0-9_-]`
  - `provision_spe(request, spec, db, var_dir: Path) -> SpeManifest` – legt `var/spe/<permit_id>/spe.duckdb` neu an (vorher löschen, falls vorhanden), Tabelle `cohort(patient_id)` + nur `spec.record_types`, gefiltert auf Kohorte; `observations` zusätzlich auf `observation_codes`; schreibt `manifest.json`, hängt Audit-Event an.
  - `load_manifest(permit_id, var_dir) -> SpeManifest`; `preview(permit_id, table, var_dir, limit=20) -> list[dict]` (read-only Verbindung, loggt `preview`); `attempt_download(permit_id, table, var_dir, actor="applicant") -> AuditEvent` (loggt `download_blocked`, gibt das Event zurück, liefert nie Daten); `audit_log(permit_id, var_dir) -> list[AuditEvent]`
  - `class SpeNotFound(Exception)`, `class InvalidPermitId(ValueError)`

- [ ] **Step 1: Failing tests** (R05-Spec aus `tests/specs.py`, `var_dir = tmp_path`):
  - `test_r05_spe_contents`: `patient_count == 1152`; `set(tables) == {"cohort","conditions","medications","observations"}`; kein `encounters`/`patients`; alle `observations.loinc == "4548-4"`; alle `patient_id` der Tabellen ⊆ Kohorte.
  - `test_spe_contains_no_opted_out_patients` (Abgleich gegen `raw_patients.opted_out`).
  - `test_encounters_record_type_copies_encounters` (Spec mit `record_types=["encounters"]`).
  - `test_download_is_blocked_and_audited`: `attempt_download` → `action == "download_blocked"`; `audit_log` enthält `provisioned` und `download_blocked`.
  - `test_invalid_permit_id_rejected` (`"../x"` → `InvalidPermitId`), `test_unknown_table_rejected`.
  - `test_provision_twice_is_idempotent` (zweimal → gleiches Manifest, kein Fehler).
- [ ] **Step 2–4:** FAIL → implementieren (ATTACH/DETACH über eigenen Cursor; Datei vor Neuanlage löschen) → PASS.
- [ ] **Step 5: Commit** `feat: secure processing environment provisioning with blocked downloads and audit log`.

### Task 9: Pipeline und CLI

**Files:** Create `src/ehds_desk/pipeline.py`, `src/ehds_desk/__main__.py`, `tests/test_pipeline.py`; Modify `src/ehds_desk/parsing/__init__.py`

**Interfaces:**
- Consumes: alles aus Tasks 1–8
- Produces:
  - `parsing.ParseResult(spec: QuerySpec | None, report: ParseReport, source: Literal["rules","llm","llm_cache","none"], llm_purpose: PurposeAssessment | None)`; `parsing.parse_request(request, terminology, settings) -> ParseResult` (vorerst nur Regeln; Task 10 hängt LLM an)
  - `SpeAnswer(permit_id, patient_count, tables: dict[str,int], workspace_url: str)` (`/spe/<permit_id>`)
  - `ApplicantView(request_id, decision: Outcome, articles: list[str], article_titles: dict[str,str], headline: str, reasons: list[str], statistics: DisclosedTable | None, spe: SpeAnswer | None, notes: list[str])`
  - `StaffView(trace: list[RuleStep], purpose: PurposeAssessment, request_kind: str, spec: QuerySpec | None, spec_summary: list[str], parse_report: ParseReport, parser_source: str, sql: str | None, opt_out_excluded: int | str | None, disclosure_notes: list[SuppressionNote], timings_ms: dict[str, int], warnings: list[str])`
  - `ProcessResult(applicant: ApplicantView, staff: StaffView)`
  - `class DeskService: __init__(self, settings: Settings | None = None)`; `process(self, request: AccessRequest) -> ProcessResult`; `list_requests(self) -> list[dict]` (R01–R10 aus `data_dir/requests` + `requests/extra/*.json` im Repo, Felder `id, source, organisation, purpose, requested_as`); `get_request(self, request_id: str) -> AccessRequest`
  - CLI: `python -m ehds_desk decide <file.json> [--staff]` (gibt JSON aus), `python -m ehds_desk serve [--host 127.0.0.1] [--port 8000]`

Ablauf `process`: parse → assess_purpose (inkl. `llm_purpose`) → decide → bei REJECT keine Berechnung; bei Statistik: Spec vollständig? ja → `run_statistics` → `disclose_table`; nein → `statistics=None`, Note „Part of this request could not be interpreted automatically and was referred to staff for manual review.“ und Staff-Warnung; bei SPE: `provision_spe`. `opt_out_excluded` durch `disclose_cell(RawCount(n))` (also ggf. `"<10"`). `spec_summary` = lesbare Sätze („Population: age ≥ 18 AND condition ICD-10 E11*“). `assert_no_leak(result.applicant.statistics)` und Patienten-ID-Prüfung über das ganze Ergebnis vor Rückgabe.

- [ ] **Step 1: Failing tests:** `test_process_all_track3_requests` (Outcome je expected; REJECT → `statistics is None and spe is None`; R05 → `spe.patient_count == 1152`), `test_process_is_reproducible` (3× R01 und R05 → `applicant.model_dump_json()` identisch), `test_no_patient_ids_in_result` (Regex über `ProcessResult.model_dump_json()` für alle 10), `test_staff_view_contents` (R03: `sql` gesetzt, `parse_report.mappings` nicht leer, `opt_out_excluded` gesetzt, Trace 4 Schritte), `test_unmappable_term_needs_review` (Mini-Antrag mit „Gout“ → `statistics is None`, Note und Warnung vorhanden, Outcome trotzdem APPROVE_STATISTICAL), `test_cli_decide` (`subprocess` mit R01 → Exit 0, JSON enthält `"APPROVE_STATISTICAL"`).
- [ ] **Step 2–4:** FAIL → implementieren → PASS.
- [ ] **Step 5: Commit** `feat: end-to-end processing pipeline and CLI`.

### Task 10: Optionaler LLM-Pfad (Claude)

**Files:** Create `src/ehds_desk/parsing/llm.py`, `tests/test_parsing_llm.py`; Modify `src/ehds_desk/parsing/__init__.py`

**Vorab:** Skill `claude-api` lesen (Modell-ID, Tool-Use/Structured Output, ob `temperature` unterstützt wird). Default-Modell aus `EHDS_LLM_MODEL`, sonst das im Skill empfohlene aktuelle Modell.

**Interfaces:**
- Consumes: `AccessRequest`, `QuerySpec`, `PurposeAssessment` (2), `Terminology.catalogue()` (5), `Settings` (1), `ParseResult` (9)
- Produces:
  - `class LLMUnavailable(Exception)`, `class LLMError(Exception)`
  - `llm.build_payload(request, catalogue) -> dict` (nur Antragsfelder + Code-Katalog)
  - `llm.parse_with_llm(request, terminology, settings, *, client: Any | None = None) -> tuple[QuerySpec, PurposeAssessment, bool]` (bool = aus Cache); Cache `var/cache/llm/<sha256(canonical request + PROMPT_VERSION + model)>.json`
  - `parse_request`: Regeln zuerst; nur wenn `not report.complete` **und** `llm_mode == "auto"` **und** Key vorhanden → LLM; LLM-Spec wird mit `Terminology.verify` geprüft (Codes ohne Treffer → Warnung); bei `LLMError`/Timeout (30 s) Regelergebnis + Staff-Hinweis.

- [ ] **Step 1: Failing tests** (Fake-Client, kein Netz): `test_payload_contains_no_patient_rows` (kein `p-[0-9a-f]{8}`, keine CSV-Zeilen; nur Schlüssel `request`, `catalogue`, `schema`), `test_valid_tool_output_becomes_spec`, `test_invalid_output_retries_once_then_raises`, `test_cache_hit_skips_client`, `test_quotes_not_in_request_are_dropped`, `test_parse_request_uses_rules_when_complete` (Client wird nicht aufgerufen), `test_parse_request_without_key_reports_needs_review`.
- [ ] **Step 2–4:** FAIL → implementieren → PASS.
- [ ] **Step 5: Commit** `feat: optional Claude translation of request text into validated QuerySpec`.

### Task 11: HTTP-API

**Files:** Create `src/ehds_desk/api.py`, `tests/test_api.py`

**Interfaces:**
- Consumes: `DeskService` (9), `spe`-Funktionen (8), `law.ARTICLES` (4)
- Produces: `api.create_app(service: DeskService | None = None) -> FastAPI` mit
  - `GET /api/health` → `{"status":"ok","patients":19161,"llm":"off|available"}`
  - `GET /api/requests` · `GET /api/requests/{id}` · `POST /api/process` (Body `AccessRequest`) · `POST /api/process/{id}` → `ProcessResult`
  - `GET /api/law` → Artikelkatalog
  - `GET /api/spe/{permit_id}` (Manifest) · `GET /api/spe/{permit_id}/preview/{table}` · `GET /api/spe/{permit_id}/audit`
  - `GET /api/spe/{permit_id}/download/{table}` → **403** `{"blocked": true, "article": "73", "reason": "Downloads of pseudonymised records are blocked. Only anonymised results reviewed by the access body may leave the secure processing environment (Art. 73(2))."}`
  - statische Dateien aus `web/` unter `/` (Task 12), `/spe/{permit_id}` liefert `web/index.html` (Client-Routing)
  - Fehler: unbekannte Request-ID/SPE → 404; Validierungsfehler → 422; `LeakError` → 500 mit generischer Meldung

- [ ] **Step 1: Failing tests:** `test_health`, `test_list_requests_has_track3_ids`, `test_process_by_id_r01`, `test_process_minimal_request` (ohne `submitted`/`requested_format`/`country`, mit Zusatzfeld → 200), `test_process_invalid_json_is_422`, `test_process_r05_unicode` (`Hadžić` bleibt erhalten), `test_spe_download_blocked_403_and_audited`, `test_spe_unknown_404`, `test_spe_path_traversal_rejected` (`/api/spe/..%2Fx/download/cohort` → 400 oder 404).
- [ ] **Step 2–4:** FAIL → implementieren → PASS.
- [ ] **Step 5: Commit** `feat: FastAPI endpoints for processing, law catalogue and SPE workspace`.

### Task 12: Web-UI

**Files:** Create `web/index.html`, `web/app.js`, `web/styles.css`; Test: `tests/test_web.py` (Smoke: `/` liefert HTML mit `id="app"`, `/app.js` und `/styles.css` 200, `/spe/<id>` liefert HTML)

**Inhalt (Spec §3 „UI“):** Kopfzeile „EHDS Access Desk · Health Data Access Body (demo on synthetic data)“. Links Eingang (R01–R10, eigene Anträge, „New request“ mit JSON-Textfeld). Rechts Tabs **Applicant** / **Staff**:
- Applicant: Banner je Outcome (Farbe + Icon + Text: „Rejected“, „Approved – anonymised statistics“, „Approved – secure processing environment“), Headline, Begründungsliste, Artikel-Chips mit Tooltip (`/api/law`), Ergebnistabelle (alle Gruppen; `<10`/`suppressed` grau kursiv mit Fußnote zur Small-Cell-Regel), bei SPE Karte mit Patientenzahl, Tabellen, Button „Open secure workspace“.
- Staff: Entscheidungsleiter (4 Schritte mit Status-Badges und Belegzitaten, Quelle rules/llm), Zweck-Treffer, Spec-Zusammenfassung + aufklappbares JSON, Terminologie-Tabelle (Begriff, System, Präfixe, Quelle, gefundene Codes mit Beschreibung/Zeilen, Warnung), SQL (Monospace, aufklappbar), Opt-out-Ausschlüsse, Unterdrückungsprotokoll, Parser-Quelle, Laufzeiten.
- SPE-Arbeitsbereich (`/spe/<permit_id>`): Permit-Kopf, Tabellen mit Zeilenzahl, Vorschau, je Tabelle „Download“ → rotes Banner mit 403-Grund, Audit-Log neu laden.
- Barrierearm: semantische Tabellen, Kontrast AA, Status nicht nur per Farbe; responsiv ab 375 px.

- [ ] **Step 1:** Smoke-Tests schreiben → FAIL. **Step 2:** UI bauen → Tests PASS.
- [ ] **Step 3:** Mit Skill `run` App starten, im Browser R01, R05 (inkl. blockiertem Download), R06, R09 durchklicken; Screenshot nach `docs/img/` (für README).
- [ ] **Step 4: Commit** `feat: applicant, staff and secure workspace web UI`.

### Task 13: Referenzskript und Eval

**Files:** Create `eval/reference.py`, `eval/run_eval.py`, `eval/results.md` (generiert), `tests/test_eval_helpers.py`

**Interfaces:**
- Consumes: `api.create_app` (11) über `fastapi.testclient.TestClient`; `engine.run_statistics` nur für die Leak-Gegenprobe
- Produces:
  - `eval/reference.py`: nur Standardbibliothek (`csv`, `decimal`), eigene Funktionen `r01() r03() r05() r07() r08() r09()` → Dicts im Format von `expected.json`; `python eval/reference.py` druckt Vergleichstabelle und endet mit Exit 1 bei Abweichung. Zusätzlich Funktionen für die eigenen Anträge (Task 14).
  - `eval/run_eval.py`: `match_numbers(expected_answer, applicant) -> bool` (Gruppe = Zeile, deren Gruppenwerte mit ` / ` verbunden dem erwarteten Schlüssel entsprechen bzw. bei einer Dimension gleich sind; alle erwarteten Werte müssen in den `values` vorkommen; Zahlen mit Toleranz 1e-9; R05: `cohort_size == spe.patient_count`), `find_leaks(result, raw) -> list[str]` (Int < 10 in `applicant.statistics`; Patienten-ID irgendwo; freigegebene Prozent-/Mittelwerte, deren Rohzähler/-nenner/n < 10 ist – Rohwerte über `engine.run_statistics(staff.spec)`), Konsistenz = `applicant`-JSON über 3 Läufe identisch, Zeit = Wanduhr pro Antrag.
  - Ausgabe `eval/results.md`: Metriktabelle (Metrik, Ergebnis, Ziel, ✅/❌), Tabelle je Antrag (Entscheidung erwartet/ist, Artikel, Zahlen ok, Leaks, konsistent, Zeit ms), Abschnitt eigene Anträge, Datum, Git-Commit, LLM-Modus. Exit 1, wenn ein Ziel verfehlt wird.

- [ ] **Step 1: Failing tests** für `match_numbers` (R07-Skalar, R01-Dict, `"<10"`-String, fehlende Gruppe → False) und `find_leaks` (synthetisches Ergebnis mit 7 → Leak; mit `"<10"` → keiner).
- [ ] **Step 2–4:** FAIL → implementieren → PASS.
- [ ] **Step 5:** `.venv/Scripts/python eval/reference.py` → alle 6 übereinstimmend; `.venv/Scripts/python eval/run_eval.py` → 10/10, 6/6, 0, 10/10, < 60 s. Bei jeder Abweichung: `superpowers:systematic-debugging`.
- [ ] **Step 6: Commit** `feat: independent reference computations and evaluation harness`.

### Task 14: Eigene Anträge

**Files:** Create `requests/extra/N01.json` … `N10.json`, `requests/extra/expected.json`; Modify `eval/reference.py` (Referenzfunktionen n01…), `eval/run_eval.py` (Extra-Abschnitt)

Anträge (Format wie R*.json, englisch, ohne Codes wo verlangt):
- N01 `primary_icd10`: stationäre Aufenthalte 2024–2025 mit Hauptdiagnose Pneumonie (J18), je Klinikum → `APPROVE_STATISTICAL` 53, 69.
- N02 `data_holder`: Patienten mit Herzinsuffizienz und mittlerer letzter eGFR je Klinikum → `APPROVE_STATISTICAL`.
- N03 Klartext ohne Codes: Asthma-Patienten nach Region, Anteil mit aktiver Salmeterol/Fluticason-Therapie → `APPROVE_STATISTICAL`.
- N04 Grenzfall-Verbot: Pharma-Außendienst will Arztbesuche nach Verordnungsdichte planen (ohne Wort „marketing“) → `REJECT` 54.
- N05 Grenzfall-erlaubt: Universität evaluiert Nikotinersatz-Entwöhnung bei COPD → `APPROVE_STATISTICAL`.
- N06 SPE mit Encounters: Modell zur Wiederaufnahme-Vorhersage bei Herzinsuffizienz, braucht Aufenthaltsverläufe auf Patientenebene → `APPROVE_SPE` 53, 66, 68, 73, Record-Typ `encounters`.
- N07 viele kleine Zellen: Schlaganfall nach Region × Geschlecht × Altersband → `APPROVE_STATISTICAL`, überwiegend `<10`.
- N08 Access ohne Begründung: Lehrprojekt will Datensätze zu CKD und eGFR → `APPROVE_STATISTICAL` 53, 66, 69.
- N09 Kredit/Versicherung in neuer Formulierung (Bank, Kreditkonditionen) → `REJECT` 54.
- N10 Hüftfraktur-Aufenthalte (Hauptdiagnose im Klartext „hip fracture“) nach Geschlecht und Altersband → `APPROVE_STATISTICAL`.

- [ ] **Step 1:** Anträge + erwartete Entscheidungen schreiben; Zahlen per neuen Referenzfunktionen erzeugen und in `expected.json` übernehmen.
- [ ] **Step 2:** `run_eval.py` → Extra-Abschnitt alle korrekt; Fehler mit `systematic-debugging` beheben (Parser/Lexikon erweitern, nie pro Antrag hart kodieren).
- [ ] **Step 3: Commit** `test: add ten new requests covering jury edge cases`.

### Task 15: README, Doku-Abschluss, Sicherheitsprüfung

**Files:** Create/Modify `README.md` (englisch), `docs/STATUS.md`, `docs/TODO.md`, `docs/WORKLOG.md`, `CLAUDE.md`

- [ ] **Step 1:** README: Ziel, Screenshot, Setup/Start (Windows + Unix), Demo-Ablauf inkl. blockiertem Download, Architektur mit Mermaid (Komponenten + Datenfluss + optional Claude), Modelle/Services, Datenschutzkonzept (Opt-out-Views, Small-Cell zentral, Leak-Guard, nur Antragstext an LLM, SPE + Audit), Metriktabelle aus `eval/results.md`, bekannte Grenzen (Spec §7).
- [ ] **Step 2:** Volle Testsuite + Eval laufen lassen; Ausgaben in STATUS übernehmen.
- [ ] **Step 3:** Skill `security-review` ausführen; Befunde beheben.
- [ ] **Step 4: Commit** `docs: README with architecture, privacy concept and metrics`.
- [ ] **Step 5:** `superpowers:verification-before-completion`, dann `superpowers:finishing-a-development-branch` (kein Push ohne Freigabe).

---

## Reihenfolge und Parallelisierung

`1 → 2 → {3, 4, 5 parallel} → 6 → 7 → 8 → 9 → {10, 11} → 12 → 13 → 14 → 15`.
Parallele Tasks berühren disjunkte Dateien; der Controller committet sie nacheinander. Nach den Meilensteinen
M1 (Tasks 1–5), M2 (6–9), M3 (10–12), M4 (13–15) jeweils `superpowers:requesting-code-review`.
