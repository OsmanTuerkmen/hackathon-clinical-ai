"""Article catalogue of Regulation (EU) 2025/327 (EHDS), Chapter IV, as far as the access desk uses it.

Data only: short English summaries in our own words (see docs/LAW.md; the regulation text is authoritative).
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Article:
    number: str
    title: str
    summary: str


ARTICLES: dict[str, Article] = {
    a.number: a
    for a in (
        Article(
            "53",
            "Permitted purposes of secondary use",
            "Health data may only be made available for listed purposes: public health and safety of care, "
            "policy-making and regulation, official statistics, teaching, scientific research (including "
            "developing and testing products or algorithms), and improving care or optimising treatment.",
        ),
        Article(
            "54",
            "Prohibited secondary use",
            "Health data must not be used for decisions that harm individuals or groups, for decisions on jobs, "
            "insurance, credit or other terms, for advertising or marketing, for developing products that can "
            "harm people or society (e.g. illegal drugs, alcohol, tobacco and nicotine products, weapons), or "
            "for activities that breach national ethics rules.",
        ),
        Article(
            "66",
            "Data minimisation and purpose limitation",
            "Only data that is adequate, relevant and limited to what the purpose needs may be provided. If "
            "anonymised data is enough, anonymised data is provided; pseudonymised data only if the applicant "
            "has shown that anonymised data is not sufficient.",
        ),
        Article(
            "67",
            "Health data access application",
            "An applicant states who they are, the purpose, how the data will be used, which data is needed, "
            "whether anonymised or pseudonymised data is required (with a reason why anonymised data is not "
            "enough), the safeguards and the duration of access.",
        ),
        Article(
            "68",
            "Data permit",
            "The access body checks the purpose, necessity and proportionality, the justification for "
            "pseudonymised data and the safeguards. If the conditions are met it issues a data permit; if only "
            "an anonymised statistical answer is justified, it may provide statistics instead (Art. 69).",
        ),
        Article(
            "69",
            "Health data request",
            "On request for a permitted purpose, the answer is given only as anonymised statistics; the "
            "applicant gets no access to the underlying data.",
        ),
        Article(
            "71",
            "Right to opt out",
            "People can object to secondary use of their data at any time without giving a reason. Their data "
            "is not provided for permits or requests granted after the objection.",
        ),
        Article(
            "73",
            "Secure processing environment",
            "Data under a data permit is accessed only inside a secure processing environment: named users "
            "only, protection against unauthorised reading, copying or removal, and logged access kept for at "
            "least one year. Only non-personal data such as anonymised statistics may be downloaded, after "
            "review.",
        ),
    )
}

# Art. 53(1): permitted purposes (used for the justification of an approval).
ART53_POINTS: dict[str, str] = {
    "53(1)(a)": "public health, prevention, surveillance, or the quality and safety of care",
    "53(1)(b)": "policy-making and regulation by public bodies in the health sector",
    "53(1)(c)": "official statistics on health and care",
    "53(1)(d)": "teaching and training of health professionals",
    "53(1)(e)": "scientific research, including developing and testing products, services or algorithms",
    "53(1)(f)": "improving care and optimising treatment",
}

# Art. 54: prohibited uses (used to explain a rejection).
ART54_POINTS: dict[str, str] = {
    "54(a)": "decisions with legal, social or economic effects to the disadvantage of individuals or groups "
    "(for example by matching or re-identifying people)",
    "54(b)": "decisions on jobs, contracts, insurance or credit, or on the terms, premiums or conditions of goods "
    "and services",
    "54(c)": "advertising or marketing",
    "54(d)": "developing or marketing products that can harm people or society, such as tobacco and nicotine "
    "products, alcohol, gambling, weapons or illicit drugs",
    "54(e)": "activities that breach national ethics rules",
}
