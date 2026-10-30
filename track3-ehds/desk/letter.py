"""Decision letter as a PDF, using only the standard library: a small PDF 1.4 writer with the built-in Helvetica
fonts (no embedding), A4 pages, automatic line wrapping and page breaks."""
from __future__ import annotations

import datetime as dt

from .pipeline import receive_text, short_reason

PAGE_W, PAGE_H, MARGIN = 595.0, 842.0, 56.0
# Helvetica advance widths (1/1000 em) for ASCII 32..126, from the Adobe core font metrics
_WIDTHS = [278, 278, 355, 556, 556, 889, 667, 191, 333, 333, 389, 584, 278, 333, 278, 278, 556, 556, 556, 556, 556,
           556, 556, 556, 556, 556, 278, 278, 584, 584, 584, 556, 1015, 667, 667, 722, 722, 667, 611, 778, 722, 278,
           500, 667, 556, 833, 722, 778, 667, 778, 722, 667, 611, 722, 667, 944, 667, 667, 611, 278, 278, 278, 469,
           556, 333, 556, 556, 500, 556, 556, 278, 556, 556, 222, 222, 500, 222, 833, 556, 556, 556, 556, 333, 500,
           278, 556, 500, 722, 500, 500, 500, 334, 260, 334, 584]
INK, MUTED, BRAND = (0.06, 0.09, 0.16), (0.40, 0.44, 0.52), (0.01, 0.41, 0.63)
OUTCOME_COLOUR = {"REJECT": (0.71, 0.14, 0.09), "APPROVE_STATISTICAL": (0.02, 0.46, 0.28),
                  "APPROVE_SPE": (0.09, 0.36, 0.83), "NO_DECISION": (0.58, 0.22, 0.05)}
OUTCOME_TITLE = {"REJECT": "Rejected", "APPROVE_STATISTICAL": "Approved: anonymised statistics",
                 "APPROVE_SPE": "Approved: secure processing environment", "NO_DECISION": "Referred to staff review"}
TABLE_TITLES = {"patients": "Patients (demographics)", "conditions": "Conditions (ICD-10)",
                "medications": "Medications (ATC)", "observations": "Observations (LOINC)", "encounters": "Encounters"}


def _width(text: str, size: float, bold: bool) -> float:
    w = sum(_WIDTHS[ord(c) - 32] if 32 <= ord(c) <= 126 else 556 for c in text)
    return w * size / 1000 * (1.07 if bold else 1.0)


def _wrap(text: str, size: float, width: float, bold: bool) -> list[str]:
    lines, cur = [], ""
    for word in text.split():
        cand = f"{cur} {word}".strip()
        if cur and _width(cand, size, bold) > width:
            lines.append(cur)
            cur = word
        else:
            cur = cand
    return lines + [cur] if cur else lines or [""]


def _pdf_string(s: str) -> bytes:
    for a, b in (("≥", ">="), ("≤", "<="), ("→", "->"), ("✓", "OK"), ("✗", "x"), ("≈", "~")):
        s = s.replace(a, b)
    raw = s.encode("cp1252", errors="replace")  # WinAnsiEncoding of the built-in fonts
    return raw.replace(b"\\", b"\\\\").replace(b"(", b"\\(").replace(b")", b"\\)")


class _Document:
    def __init__(self, footer: str):
        self.footer = footer
        self.pages: list[bytes] = []
        self.ops: list[bytes] = []
        self.y = PAGE_H - MARGIN

    def _page_break(self):
        self.ops.append(b"BT /F1 8 Tf %.3f %.3f %.3f rg %.1f %.1f Td (%s) Tj ET" % (
            *MUTED, MARGIN, MARGIN - 24, _pdf_string(f"{self.footer} - page {len(self.pages) + 1}")))
        self.pages.append(b"\n".join(self.ops))
        self.ops, self.y = [], PAGE_H - MARGIN

    def text(self, s: str, size: float = 10.5, bold: bool = False, colour=INK, after: float = 4, indent: float = 0):
        for line in _wrap(s, size, PAGE_W - 2 * MARGIN - indent, bold):
            if self.y - size * 1.3 < MARGIN:
                self._page_break()
            self.y -= size * 1.3
            self.ops.append(b"BT /%s %.1f Tf %.3f %.3f %.3f rg %.1f %.1f Td (%s) Tj ET" % (
                b"F2" if bold else b"F1", size, *colour, MARGIN + indent, self.y, _pdf_string(line)))
        self.y -= after

    def labelled(self, label: str, value: str):
        self.text(label, 8.5, True, MUTED, after=1)
        self.text(value or "-", 10.5, after=7)

    def rule(self, gap: float = 10):
        self.y -= gap / 2
        self.ops.append(b"%.3f %.3f %.3f RG 0.6 w %.1f %.1f m %.1f %.1f l S" % (
            0.85, 0.89, 0.93, MARGIN, self.y, PAGE_W - MARGIN, self.y))
        self.y -= gap / 2

    def to_pdf(self) -> bytes:
        self._page_break()
        objects = [b"<< /Type /Catalog /Pages 2 0 R >>", b"",
                   b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>",
                   b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold /Encoding /WinAnsiEncoding >>"]
        kids = []
        for content in self.pages:
            objects.append(b"<< /Length %d >>\nstream\n%s\nendstream" % (len(content) + 1, content))
            objects.append(b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Resources << /Font << /F1 3 0 R "
                           b"/F2 4 0 R >> >> /Contents %d 0 R >>" % (len(objects)))
            kids.append(len(objects))
        objects[1] = b"<< /Type /Pages /Kids [%s] /Count %d >>" % (b" ".join(b"%d 0 R" % k for k in kids), len(kids))
        out, offsets = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n"), []
        for i, obj in enumerate(objects, 1):
            offsets.append(len(out))
            out += b"%d 0 obj\n%s\nendobj\n" % (i, obj)
        xref = len(out)
        out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objects) + 1)
        out += b"".join(b"%010d 00000 n \n" % o for o in offsets)
        out += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objects) + 1, xref)
        return bytes(out)


