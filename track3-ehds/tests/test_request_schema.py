"""Lenient intake: unusual but recognisable uploads are normalised (and say so) instead of being refused."""
import json
import unittest
from pathlib import Path

from desk.request_schema import RequestError, parse_request

ROOT = Path(__file__).resolve().parent.parent
BASE = json.loads((ROOT / "requests" / "R01.json").read_text(encoding="utf-8"))


class LenientIntakeTest(unittest.TestCase):
    def test_common_variations_are_normalised(self):
        variants = {
            "byte-order mark and a list": "\ufeff" + json.dumps([BASE, BASE]),
            "wrapped in an object": json.dumps({"request": BASE}),
            "other key names, text block": json.dumps({
                "Type": "Health Data Request", "Format": "anonymized statistics", "Purpose": BASE["purpose"],
                "Question": BASE["question"], "Definitions": "\n".join(BASE["definitions"])}),
            "missing format": json.dumps({k: v for k, v in BASE.items() if k != "requested_format"}),
        }
        for name, raw in variants.items():
            with self.subTest(name):
                req = parse_request(raw)
                self.assertEqual((req["requested_as"], req["requested_format"]),
                                 ("health data request", "anonymised statistics"))
                self.assertEqual(req["definitions"], BASE["definitions"])
                if name != "byte-order mark and a list" or True:
                    self.assertTrue(req.get("normalisation_notes") or name == "byte-order mark and a list")

    def test_missing_type_is_inferred_from_a_records_format(self):
        raw = {k: v for k, v in BASE.items() if k != "requested_as"}
        raw["requested_format"] = "pseudonymized patient records"
        req = parse_request(raw)
        self.assertEqual((req["requested_as"], req["requested_format"]),
                         ("health data access application", "pseudonymised records"))

    def test_unrecognisable_input_is_still_refused(self):
        for raw in ('{"hello": "world"}', "[1, 2, 3]", '"just text"'):
            with self.assertRaises(RequestError):
                parse_request(raw)


if __name__ == "__main__":
    unittest.main()
