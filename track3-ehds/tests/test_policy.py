"""Decision rules (Art. 53, 54, 66, 68, 69, 73) without touching patient data."""
import unittest

from desk import policy
from desk.request_schema import RequestError, parse_request


def req(purpose, question="How many patients have diabetes by region?", requested_as="health data request",
        fmt="anonymised statistics", definitions=None, organisation="Some organisation"):
    return parse_request({"id": "X", "applicant": {"name": "A", "organisation": organisation, "country": "AT"},
                          "requested_as": requested_as, "requested_format": fmt, "purpose": purpose,
                          "question": question, "definitions": definitions or ["Report per region: patients."]})


class ProhibitedPurposeTest(unittest.TestCase):
    def assertRejected(self, purpose, point):
        d = policy.decide(req(purpose))
        self.assertEqual(d.outcome, policy.REJECT, purpose)
        self.assertEqual(d.articles, ["54"])
        self.assertIn(point, [f.point for f in d.prohibited])

    def test_prohibited_purposes(self):
        self.assertRejected("We want to set private health insurance premiums according to the risk of diabetics.",
                            "54(1)(b)")
        self.assertRejected("Our bank wants to use diagnoses to improve credit scoring of loan applicants.", "54(1)(b)")
        self.assertRejected("We will match the records with our employee list before we renew contracts.", "54(1)(b)")
        self.assertRejected("We plan an advertising campaign for our new inhaler in regions with many asthma patients.",
                            "54(1)(c)")
        self.assertRejected("We are developing new e-cigarette flavours and want to position them for young adults.",
                            "54(1)(d)")
        self.assertRejected("We develop alcoholic beverages and want to target regions with high consumption.", "54(1)(d)")

    def test_more_prohibited_phrasings(self):
        for purpose in (
                "We are a pharmaceutical company and want to identify regions with low prescription rates to target "
                "our sales representatives.",
                "We want to know which of our customers have diabetes so we can adjust their contracts.",
                "A betting company wants to find regions with high depression rates for its campaigns.",
                "We want to increase sales of our new inhaler in regions with many asthma patients.",
                "We want to develop an energy drink with high caffeine and market it to young adults.",
                "We will use the data to decide which patients should be denied reimbursement.",
                "We want to link the hospital data with our customer database to identify individual patients."):
            d = policy.decide(req(purpose))
            self.assertEqual((d.outcome, d.articles), (policy.REJECT, ["54"]), purpose)

    def test_benign_mentions_are_not_rejected(self):
        for purpose in ("Post-marketing surveillance of SGLT2 inhibitor safety for the medicines agency.",
                        "Research to evaluate a smoking cessation programme and support tobacco control policy.",
                        "Public health research on alcohol-related liver disease to improve prevention.",
                        "The public health insurance fund plans prevention programmes for patients with diabetes.",
                        "A public health campaign against gambling addiction needs regional depression figures.",
                        "Research on the labour market participation of people with chronic diseases, for policy.",
                        "The national vaccination campaign of the health authority needs regional asthma prevalence.",
                        "Occupational health research on sick leave patterns in healthcare workers (aggregated).",
                        "Health technology assessment of GLP-1 receptor agonists for the reimbursement body."):
            d = policy.decide(req(purpose))
            self.assertNotEqual(d.outcome, policy.REJECT, purpose)

    def test_applicant_identity_is_not_used(self):
        legit = "Research on regional differences in type 2 diabetes to plan prevention."
        for org in ("Alpenland Versicherung AG, pricing department", "Brightline Health Marketing GmbH"):
            self.assertEqual(policy.decide(req(legit, organisation=org)).outcome, policy.APPROVE_STATISTICAL)


class RouteTest(unittest.TestCase):
    def test_health_data_request_is_statistical_even_with_justification(self):
        d = policy.decide(req("Research to train a model; aggregates are not enough."))
        self.assertEqual((d.outcome, d.articles), (policy.APPROVE_STATISTICAL, ["53", "69"]))

    def test_access_application_with_justification_gets_spe(self):
        d = policy.decide(req("We train and validate a prediction model. Training needs individual-level histories; "
                              "aggregates are not enough.", requested_as="health data access application",
                              fmt="pseudonymised records"))
        self.assertEqual((d.outcome, d.articles), (policy.APPROVE_SPE, ["53", "66", "68", "73"]))
        self.assertIsNotNone(d.justification)

    def test_access_application_without_justification_gets_statistics(self):
        for purpose in ("We compare ACE inhibitor use between age groups to update a teaching module.",
                        "Research on diabetes care; we do not need individual-level data."):
            d = policy.decide(req(purpose, requested_as="health data access application", fmt="pseudonymised records"))
            self.assertEqual((d.outcome, d.articles), (policy.APPROVE_STATISTICAL, ["53", "66", "69"]), purpose)

    def test_no_recognisable_purpose_is_not_auto_approved(self):
        d = policy.decide(req("We are curious about the numbers."))
        self.assertEqual(d.outcome, policy.NO_DECISION)
        self.assertEqual(d.articles, [])


class RequestValidationTest(unittest.TestCase):
    def test_invalid_requests_fail_clearly(self):
        with self.assertRaises(RequestError) as ctx:
            parse_request('{"requested_as": "something else", "purpose": "x"}')
        self.assertTrue(any("requested_as" in e for e in ctx.exception.errors))
        with self.assertRaises(RequestError):
            parse_request("not json")
        with self.assertRaises(RequestError):
            parse_request("[1, 2]")


if __name__ == "__main__":
    unittest.main()