def _fmt(v) -> str:
    if isinstance(v, int):
        return f"{v:,}".replace(",", " ")
    if isinstance(v, float):
        return f"{v:.1f}"
    return str(v)


def decision_letter(case: dict) -> bytes:
    """The decision as a short, printable letter for the applicant's records."""
    req = case.get("request") or {}
    d = case.get("decision") or {}
    ap = req.get("applicant") or {}
    ident = case.get("identity")
    try:
        date = dt.datetime.strptime(case.get("received_at", ""), "%Y-%m-%d %H:%M:%S").strftime("%d %B %Y")
    except ValueError:
        date = case.get("received_at", "")
    doc = _Document("Doccess - hackathon simulation on synthetic data - not a decision of a real access body")
    doc.text("Doccess", 22, True, BRAND, after=0)
    doc.text("Secure access to health data for research and better care", 9.5, colour=MUTED, after=6)
    doc.rule(14)
    doc.text("Decision on your health data request", 16, True, after=2)
    doc.text(f"Case {case.get('case_id')} - {date}", 10, colour=MUTED, after=10)

    if case.get("status") == "INVALID_REQUEST":
        doc.text("The request was not valid and was not assessed:", 11, True)
        for e in case.get("errors") or []:
            doc.text(f"- {e}", indent=10)
        return doc.to_pdf()

    applicant = ", ".join(x for x in (ident["name"] if ident else ap.get("name"), ap.get("organisation")) if x)
    if ident:
        applicant += " (identified with ID Austria, simulated)"
    doc.labelled("APPLICANT", applicant)
    doc.labelled("REQUEST", f"{req.get('id')} - {req.get('requested_as')} - {req.get('requested_format')}")
    doc.labelled("PURPOSE", req.get("purpose", ""))
    doc.labelled("QUESTION", req.get("question", ""))
    doc.rule(14)

    outcome = d.get("outcome", "")
    doc.text(f"Decision: {OUTCOME_TITLE.get(outcome, outcome)}", 15, True, OUTCOME_COLOUR.get(outcome, INK), after=1)
    doc.text(outcome, 9, colour=MUTED, after=8)
    doc.labelled("IN SHORT", short_reason(d))
    doc.labelled("LEGAL BASIS", "; ".join(f"Art. {a} {d.get('article_titles', {}).get(a, '')}".strip()
                                          for a in d.get("articles") or []))
    doc.labelled("WHAT YOU RECEIVE", receive_text(d, case.get("fulfilment") or {}))
    doc.labelled("REASONING", d.get("reason", ""))
    doc.rule(14)

    res = case.get("result") or {}
    if res.get("kind") == "statistics":
        doc.text("Anonymised statistics", 12, True, after=2)
        doc.text("Counts below 10 are shown as <10; percentages and means based on fewer than 10 patients are "
                 "suppressed. Values are rounded half up to one decimal.", 9, colour=MUTED, after=6)
        labels = {c["id"]: c["label"] for c in res.get("columns", [])}
        for row in res.get("rows", []):
            cells = "   ".join(f"{labels[k]}: {_fmt(v)}" for k, v in row["cells"].items())
            doc.text(f"{row['label']}", 10, True, after=0)
            doc.text(cells, 9.5, indent=10, after=4)
    elif res.get("kind") == "spe":
        doc.text("Secure processing environment", 12, True, after=2)
        doc.text(f"{_fmt(res.get('cohort_size'))} patients were selected (exact count). Only these patients and the "
                 "requested record types were copied into an isolated workspace; downloads of records are blocked.",
                 10, after=6)
        for t, info in (res.get("tables") or {}).items():
            filt = f", LOINC {', '.join(info['filter']['loinc'])} only" if (info.get("filter") or {}).get("loinc") else ""
            doc.text(f"- {TABLE_TITLES.get(t, t)}: {_fmt(info['rows'])} rows for {_fmt(info['patients'])} patients{filt}",
                     10, indent=6, after=2)
    else:
        doc.text("No patient data was released.", 10.5)
    checks = case.get("privacy_checks") or []
    if checks:
        passed = sum(c["status"] == "pass" for c in checks)
        doc.y -= 6
        doc.text(f"Privacy checks: {passed} of {len(checks)} passed.", 10, colour=MUTED)
    doc.y -= 8
    doc.text("This letter was generated automatically by Doccess, a hackathon prototype on synthetic data. It is not a "
             "decision of a real health data access body.", 8.5, colour=MUTED)
    return doc.to_pdf()
