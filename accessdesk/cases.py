"""Persistent inbox, applicant submissions, and staff reviews."""
import json
import re
import threading
from datetime import datetime, timezone
from pathlib import Path

from .atomic import write_json_atomic
from .config import load_requests
from .safes.projects import ARTICLE_TITLES


class CaseRegistry:
    def __init__(self, desk, data_dir):
        self.desk = desk
        self.data_dir = Path(data_dir).resolve()
        self.root = Path(desk.root).resolve()
        self.submissions_dir = self.root / "submissions"
        self.reviews_path = self.root / "reviews.json"
        self._lock = threading.RLock()
        self._cases = {}
        self._reviews = self._read_reviews()
        for group, request in load_requests(self.data_dir):
            self._add(group, request, None)
        self.submissions_dir.mkdir(parents=True, exist_ok=True)
        for path in sorted(self.submissions_dir.glob("U*.json")):
            with path.open(encoding="utf-8") as stream:
                submission = json.load(stream)
            self._add("custom", submission["request"], submission.get("login"))
        ids = [
            int(match.group(1))
            for case_id in self._cases
            if (match := re.fullmatch(r"U(\d+)", case_id))
        ]
        self._next_id = max(ids, default=0) + 1

    def _read_reviews(self):
        if not self.reviews_path.exists():
            return {}
        with self.reviews_path.open(encoding="utf-8") as stream:
            reviews = json.load(stream)
        if not isinstance(reviews, dict):
            raise ValueError("reviews.json must contain a case-to-review mapping")
        return reviews

    def _add(self, group, request, login):
        request = dict(request)
        case_id = request["id"]
        received_at = request.get("submitted") or _now()
        auth_login = "" if group == "custom" and login is None else login
        result = self.desk.process(
            request,
            use_cache=True,
            actor=f"system:case-registry",
            login=auth_login,
        )
        self._cases[case_id] = {
            "group": group,
            "request": request,
            "login": login,
            "received_at": received_at,
            "result": result,
        }

    def list(self, status=None, decision=None, q=None, group=None):
        with self._lock:
            summaries = [self._summary(case_id, case) for case_id, case in self._cases.items()]
        query = q.casefold().strip() if q else None
        if status:
            summaries = [summary for summary in summaries if summary["status"] == status]
        if decision:
            summaries = [summary for summary in summaries if summary["decision"] == decision]
        if group:
            summaries = [summary for summary in summaries if summary["group"] == group]
        if query:
            summaries = [
                summary for summary in summaries
                if query in " ".join(str(value) for value in (
                    summary["id"], summary["applicant"]["name"], summary["applicant"]["organisation"],
                    summary["question"],
                )).casefold()
            ]
        return sorted(summaries, key=lambda summary: (summary["received_at"], summary["id"]), reverse=True)

    def get(self, case_id):
        with self._lock:
            case = self._cases.get(case_id)
            if case is None:
                return None
            summary = self._summary(case_id, case)
            result = self._effective_result(case_id, case)
            return {
                "summary": summary,
                "result": result,
                "reviews": list(self._reviews.get(case_id, [])),
                "visible_to_applicant": self._visible(summary, result),
                "login": case["login"],
                "audit_path": self.desk.audit.path,
            }

    def submit(self, request, login=None):
        with self._lock:
            case_id = f"U{self._next_id:02d}"
            submitted = request.get("submitted") or _now()
            stored_request = {**request, "id": case_id, "submitted": submitted}
            result = self.desk.process(
                stored_request,
                use_cache=True,
                actor=f"applicant:{stored_request.get('applicant', {}).get('name', '?')}",
                login=login or "",
            )
            case = {
                "group": "custom",
                "request": stored_request,
                "login": login,
                "received_at": submitted,
                "result": result,
            }
            write_json_atomic(
                self.submissions_dir / f"{case_id}.json",
                {"request": stored_request, "login": login},
            )
            self._next_id += 1
            self._cases[case_id] = case
            return self._summary(case_id, case)

    def review(self, case_id, action, reason, reviewer):
        if action not in ("release", "hold", "reject"):
            raise ValueError("action must be release, hold, or reject")
        reason, reviewer = reason.strip(), reviewer.strip()
        if not 20 <= len(reason) <= 2000:
            raise ValueError("reason must contain 20 to 2,000 characters")
        if not 2 <= len(reviewer) <= 80:
            raise ValueError("reviewer must contain 2 to 80 characters")
        with self._lock:
            case = self._cases.get(case_id)
            if case is None:
                return None
            previous_status = self._summary(case_id, case)["status"]
            review = {
                "action": action,
                "reason": reason,
                "reviewer": reviewer,
                "reviewed_at": _now(),
            }
            self._reviews.setdefault(case_id, []).append(review)
            write_json_atomic(self.reviews_path, self._reviews)
            summary = self._summary(case_id, case)
            self.desk.audit.log(
                "case_reviewed",
                case_id,
                actor=reviewer,
                action=action,
                reason=reason,
                reviewer=reviewer,
                previous_status=previous_status,
                new_status=summary["status"],
            )
            return summary

    def _last_review(self, case_id):
        reviews = self._reviews.get(case_id, [])
        return reviews[-1] if reviews else None

    def _status(self, case_id, result):
        review = self._last_review(case_id)
        if review:
            return {
                "release": "released",
                "hold": "review_needed",
                "reject": "rejected_after_review",
            }[review["action"]]
        return result["status"]

    def _effective_result(self, case_id, case):
        result = dict(case["result"])
        result["decision"] = dict(case["result"]["decision"])
        result["delivery"] = dict(case["result"]["delivery"])
        review = self._last_review(case_id)
        if not review:
            if (
                result["status"] == "review_needed"
                and result["delivery"]["status"] in ("released", "access_granted")
            ):
                result["delivery"].update({
                    "status": "on_hold_review",
                    "en": "Approved by the rules, but held for staff review (see warnings).",
                    "de": "Nach den Regeln genehmigt, aber zur Prüfung durch die Behörde zurückgehalten (siehe Hinweise).",
                })
            return result
        if review["action"] == "hold":
            result["delivery"].update({
                "status": "on_hold_review",
                "en": "Approved by the rules, but held for staff review (see warnings).",
                "de": "Nach den Regeln genehmigt, aber zur Prüfung durch die Behörde zurückgehalten (siehe Hinweise).",
            })
        elif review["action"] == "reject":
            result["decision"].update({
                "decision": "REJECT",
                "articles": ["54"],
                "reason_en": review["reason"],
                "reason_de": review["reason"],
                "articles_detail": [{
                    "n": "54",
                    "title_en": ARTICLE_TITLES["54"][0],
                    "title_de": ARTICLE_TITLES["54"][1],
                }],
            })
            result["delivery"].update({
                "status": "rejection_sent",
                "en": "Decision sent to the applicant. No data released.",
                "de": "Bescheid an den Antragsteller gesendet. Keine Daten freigegeben.",
            })
        elif result["decision"]["decision"] == "REJECT":
            result["delivery"]["status"] = "rejection_sent"
        elif result["decision"]["decision"] == "APPROVE_SPE":
            result["delivery"]["status"] = "access_granted"
        elif result["decision"]["decision"] == "APPROVE_STATISTICAL":
            result["delivery"]["status"] = "released"
        return result

    def _summary(self, case_id, case):
        result = self._effective_result(case_id, case)
        request = case["request"]
        applicant = request.get("applicant") or {}
        decision = result["decision"]
        features = result["features"]
        five_safes = {
            safe: values["status"] for safe, values in result["five_safes"].items()
        }
        if decision["decision"] == "REJECT" and self._status(case_id, result) == "rejected_after_review":
            five_safes.update({"projects": "fail", "settings": "na", "outputs": "na"})
        kind = "application" if "access application" in decision.get("kind", "").lower() else "request"
        return {
            "id": case_id,
            "group": case["group"],
            "submitted": request.get("submitted"),
            "received_at": case["received_at"],
            "applicant": {
                "name": applicant.get("name", ""),
                "organisation": applicant.get("organisation", ""),
                "country": applicant.get("country", ""),
            },
            "requested_as": request.get("requested_as"),
            "kind": kind,
            "question": request.get("question", ""),
            "decision": decision["decision"],
            "articles": list(decision["articles"]),
            "status": self._status(case_id, case["result"]),
            "delivery_status": result["delivery"]["status"],
            "five_safes": five_safes,
            "flags_count": len(features.get("prohibited", [])) + len(result["who"].get("flags", [])),
            "ai_involved": bool(result["ai"].get("opinion")) or any(
                "ai" in mapping.get("source", "").casefold()
                for mapping in result.get("mappings", [])
            ),
            "permit_id": (result.get("spe") or {}).get("permit_id"),
            "reviewed": bool(self._last_review(case_id)),
        }

    @staticmethod
    def _visible(summary, result):
        return (
            summary["status"] == "auto_decided"
            and result["delivery"]["status"] in ("released", "access_granted")
        ) or summary["status"] == "released"


def _now():
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")
