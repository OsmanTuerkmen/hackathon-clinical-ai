from accessdesk.safes import projects


def _features(purpose, question="How many patients?"):
    return projects.analyze({
        "purpose": purpose,
        "question": question,
        "applicant": {"organisation": "University"},
    })


def test_benign_purposes_are_not_false_positives():
    for purpose in [
        "We evaluate a smoking cessation programme for patients with COPD.",
        "Post-marketing surveillance of SGLT2 inhibitors for side effects.",
        "Research on the health of hospital employees' patients is not planned; we study asthma.",
    ]:
        assert _features(purpose)["prohibited"] == []


def test_prohibited_purposes_are_categorized():
    cases = [
        ("We want to set the tariffs of our health insurance products.", "insurance"),
        ("We plan an advertising campaign for our new drug.", "marketing"),
        ("We develop new vape flavours for young adults.", "harmful_products"),
    ]
    for purpose, category in cases:
        assert _features(purpose)["prohibited"][0]["category"] == category


def test_disguised_credit_employment_and_brand_marketing_purposes_are_rejected():
    cases = [
        (
            "We want to raise awareness for our statin brand and position the product among cardiologists.",
            "NovaPharma AG, Brand Communications",
            "marketing",
        ),
        (
            "We want to adjust credit limits and repayment terms using the health data.",
            "Alpen Bank AG, Credit Risk",
            "insurance",
        ),
        (
            "We want to decide which fixed-term staff to keep based on their records.",
            "North Services GmbH, People & Culture",
            "employment",
        ),
    ]
    for purpose, organisation, category in cases:
        features = projects.analyze({
            "purpose": purpose, "question": "", "applicant": {"organisation": organisation},
        })
        assert features["prohibited"][0]["category"] == category


def test_benign_health_awareness_workforce_brand_and_credit_studies_are_not_rejected():
    controls = [
        ("The regional health authority plans a vaccination awareness campaign for older adults.", "Regional Health Authority"),
        ("The ministry plans the nursing workforce needed for an ageing population.", "Ministry of Health"),
        ("We compare how often brand-name and generic statins are prescribed, to advise on cost-effective prescribing.", "University"),
        ("We study whether financial stress, such as unpaid credit card debt, is linked to depression.", "Research Institute"),
        ("Research on staff health in hospitals to improve occupational safety.", "University Hospital"),
        ("We evaluate a smoking cessation programme for patients with COPD.", "University"),
        ("Post-marketing surveillance of SGLT2 inhibitors for side effects.", "University"),
        ("Research on the health of hospital employees' patients is not planned; we study asthma.", "University"),
    ]
    for purpose, organisation in controls:
        features = projects.analyze({
            "purpose": purpose,
            "question": "",
            "applicant": {"organisation": organisation},
        })
        assert features["prohibited"] == [], purpose


def test_fixed_decision_order_for_prohibited_statistics_and_spe():
    rejected = projects.decide(
        {"requested_as": "health data request", "purpose": "Advertising campaign."},
        _features("Advertising campaign."),
    )
    assert (rejected["decision"], rejected["articles"]) == ("REJECT", ["54"])

    statistical = projects.decide(
        {"requested_as": "health data request", "purpose": "Research."},
        _features("Research."),
    )
    assert (statistical["decision"], statistical["articles"]) == (
        "APPROVE_STATISTICAL", ["53", "69"],
    )

    spe = projects.decide(
        {"requested_as": "health data access application", "purpose": "Research; individual-level records are needed."},
        _features("Research; individual-level records are needed."),
    )
    assert (spe["decision"], spe["articles"]) == ("APPROVE_SPE", ["53", "66", "68", "73"])
