"""Runs an access request through the five safeguards."""
import hashlib
import json
import os
import threading
import time

from . import audit as audit_module
from . import ai as ai_module
from . import ai_spec
from . import differencing
from . import store
from .plan import compiler, parser
from .safes import data as safe_data
from .safes import outputs, people, projects, settings


class AccessDesk:
    def __init__(self, data_dir, root, registry_path, expected_path=None):
        self.root = root
        os.makedirs(root, exist_ok=True)
        started = time.perf_counter()
        self.store = store.load(data_dir)
        self.ai = ai_module.Assistant(root)
        self.load_seconds = round(time.perf_counter() - started, 2)
        self.audit = audit_module.Audit(os.path.join(root, "audit.jsonl"))
        self.release_ledger = differencing.ReleaseLedger(root)
        self.registry = people.Registry(registry_path)
        self.expected = {}
        if expected_path and os.path.exists(expected_path):
            with open(expected_path, encoding="utf-8") as stream:
                self.expected = json.load(stream)
        self.cache = {}
        self.lock = threading.RLock()

    def process(self, request, use_cache=True, actor=None, login=None, differencing=False):
        with self.lock:
            return self._process(request, use_cache, actor, login, differencing)

    def _process(self, request, use_cache, actor, login, differencing_guard):
        cache_key = hashlib.sha256(
            json.dumps(
                [request, login, differencing_guard],
                sort_keys=True,
                ensure_ascii=False,
            ).encode("utf-8")
        ).hexdigest()
        if use_cache and cache_key in self.cache:
            return {**self.cache[cache_key], "cached": True}
        request_id = request.get("id") or ("U" + cache_key[:6])
        request = {**request, "id": request_id}
        actor = actor or f"applicant:{request.get('applicant', {}).get('name', '?')}"
        timings = {}
        started = time.perf_counter()
        self.audit.log(
            "request_received",
            request_id,
            actor,
            requested_as=request.get("requested_as"),
            organisation=request.get("applicant", {}).get("organisation"),
        )

        t = time.perf_counter()
        features = projects.analyze(request)
        who = self.registry.check(request, features, login=login)
        timings["identity"] = _ms(t)
        self.audit.log(
            "identity_checked",
            request_id,
            status=who["status"],
            checks={check["id"]: check["ok"] for check in who["checks"]},
            flags=[flag["id"] for flag in who["flags"]],
        )

        t = time.perf_counter()
        decision = projects.decide(request, features)
        ai_status = self.ai.status()
        ai = {
            "status": ai_status,
            "opinion": None,
            "agrees": None,
            "model": ai_status["model"],
            "cached": False,
        }
        if ai_status["enabled"]:
            system, user = ai_spec.purpose_messages(request)
            answer = self.ai.call("purpose", system, user, ai_spec.purpose_schema())
            ai["cached"] = answer["cached"]
            if answer["value"] is not None:
                opinion = dict(answer["value"])
                quote = str(opinion.get("evidence_quote") or "")
                request_text = "\n".join(
                    str(request.get(key) or "") for key in ("purpose", "question")
                )
                opinion["evidence_quote_verified"] = bool(
                    quote and quote.casefold() in request_text.casefold()
                )
                ai["opinion"] = opinion
                ai["agrees"] = opinion.get("prohibited") == (decision["decision"] == "REJECT")
            elif answer["reason"]:
                ai["status"] = {**ai_status, "reason": answer["reason"]}
        timings["purpose"] = _ms(t)
        self.audit.log(
            "decision_made",
            request_id,
            decision=decision["decision"],
            articles=decision["articles"],
            ai_agrees=ai["agrees"],
        )

        t = time.perf_counter()
        parser.AI_MAPPER = self._map_term if ai_status["enabled"] else None
        plan = parser.parse(request, self.store)
        mappings = safe_data.mappings(plan, self.store)
        timings["translation"] = _ms(t)

        t = time.perf_counter()
        sql, released, manifest, notes = None, None, None, []
        if decision["decision"] == "APPROVE_STATISTICAL":
            if plan.patient_level_requested:
                notes.append({
                    "en": "A patient-level listing was requested; only counts are released.",
                    "de": "Eine Liste einzelner Patient:innen wurde beantragt; freigegeben werden nur Anzahlen.",
                })
            result = compiler.run(plan, self.store)
            sql = result["sql"]
            timings["computation"] = _ms(t)
            t = time.perf_counter()
            released = outputs.release(result, plan)
            if differencing_guard:
                released_sets = compiler.cell_sets(plan, self.store)
                self.release_ledger.apply(
                    released, released_sets, request, request_id, self.store, plan.unit
                )
            outputs.assert_no_leak(released)
            timings["privacy_gate"] = _ms(t)
            self.audit.log(
                "statistics_computed",
                request_id,
                cells=released["gate"]["cells"],
                hidden=(
                    released["gate"]["counts_hidden"]
                    + released["gate"]["pct_suppressed"]
                    + released["gate"]["means_suppressed"]
                ),
            )
        elif decision["decision"] == "APPROVE_SPE":
            manifest = settings.create(
                request, plan, self.store, self.root, who["persons_with_access"]
            )
            sql = manifest["cohort_sql"]
            timings["computation"] = _ms(t)
            timings["privacy_gate"] = 0.0
            self.audit.log(
                "spe_created",
                request_id,
                permit=manifest["permit_id"],
                cohort_size=manifest["cohort_size"],
                tables=[record["table"] for record in manifest["tables_copied"]],
            )
        else:
            timings["computation"] = 0.0
            timings["privacy_gate"] = 0.0
            notes.append({
                "en": "Rejected: no query was run and no patient data was touched.",
                "de": "Abgelehnt: Es wurde keine Abfrage ausgeführt und kein Patientendatensatz berührt.",
            })

        delivery = self._delivery(decision, who, ai)
        self.audit.log("result_" + delivery["status"], request_id, decision=decision["decision"])
        timings["total"] = _ms(started)
        five_safes = self._five_safes(
            decision, who, plan, released, manifest, differencing_guard
        )
        funnel = (
            safe_data.applicant_funnel(plan, self.store)
            if decision["decision"] != "REJECT" else []
        )
        result = {
            "id": request_id,
            "request": request,
            "cached": False,
            "timings_ms": timings,
            "who": who,
            "features": features,
            "decision": {
                **decision,
                "articles_detail": [
                    {
                        "n": article,
                        "title_en": projects.ARTICLE_TITLES[article][0],
                        "title_de": projects.ARTICLE_TITLES[article][1],
                    }
                    for article in decision["articles"]
                ],
            },
            "ai": ai,
            "plan": plan.model_dump(mode="json"),
            "mappings": mappings,
            "sql": sql,
            "released": released,
            "spe": manifest,
            "notes": notes,
            "delivery": delivery,
            "opted_out_excluded": self.store.opted_out,
            "expected_check": None,
            "warnings": list(plan.warnings),
            "funnel": funnel,
            "five_safes": five_safes,
            "data_minimisation": safe_data.minimisation_summary(
                decision["decision"], plan, manifest
            ),
            "status": self._status(decision, delivery, plan),
        }
        expected = self.expected.get(request_id)
        if expected is not None and request.get("applicant") and _is_original(request, request_id):
            try:
                from .evaluation import compare
            except ImportError:
                pass
            else:
                result["expected_check"] = compare(result, expected)
        self.cache[cache_key] = result
        return result

    def _map_term(self, name, body):
        codes = ai_spec.allowed_codes(self.store)
        system, user = ai_spec.term_messages(self.store, name, body)
        answer = self.ai.call("term", system, user, ai_spec.term_schema(self.store))
        value = answer["value"]
        if not isinstance(value, dict) or value.get("system") not in ("icd10", "atc", "loinc"):
            return None
        allowed = {code.casefold(): code for code in codes}
        selected = []
        for code in value.get("codes", []):
            canonical = allowed.get(str(code).casefold())
            if canonical is None:
                return None
            selected.append(canonical)
        if not selected:
            return None
        code_system = value["system"]
        present = [
            code for system_name, code in self.store.descriptions
            if system_name == code_system
        ]
        if code_system == "loinc":
            if not all(code in present for code in selected):
                return None
        elif not all(any(code_in_data.startswith(code) for code_in_data in present) for code in selected):
            return None
        return {
            "system": code_system,
            "codes": selected,
            "note": str(value.get("note") or ""),
        }

    @staticmethod
    def _delivery(decision, who, ai):
        if decision["decision"] == "REJECT":
            return {
                "status": "rejection_sent",
                "en": "Decision sent to the applicant. No data released.",
                "de": "Bescheid an den Antragsteller gesendet. Keine Daten freigegeben.",
            }
        if who["status"] == "failed":
            return {
                "status": "on_hold_identity",
                "en": "On hold: a credential failed verification. Nothing is released until staff have checked the applicant.",
                "de": "Zurückgehalten: Ein Nachweis ist ungültig. Nichts wird freigegeben, bis die Behörde den Antragsteller geprüft hat.",
            }
        if who["status"] != "verified":
            return {
                "status": "on_hold_identity",
                "en": "On hold until the applicant has verified their identity (eID) and organisation.",
                "de": "Zurückgehalten, bis Identität (eID) und Organisation bestätigt sind.",
            }
        if who["flags"] or ai.get("agrees") is False:
            return {
                "status": "on_hold_review",
                "en": "Approved by the rules, but held for staff review (see warnings).",
                "de": "Nach den Regeln genehmigt, aber zur Prüfung durch die Behörde zurückgehalten (siehe Hinweise).",
            }
        if decision["decision"] == "APPROVE_SPE":
            return {
                "status": "access_granted",
                "en": "Data permit issued. Access only inside the secure environment.",
                "de": "Datengenehmigung erteilt. Zugriff nur in der sicheren Umgebung.",
            }
        return {
            "status": "released",
            "en": "Statistics released to the applicant.",
            "de": "Statistik an den Antragsteller freigegeben.",
        }

    @staticmethod
    def _status(decision, delivery, plan):
        if delivery["status"] == "on_hold_identity":
            return "held_identity"
        if delivery["status"] == "on_hold_review" or (
            decision["decision"] != "REJECT" and plan.warnings
        ):
            return "review_needed"
        return "auto_decided"

    @staticmethod
    def _five_safes(decision, who, plan, released, manifest, differencing_guard=False):
        people_status = {
            "verified": "pass", "unverified": "warn", "failed": "fail",
        }[who["status"]]
        if who["flags"] and people_status == "pass":
            people_status = "warn"
        if who["status"] == "failed":
            people_en, people_de = "A credential failed verification.", "Ein Nachweis ist ungültig."
        elif people_status == "warn":
            people_en, people_de = "Identity is unverified or needs review.", "Identität ist ungeprüft oder muss geprüft werden."
        else:
            people_en, people_de = "Applicant credentials were verified.", "Die Nachweise des Antragstellers wurden geprüft."

        rejected = decision["decision"] == "REJECT"
        projects_status = "fail" if rejected else "pass"
        projects_en = "Purpose rejected under Art. 54." if rejected else "Purpose approved under the decision rules."
        projects_de = "Zweck nach Art. 54 abgelehnt." if rejected else "Zweck nach den Entscheidungsregeln genehmigt."

        data_status = "warn" if plan.warnings else "pass"
        data_en = "Parser warnings require review." if plan.warnings else "Definitions were translated into a typed, validated query plan."
        data_de = "Parserhinweise müssen geprüft werden." if plan.warnings else "Definitionen wurden in einen typisierten, validierten Abfrageplan übersetzt."

        if decision["decision"] == "APPROVE_STATISTICAL":
            settings_status = outputs_status = "pass"
            settings_en = "Processed inside the access body; only gated aggregates leave."
            settings_de = "In der Behörde verarbeitet; nur geschützte Aggregate verlassen sie."
            gate = released["gate"]
            outputs_en = (
                f"Small-cell gate applied to {gate['cells']} cells; "
                f"{gate['counts_hidden'] + gate['pct_suppressed'] + gate['means_suppressed']} suppressed."
            )
            outputs_de = (
                f"Kleinzellenschleuse auf {gate['cells']} Zellen angewandt; "
                f"{gate['counts_hidden'] + gate['pct_suppressed'] + gate['means_suppressed']} unterdrückt."
            )
            diff_count = len((released.get("differencing") or {}).get("suppressed", []))
            if differencing_guard and diff_count:
                outputs_status = "warn"
                outputs_en = f"Differencing check: {diff_count} cells suppressed."
                outputs_de = f"Differenz-Schutz: {diff_count} Zellen unterdrückt."
        elif decision["decision"] == "APPROVE_SPE":
            settings_status = outputs_status = "pass"
            settings_en = "Separate permit workspace; downloads are blocked."
            settings_de = "Getrennter Genehmigungsarbeitsbereich; Downloads sind gesperrt."
            outputs_en = "Only reviewed aggregates or model weights may leave."
            outputs_de = "Nur geprüfte Aggregate oder Modellgewichte dürfen die Umgebung verlassen."
        else:
            settings_status = outputs_status = "na"
            settings_en = outputs_en = "No data processing or output for a rejected request."
            settings_de = outputs_de = "Keine Datenverarbeitung oder Ausgabe für einen abgelehnten Antrag."

        return {
            "people": {
                "status": people_status, "summary_en": people_en, "summary_de": people_de,
            },
            "projects": {
                "status": projects_status, "summary_en": projects_en, "summary_de": projects_de,
            },
            "data": {
                "status": data_status, "summary_en": data_en, "summary_de": data_de,
            },
            "settings": {
                "status": settings_status, "summary_en": settings_en, "summary_de": settings_de,
            },
            "outputs": {
                "status": outputs_status, "summary_en": outputs_en, "summary_de": outputs_de,
            },
        }

    def _mappings(self, plan):
        return safe_data.mappings(plan, self.store)


def _ms(started):
    return round((time.perf_counter() - started) * 1000, 1)


def _is_original(request, request_id):
    return request_id.startswith("R") and len(request_id) == 3
