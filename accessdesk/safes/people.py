"""Who is really asking? Checks the applicant before data is released.

Art. 67(2)(a) asks for the applicant's identity and professional function and
for the names of everyone who will get access. A title such as "Dr." in the
request proves nothing. The app checks signed credentials instead:

1. Person: eID login (ID Austria / EU Digital Identity Wallet).
2. Organisation: entry in a business or research-organisation register.
3. Mandate: the person may act for that organisation (e-mandate).
4. Role, when claimed: e.g. physician, attested by the Medical Chamber.
5. Plausibility: does the type of organisation fit the stated purpose?

All of this is SIMULATED in the demo with demo/registry.json, but the
signatures are real Ed25519 signatures, so a forged credential fails.
"""
import json
import os
import re
import unicodedata

from . import ed25519

try:
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
    from cryptography.exceptions import InvalidSignature
    HAVE_CRYPTO = True
except BaseException as e:      # missing, or a broken install (pyo3 raises a BaseException)
    if isinstance(e, (KeyboardInterrupt, SystemExit)):
        raise
    HAVE_CRYPTO = False         # the pure-Python check in ed25519.py is used instead

_verified = {}


def check_signature(public_hex, signature_hex, msg):
    key = (public_hex, signature_hex, msg)
    if key not in _verified:
        try:
            pub, sig = bytes.fromhex(public_hex), bytes.fromhex(signature_hex)
        except ValueError:
            return False
        if HAVE_CRYPTO:
            try:
                Ed25519PublicKey.from_public_bytes(pub).verify(sig, msg)
                _verified[key] = True
            except (InvalidSignature, ValueError):
                _verified[key] = False
        else:
            _verified[key] = ed25519.verify(pub, msg, sig)
    return _verified[key]


TITLES = r"\b(dr|med|univ|prof|mag|di|dipl|ing|msc|bsc|mba|phd|ma|ba|priv|doz)\b\.?"


def plain_name(name):
    n = unicodedata.normalize("NFKC", name)
    n = re.sub(TITLES, " ", n, flags=re.I)
    return re.sub(r"[\s.,]+", " ", n).strip().lower()


def org_core(org):
    return re.split(r",|\(", org)[0].strip().lower()


def claims_physician(request):
    text = " ".join([request.get("applicant", {}).get("name", ""), request.get("purpose", "")]).lower()
    return bool(re.search(r"dr\.?\s*med\b|\bas a (gp|physician|doctor)\b|\bmy patients?\b|\bgeneral practitioner\b", text))


