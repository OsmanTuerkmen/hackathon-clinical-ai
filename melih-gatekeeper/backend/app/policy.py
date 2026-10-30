"""Policy as data: EHDS Art. 53 purposes and Art. 54 prohibitions.

Single source of truth for the keyword rules, the LLM prompt (descriptions and examples) and the tests.
Quotes are short excerpts of Regulation (EU) 2025/327; verify against EUR-Lex before production use.
"""
from __future__ import annotations

PROHIBITED: dict[str, dict] = {
    "decisions_detrimental_to_persons": {
        "article": "54(1)(a)-(b)",
        "quote": "taking decisions detrimental to a natural person or a group of natural persons",
        "description": "Decisions that harm individuals or groups, incl. job offers, contracts, credit, or less favourable terms for goods or services.",
        "keywords": [r"employee", r"\bstaff list", r"recruit", r"job applicant", r"applicants?\b.{0,20}\bscreen", r"renew(ing)? contracts",
                     r"\bhr department", r"\bhiring\b", r"credit scor", r"creditworth", r"\bloan", r"tenant screening", r"mitarbeiter", r"bewerber"],
        "examples": ["Match records with our employee list before renewing contracts.", "Use diagnoses to score loan applicants."],
        "near_misses": ["Occupational-health research by a public health institute on shift work and depression."],
    },
    "insurance_exclusion_or_premiums": {
        "article": "54(1)(b)",
        "quote": "excluding them from the benefit of an insurance or credit contract or to modify their contributions and insurance premiums",
        "description": "Excluding people from insurance, or setting or adjusting premiums using health data.",
        "keywords": [r"premium", r"insurance pric", r"\bpricing\b", r"underwrit", r"insurab", r"risk[- ]based pric", r"tarif", r"prämie"],
        "examples": ["Align private health insurance premiums with actual risk."],
        "near_misses": ["A social insurer studying the effect of a prevention programme, explicitly not used for pricing."],
    },
    "advertising_or_marketing": {
        "article": "54(1)(c)",
        "quote": "carrying out advertising or marketing activities",
        "description": "Advertising or marketing to health professionals, organisations or the public.",
        "keywords": [r"advertis", r"marketing", r"(advertising|marketing|sales|promotional|ad) campaigns?", r"promot(e|ing) (our|the|a new|their) (product|drug|brand)", r"promotional", r"sales (force|target|territor)", r"position(ing)? (the|our) product",
                     r"market share", r"werbung", r"vermarkt"],
        "examples": ["Focus our physician advertising campaign on regions where the drug is prescribed most."],
        "near_misses": ["A pharmacovigilance study of a newly launched drug's safety, required by the regulator."],
    },
    "harmful_products": {
        "article": "54(1)(d)",
        "quote": "developing products or services that may harm individuals, public health or society at large",
        "description": "Developing products or services that may harm people, e.g. illicit drugs, alcohol, tobacco and nicotine, weapons, or addictive products.",
        "keywords": [r"nicotine", r"tobacco", r"cigarette", r"\bvap(e|ing)\b", r"pouch", r"alcohol", r"\bbeer\b", r"spirits", r"weapon", r"gambling", r"illicit drug",
                     r"tabak", r"alkohol"],
        "examples": ["Develop nicotine pouch flavours positioned as a healthier alternative."],
        "near_misses": ["University study of smoking-cessation outcomes to plan a public quit-smoking programme."],
    },
    "ethics_violation": {
        "article": "54(1)(e)",
        "quote": "activities in conflict with ethical provisions laid down in national law",
        "description": "Anything conflicting with national ethics law, e.g. selling data on, re-identifying people, or passing data to parties not in the permit.",
        "keywords": [r"re-?identif", r"sell (the )?data", r"resell", r"data broker", r"pass (the )?data (on )?to (our )?(partners|clients|third)", r"weiterverkauf"],
        "examples": ["Resell the aggregated tables to our clients."],
        "near_misses": [],
    },
}

ALLOWED: dict[str, dict] = {
    "public_interest_public_health": {"article": "53(1)(a)", "public_body_only": True,
                                      "description": "Public interest in public or occupational health, e.g. protection against cross-border threats, surveillance.",
                                      "keywords": [r"public health", r"prevention", r"surveillance", r"health authorit", r"outbreak"]},
    "policy_making_and_regulation": {"article": "53(1)(b)", "public_body_only": True,
                                     "description": "Policy-making and regulatory activities in health and care.",
                                     "keywords": [r"ministry", r"policy", r"regulat", r"quality programme", r"treatment gap", r"guideline"]},
    "official_statistics": {"article": "53(1)(c)", "public_body_only": True,
                            "description": "Official statistics.",
                            "keywords": [r"official statistic", r"statistics office", r"national statistic", r"annual (health )?report"]},
    "education_and_teaching": {"article": "53(1)(d)", "public_body_only": False,
                               "description": "Education or teaching in health or care.",
                               "keywords": [r"teaching", r"education", r"curriculum", r"training module", r"lecture"]},
    "scientific_research": {"article": "53(1)(e)", "public_body_only": False,
                            "description": "Scientific research related to health or care that contributes to public health.",
                            "keywords": [r"research", r"\bstudy\b", r"epidemiolog", r"universit", r"institute", r"cohort study"]},
    "algorithm_training_and_testing": {"article": "53(1)(e)", "public_body_only": False,
                                       "description": "Development, training, testing and validation of algorithms and AI systems (part of scientific research).",
                                       "keywords": [r"\bmodel\b", r"algorithm", r"machine learning", r"\bai\b", r"predict", r"validat"]},
    "improving_healthcare": {"article": "53(1)(f)", "public_body_only": False,
                             "description": "Improving the delivery of care, optimising treatment and provision of healthcare.",
                             "keywords": [r"improv(e|ing) (the )?(care|treatment)", r"optimi[sz]", r"personali[sz]ed"]},
}

PUBLIC_BODY_SIGNALS = [r"ministry", r"ministerium", r"federal", r"national", r"statistics office", r"statistik austria", r"public health",
                       r"health authorit", r"gesundheitsbehörde", r"agency", r"agentur", r"\bages\b", r"government", r"regional health",
                       r"universit", r"university hospital", r"medizinische universität"]
PRIVATE_SIGNALS = [r"\bgmbh\b", r"\bag\b", r"\bltd\b", r"\binc\b", r"company", r"\bs\.?a\.?\b", r"spin-?off", r"\bplc\b", r"\bkg\b", r"\bse\b"]

JUSTIFICATION_PATTERNS = [
    r"aggregates? (are|is) not (enough|sufficient)", r"statistics (are|is|would be) not (enough|sufficient)",
    r"individual[- ]level (data|histor|records)", r"patient[- ]level (data|histor|records)", r"need(s)? individual",
    r"train(ing)? (and validat\w+ )?(a|the|our) model", r"cannot be (answered|done) with (aggregate|statistic)",
    r"aggregierte daten (reichen|genügen) nicht",
]
# purposes for which pseudonymised individual-level access can be justified
SPE_ELIGIBLE = {"scientific_research", "algorithm_training_and_testing", "public_interest_public_health", "improving_healthcare"}
