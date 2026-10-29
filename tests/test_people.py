import copy
import json
from pathlib import Path

from accessdesk.safes import ed25519
from accessdesk.safes.people import Registry, plain_name
from accessdesk.safes.projects import analyze


def test_valid_forged_and_tampered_credentials():
    registry = Registry(str(Path(__file__).resolve().parents[1] / "demo" / "registry.json"))
    good = registry.wallets[plain_name("Dr. Nina Hofbauer")]["credentials"][-1]
    forged = registry.wallets[plain_name("Dr. med. Max Mustermann")]["credentials"][-1]
    assert registry.verify(good)[0]
    assert not registry.verify(forged)[0]
    tampered = copy.deepcopy(good)
    tampered["claims"]["name"] = "Someone Else"
    assert not registry.verify(tampered)[0]


def test_pure_python_signature_verification_matches_registry_signatures():
    registry = Registry(str(Path(__file__).resolve().parents[1] / "demo" / "registry.json"))
    for wallet in registry.data["wallets"]:
        for credential in wallet["credentials"]:
            public_key = bytes.fromhex(registry.issuers[credential["issuer"]]["public_key"])
            message = json.dumps(
                {key: credential[key] for key in ("type", "issuer", "claims")},
                sort_keys=True, ensure_ascii=False, separators=(",", ":"),
            ).encode()
            expected = (
                wallet["holder"] != "Dr. med. Max Mustermann"
                or credential["type"] != "profession"
            )
            assert ed25519.verify(
                public_key, message, bytes.fromhex(credential["signature"])
            ) is expected


def test_art53_public_sector_purposes_flag_non_public_applicants():
    registry = Registry(str(Path(__file__).resolve().parents[1] / "demo" / "registry.json"))
    request = {
        "applicant": {"name": "Alex Researcher", "organisation": "Independent Health Lab"},
        "purpose": "We evaluate a public health vaccination programme.",
        "question": "How many people received vaccination?",
    }
    features = analyze(request)

    result = registry.check(request, features)

    flag = next(flag for flag in result["flags"] if flag["id"] == "art53_2_reserved")
    assert flag["de"] == (
        "Zwecke nach Art. 53 Abs. 1 lit. a–c sind öffentlichen Stellen vorbehalten "
        "(Art. 53 Abs. 2). Die Behörde soll prüfen, ob der Antrag in deren Auftrag erfolgt."
    )
    assert flag["en"] == (
        "Purposes under Art. 53(1)(a)–(c) are reserved for public sector bodies "
        "(Art. 53(2)). Staff should check whether the applicant acts on behalf of one."
    )


def test_art53_public_sector_purposes_do_not_flag_public_authorities():
    registry = Registry(str(Path(__file__).resolve().parents[1] / "demo" / "registry.json"))
    request = {
        "applicant": {"name": "Alex Official", "organisation": "Ministry of Health"},
        "purpose": "We evaluate a public health vaccination programme.",
        "question": "How many people received vaccination?",
    }

    result = registry.check(request, analyze(request))

    assert "art53_2_reserved" not in {flag["id"] for flag in result["flags"]}