class Registry:
    def __init__(self, path):
        self.path = path
        with open(path, encoding="utf-8") as f:
            self.data = json.load(f)
        self.issuers = self.data["issuers"]
        self.wallets = {plain_name(w["holder"]): w for w in self.data["wallets"]}

    def verify(self, cred):
        issuer = self.issuers.get(cred.get("issuer"))
        if not issuer:
            return False, "unknown issuer"
        msg = json.dumps({k: cred[k] for k in ("type", "issuer", "claims")}, sort_keys=True,
                         ensure_ascii=False, separators=(",", ":")).encode()
        if check_signature(issuer["public_key"], cred.get("signature", ""), msg):
            return True, f"valid signature by {issuer['name']}"
        return False, f"INVALID signature: claims were changed after {issuer['name']} signed them"

    def holders(self):
        return [w["holder"] for w in self.data["wallets"]]

    def check(self, request, features, login=None):
        """login=None: the applicant logged in with the eID named in the
        request (pre-registered demo requests). login="": nobody logged in.
        login="<name>": that person logged in."""
        app = request.get("applicant", {})
        name, org = app.get("name", ""), app.get("organisation", "")
        if login is None:
            wallet = self.wallets.get(plain_name(name))
        else:
            wallet = self.wallets.get(plain_name(login)) if login else None
        checks = []
        creds = wallet["credentials"] if wallet else []

        def find(kind):
            return [c for c in creds if c["type"] == kind]

        # 1 person
        pid = find("person_identity")
        if pid:
            ok, msg = self.verify(pid[0])
            match = plain_name(pid[0]["claims"]["name"]) == plain_name(name)
            checks.append({"id": "person", "ok": bool(ok and match), "issuer": self.issuers[pid[0]["issuer"]]["name"],
                           "detail_en": f"{pid[0]['claims']['name']}, {msg}" + ("" if match else " (name does not match the request)"),
                           "detail_de": f"{pid[0]['claims']['name']}, " + _de(msg) + ("" if match else " (Name passt nicht zum Antrag)")})
        else:
            checks.append({"id": "person", "ok": False, "issuer": None,
                           "detail_en": "No eID login for this applicant", "detail_de": "Keine eID-Anmeldung für diese Person"})
        # 2 organisation
        oc = find("organisation")
        org_claims = None
        if oc:
            ok, msg = self.verify(oc[0])
            org_claims = oc[0]["claims"]
            match = org_core(org_claims["name"]) in org.lower() or org_core(org) in org_claims["name"].lower()
            checks.append({"id": "organisation", "ok": bool(ok and match), "issuer": self.issuers[oc[0]["issuer"]]["name"],
                           "detail_en": f"{org_claims['name']} ({org_claims['registry_id']}), {msg}",
                           "detail_de": f"{org_claims['name']} ({org_claims['registry_id']}), " + _de(msg)})
        else:
            checks.append({"id": "organisation", "ok": False, "issuer": None,
                           "detail_en": "Organisation not found in a register", "detail_de": "Organisation in keinem Register gefunden"})
        # 3 mandate
        md = find("mandate")
        if md:
            ok, msg = self.verify(md[0])
            checks.append({"id": "mandate", "ok": bool(ok), "issuer": self.issuers[md[0]["issuer"]]["name"],
                           "detail_en": f"May act for {md[0]['claims']['organisation']}, {msg}",
                           "detail_de": f"Darf für {md[0]['claims']['organisation']} handeln, " + _de(msg)})
        else:
            checks.append({"id": "mandate", "ok": False, "issuer": None,
                           "detail_en": "No mandate to act for the organisation", "detail_de": "Keine Vollmacht für die Organisation"})
        # 4 role
        prof = find("profession")
        wants_physician = claims_physician(request)
        if prof:
            ok, msg = self.verify(prof[0])
            checks.append({"id": "role", "ok": bool(ok), "issuer": self.issuers[prof[0]["issuer"]]["name"],
                           "detail_en": f"Physician, licence {prof[0]['claims']['licence_no']}: {msg}",
                           "detail_de": f"Ärztin/Arzt, Nr. {prof[0]['claims']['licence_no']}: " + _de(msg)})
        elif wants_physician:
            checks.append({"id": "role", "ok": False, "issuer": None,
                           "detail_en": "Claims to be a physician, but no Medical Chamber credential",
                           "detail_de": "Gibt an, Ärztin/Arzt zu sein, aber kein Nachweis der Ärztekammer"})
        elif re.search(r"\bdr\b", name, re.I):
            checks.append({"id": "role", "ok": True, "issuer": None, "info": True,
                           "detail_en": "Title “Dr.” is an academic degree here; this purpose needs no medical licence",
                           "detail_de": "„Dr.“ ist hier ein akademischer Grad; für diesen Zweck ist keine ärztliche Zulassung nötig"})

        # 5 plausibility: does the organisation fit the purpose?
        from .projects import ORG_LABELS, SUSPICIOUS_ORGS
        otype = (org_claims or {}).get("org_type") or features.get("org_type", "unknown")
        flags = []
        if otype in SUSPICIOUS_ORGS and not features["prohibited"]:
            flags.append({"id": "org_purpose",
                          "en": f"{ORG_LABELS[otype][0]} asks for health data with a harmless-sounding purpose. "
                                "Art. 54 forbids using the results for premiums, marketing or decisions about people: "
                                "staff should review and require a signed declaration.",
                          "de": f"{ORG_LABELS[otype][1]} fragt Gesundheitsdaten mit unverdächtig klingendem Zweck an. "
                                "Art. 54 verbietet die Nutzung für Prämien, Werbung oder Entscheidungen über Personen: "
                                "Behörde soll prüfen und eine unterschriebene Erklärung verlangen."})
        if features["reidentification"]:
            flags.append({"id": "reidentification",
                          "en": "The request wants to link data to named people (re-identification, Art. 61(3)).",
                          "de": "Der Antrag will Daten mit namentlich bekannten Personen verknüpfen (Re-Identifizierung, Art. 61(3))."})
        allowed = {purpose["category"] for purpose in features["allowed"]}
        if allowed and allowed <= {"public_health", "policy", "statistics"} and otype != "public_authority":
            flags.append({
                "id": "art53_2_reserved",
                "de": (
                    "Zwecke nach Art. 53 Abs. 1 lit. a–c sind öffentlichen Stellen vorbehalten "
                    "(Art. 53 Abs. 2). Die Behörde soll prüfen, ob der Antrag in deren Auftrag erfolgt."
                ),
                "en": (
                    "Purposes under Art. 53(1)(a)–(c) are reserved for public sector bodies "
                    "(Art. 53(2)). Staff should check whether the applicant acts on behalf of one."
                ),
            })
        if re.search(r"\bmy patients?\b|\bfor (?:the )?treatment of\b", request.get("purpose", ""), re.I):
            flags.append({"id": "primary_use",
                          "en": "Data about one's own patients for treatment is primary use (ELGA), not EHDS secondary use.",
                          "de": "Daten eigener Patient:innen für die Behandlung sind Primärnutzung (ELGA), keine EHDS-Sekundärnutzung."})

        core = [c for c in checks if c["id"] in ("person", "organisation", "mandate")]
        role = [c for c in checks if c["id"] == "role" and not c.get("info")]
        if all(c["ok"] for c in core) and all(c["ok"] for c in role):
            status = "verified"
        elif any("INVALID" in c["detail_en"] for c in checks):
            status = "failed"
        else:
            status = "unverified"
        return {"status": status, "checks": checks, "flags": flags, "org_type": otype,
                "org_type_label": ORG_LABELS.get(otype, ORG_LABELS["unknown"]),
                "persons_with_access": [name] + list(request.get("team", [])),
                "simulated": True}


def _de(msg):
    return (msg.replace("valid signature by", "gültige Signatur von")
               .replace("INVALID signature: claims were changed after", "UNGÜLTIGE Signatur: Angaben wurden nachträglich verändert, signiert von")
               .replace("signed them", "")
               .replace("signature not checked (install 'cryptography')", "Signatur nicht geprüft (Paket 'cryptography' fehlt)")
               .replace("unknown issuer", "unbekannter Aussteller"))
