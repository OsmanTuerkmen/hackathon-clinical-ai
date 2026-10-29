"""Builds demo/registry.json: a SIMULATED trust registry with signed credentials.

In production, applicants would log in with ID Austria or an EU Digital
Identity Wallet and present credentials signed by real issuers (business
register, research organisation registry, Austrian Medical Chamber,
e-mandate service). Here every issuer gets a demo Ed25519 key derived from a
fixed seed, so the file is reproducible. One credential is deliberately
forged (D03) to show that the app detects it.

Run: python3 tools/make_registry.py
"""
import hashlib
import json
import os

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives import serialization

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

ISSUERS = {
    "id-austria": ("ID Austria (simulated eID)", "eid"),
    "eudi-it": ("EU Digital Identity Wallet, Italy (simulated)", "eid"),
    "eudi-se": ("EU Digital Identity Wallet, Sweden (simulated)", "eid"),
    "eudi-de": ("EU Digital Identity Wallet, Germany (simulated)", "eid"),
    "firmenbuch": ("Business register / Firmenbuch (simulated)", "organisation"),
    "ror": ("Research Organization Registry (simulated)", "organisation"),
    "gov-at": ("Austrian public-sector directory (simulated)", "organisation"),
    "usp-mandate": ("e-mandate service / elektronische Vollmacht (simulated)", "mandate"),
    "aerztekammer": ("Austrian Medical Chamber / Ärztekammer (simulated)", "profession"),
}


def key_for(issuer):
    seed = hashlib.sha256(f"accessdesk-demo-{issuer}".encode()).digest()
    return Ed25519PrivateKey.from_private_bytes(seed)


def canonical(cred):
    return json.dumps({k: cred[k] for k in ("type", "issuer", "claims")}, sort_keys=True,
                      ensure_ascii=False, separators=(",", ":")).encode()


def sign(cred):
    cred["signature"] = key_for(cred["issuer"]).sign(canonical(cred)).hex()
    return cred


def person(issuer, name, birth, country):
    return sign({"type": "person_identity", "issuer": issuer,
                 "claims": {"name": name, "birth_date": birth, "country": country, "assurance": "high"}})


def org(issuer, name, org_type, reg_id, country):
    return sign({"type": "organisation", "issuer": issuer,
                 "claims": {"name": name, "org_type": org_type, "registry_id": reg_id, "country": country}})


def mandate(name, org_name):
    return sign({"type": "mandate", "issuer": "usp-mandate",
                 "claims": {"person": name, "organisation": org_name, "scope": "submit health data applications"}})


def physician(name, licence):
    return sign({"type": "profession", "issuer": "aerztekammer",
                 "claims": {"name": name, "profession": "physician", "licence_no": licence, "status": "active"}})


def wallet(holder, *creds):
    return {"holder": holder, "credentials": list(creds)}


