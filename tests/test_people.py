import copy
import json
from pathlib import Path

from accessdesk.safes import ed25519
from accessdesk.safes.people import Registry, plain_name


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
