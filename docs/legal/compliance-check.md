# Compliance check: Regulation (EU) 2025/327 (EHDS), Chapter IV

Checked on 29 October 2026 against the official text in English and German (Official Journal L, 5.3.2025, CELEX 32025R0327, retrieved from the EU Publications Office). Text in quotation marks is copied verbatim from the Regulation. Everything else is a paraphrase or describes AccessDesk. The UI and the decision letter use paraphrases, and every sentence names its article.

Source: © European Union, https://eur-lex.europa.eu/eli/reg/2025/327/oj. Reuse is authorised provided the source is acknowledged (Commission Decision 2011/833/EU).

## Articles used in decisions

| Art. | Official title (EN / DE) | Key provision (verbatim) | How AccessDesk applies it |
|---|---|---|---|
| 53 | Purposes for which electronic health data can be processed for secondary use / Zwecke, für die elektronische Gesundheitsdaten zur Sekundärnutzung verarbeitet werden können | (1) access only where processing "is necessary for one of the following purposes", points (a) to (f) | `safes/projects.py` looks for the allowed purposes and keeps the matching phrases as evidence. The decision letter names the matching point of para. 1. |
| 54 | Prohibited secondary use / Unerlaubte Sekundärnutzung | prohibited: "(a) taking decisions detrimental to a natural person …", "(b) … job offers, … insurance or credit contract, … premiums or conditions of loans …", "(c) carrying out advertising or marketing activities", "(d) developing products or services that may harm individuals … such as … alcoholic beverages, tobacco and nicotine products, weaponry …" | Step 1 of the fixed decision order. Rules with evidence cover the categories insurance/credit, employment, marketing, harmful products and detrimental decisions. A match leads to `REJECT [54]` before any query runs. |
| 66 | Data minimisation and purpose limitation / Datenminimierung und Zweckbindung | (2) "provide electronic health data in an anonymised format, where the purpose of processing … can be achieved with such data"; (3) pseudonymised access where the user "has sufficiently demonstrated that the purpose of processing cannot be achieved with anonymised data" | Steps 3 and 4. An access application whose text explains why statistics are not enough leads to SPE; any other application is answered with statistics. The SPE receives only the cohort and the record types the request names (para. 1). |
| 67 | Health data access applications / Anträge auf Zugang zu Gesundheitsdaten | content of an application, incl. identity and professional function of the applicant | Identity checks in `safes/people.py` (signed credentials, simulated). Art. 67 may be cited in addition (allowed by the brief). |
| 68 | Data permit / Datengenehmigung | (3) "grant access … by issuing a data permit"; second subparagraph: the body may instead provide an anonymised statistical response "on condition that … the health data applicant agrees"; (10) contents of a permit (a) to (h); (12) "duration shall not exceed 10 years", data deleted "within six months of the expiry" | `APPROVE_SPE` issues a permit. The permit annex lists (a) data categories and format, (b) purpose, (d) authorised persons, (e) duration, (f) tools, (g) fees. Statistics instead of records (R09) cite the second subparagraph of para. 3 in the reasons. |
| 69 | Health data request / Gesundheitsdatenanfrage | (1) "obtaining a response only in an anonymised statistical format … the health data user shall have no access to the electronic health data used to provide that response" | Step 2. Statistics leave only through the privacy gate. Raw rows never leave the app. |
| 71 | Right to opt out … / Recht zum Widerspruch … | (3) data of people who opted out "shall not be made available or otherwise processed pursuant to data permits … or health data requests" | The 839 opted-out patients are removed when the CSVs are loaded, every query filters again, and the evaluation checks the store and every SPE. |
| 73 | Secure processing environment / Sichere Verarbeitungsumgebung | (1)(a) access restricted to "authorised natural persons listed in the data permit"; (1)(e) "identifiable logs of access … kept for at least one year"; (2) the body "shall review the electronic health data included in a download request to ensure that health data users are only able to download non-personal electronic health data" | One DuckDB file per permit, opened read-only with external file access disabled. Raw download returns HTTP 403 and is logged. Exports go through an automatic small-cell check and staff approval. Every console query is logged. |

## Articles used for duties, conditions and transparency

| Art. | Official title (EN / DE) | Key provision (verbatim) | How AccessDesk applies it |
|---|---|---|---|
| 57 | Tasks of health data access bodies / Aufgaben der Zugangsstellen für Gesundheitsdaten | (1)(e) a management system recording "the name of the health data applicant, the purpose of access, the date of issuance, the duration of the data permit and a description …"; (1)(j) "making public, through electronic means: … (ii) any health data access application and health data request without undue delay after initial reception; (iii) all data permits issued or health data requests approved as well as refusal decisions, including their justification, within 30 working days …" | The **transparency register** is required by Art. 57(1)(j)(ii) and (iii). It lists every request on receipt and the decision with its justification, but no numbers, patient data, identity-check details or internal flags. The staff inbox is the management system of point (e). |
| 58 | Obligations … towards natural persons / Pflichten … gegenüber natürlichen Personen | (1)(f) publish "who has been granted access to datasets … and details of the data permit regarding the purposes" | The register shows organisation, purpose, decision, articles, duration and record types for each permit. |
| 61 | Duties of health data users / Pflichten der Gesundheitsdatennutzer | (2) no access for "third parties not mentioned in the data permit"; (3) "shall not re-identify or attempt to re-identify"; (4) publish results "within 18 months", "only anonymous data", acknowledge the EHDS as source | Conditions in every approval letter. |
| 62 | Fees / Gebühren | fees may be charged | Placeholder condition in the permit (no fees in the demo). |

## Findings from the check

1. **The publication duty is Art. 57(1)(j).** Requests and applications are published on receipt (ii). Permits, approved requests and refusals are published with their justification within 30 working days (iii). Art. 58(1)(f) adds who was granted access, and for which purpose.
2. **Art. 53(2) reserves purposes (a) to (c)** (public health, policymaking, official statistics) for public sector bodies. The brief's decision order does not test this, and the metrics follow the brief. AccessDesk shows a staff warning when a private applicant relies only on (a) to (c). The decision itself does not change.
3. **Statistics instead of records** (R09-type cases) are covered by the second subparagraph of Art. 68(3) and require the applicant's agreement. The letter says so. The decision keeps the articles the brief expects: 53, 66, 69.
4. **Download review** is a duty of the access body under Art. 73(2). Rejecting raw downloads is not enough: the body must review what leaves. This is why exports need staff approval.

## What is simulated or out of scope

- eID (ID Austria, EUDI Wallet), the business register, ROR, the e-mandate service and the Medical Chamber are simulated. The Ed25519 signatures are real.
- Deadlines (Art. 68(4), 69(4)), fees (Art. 62), cross-border access (Art. 67(3), Art. 75) and national opt-out exceptions (Art. 71(4)) are not modelled.
- The information on legal remedies in the letter is a marked placeholder. National procedural law decides its content.