def build():
    W = []
    W.append(wallet("Dr. Sophie Lechner",
                    person("id-austria", "Sophie Lechner", "1984-05-11", "AT"),
                    org("ror", "Danube Institute for Diabetes Research", "research", "ror:0demo-danube", "AT"),
                    mandate("Sophie Lechner", "Danube Institute for Diabetes Research")))
    W.append(wallet("Markus Gruber",
                    person("id-austria", "Markus Gruber", "1979-02-03", "AT"),
                    org("firmenbuch", "Alpenland Versicherung AG", "insurance", "FN 100001a", "AT"),
                    mandate("Markus Gruber", "Alpenland Versicherung AG")))
    W.append(wallet("Mag. Petra Wimmer",
                    person("id-austria", "Petra Wimmer", "1976-09-20", "AT"),
                    org("gov-at", "Federal Ministry of Health", "public_authority", "gov:bmg", "AT"),
                    mandate("Petra Wimmer", "Federal Ministry of Health")))
    W.append(wallet("Julia Steiner",
                    person("eudi-de", "Julia Steiner", "1990-12-01", "DE"),
                    org("firmenbuch", "Brightline Health Marketing GmbH", "marketing", "HRB 200002", "DE"),
                    mandate("Julia Steiner", "Brightline Health Marketing GmbH")))
    W.append(wallet("Dr. Amir Hadžić",
                    person("id-austria", "Amir Hadžić", "1988-07-14", "AT"),
                    org("firmenbuch", "GlucoSense", "company", "FN 100003b", "AT"),
                    mandate("Amir Hadžić", "GlucoSense")))
    W.append(wallet("Thomas Berger",
                    person("id-austria", "Thomas Berger", "1971-03-30", "AT"),
                    org("firmenbuch", "Berger Logistik GmbH", "employer_hr", "FN 100004c", "AT"),
                    mandate("Thomas Berger", "Berger Logistik GmbH")))
    W.append(wallet("Dr. Lukas Fischer",
                    person("id-austria", "Lukas Fischer", "1982-11-08", "AT"),
                    org("gov-at", "National statistics office", "public_authority", "gov:stat", "AT"),
                    mandate("Lukas Fischer", "National statistics office")))
    W.append(wallet("Prof. Elena Rossi",
                    person("eudi-it", "Elena Rossi", "1969-04-25", "IT"),
                    org("ror", "Comprehensive Cancer Centre", "research", "ror:0demo-ccc", "IT"),
                    mandate("Elena Rossi", "Comprehensive Cancer Centre")))
    W.append(wallet("Dr. Nina Hofbauer",
                    person("id-austria", "Nina Hofbauer", "1985-01-17", "AT"),
                    org("ror", "Institute for General Practice", "research", "ror:0demo-igp", "AT"),
                    mandate("Nina Hofbauer", "Institute for General Practice"),
                    physician("Nina Hofbauer", "ÄK-W-48213")))
    W.append(wallet("Sarah Novak",
                    person("eudi-se", "Sarah Novak", "1993-06-02", "SE"),
                    org("firmenbuch", "Nordic Pouch Company", "harmful_industry", "SE556000-0005", "SE"),
                    mandate("Sarah Novak", "Nordic Pouch Company")))
    # Demo cases
    W.append(wallet("Dr. med. Clara Moser",
                    person("id-austria", "Clara Moser", "1980-08-09", "AT"),
                    org("ror", "Medical University of Graz", "research", "ror:0demo-mug", "AT"),
                    mandate("Clara Moser", "Medical University of Graz"),
                    physician("Clara Moser", "ÄK-ST-30117")))
    W.append(wallet("Dr. Jakob Huber",
                    person("id-austria", "Jakob Huber", "1983-10-12", "AT"),
                    org("ror", "Austrian Institute for Health Services Research", "research", "ror:0demo-aihsr", "AT"),
                    mandate("Jakob Huber", "Austrian Institute for Health Services Research")))
    forged = physician("Max Mustermann", "ÄK-W-00000")
    forged["claims"]["licence_no"] = "ÄK-W-99999"     # changed after signing -> signature no longer valid
    W.append(wallet("Dr. med. Max Mustermann",
                    person("id-austria", "Max Mustermann", "1975-01-01", "AT"),
                    forged))
    W.append(wallet("Dr. Eva Lang",
                    person("id-austria", "Eva Lang", "1981-05-05", "AT"),
                    org("firmenbuch", "VitaPlus Krankenversicherung AG", "insurance", "FN 100005d", "AT"),
                    mandate("Eva Lang", "VitaPlus Krankenversicherung AG")))

    issuers = {}
    for iid, (name, kind) in ISSUERS.items():
        pub = key_for(iid).public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
        issuers[iid] = {"name": name, "kind": kind, "public_key": pub.hex()}
    return {
        "note": "SIMULATION for the hackathon demo. Real deployments use ID Austria / EU Digital Identity Wallet "
                "and credentials from real issuers. One credential (Max Mustermann) is deliberately forged.",
        "issuers": issuers,
        "wallets": W,
    }


if __name__ == "__main__":
    out = os.path.join(ROOT, "demo", "registry.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(build(), f, ensure_ascii=False, indent=1)
    print("wrote", out)
