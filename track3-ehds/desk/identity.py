"""Simulated ID Austria sign-in for applicants (hackathon simulation, fictional test persons only).

The real ID Austria identity provider supports only the OpenID Connect authorization code flow
(idp.id-austria.gv.at, reference environment idp.ref.id-austria.gv.at) and needs a service provider registered in
the IDA-SPR with a client_secret. This module mimics that flow with a local mock identity provider:

    /idp-sim/authorize  -> the user picks a test person and confirms (stands in for the ID Austria app)
    /idp-sim/approve    -> one-time code, redirect back with ?code=...&state=...
    /api/auth/token     -> code exchanged for a desk session (bearer token)

A case stores only the display name, an eIDAS assurance level and a sector-specific pseudonym (modelled on the
Austrian bPK for the health sector); never a real identifier. The decision itself never uses the identity.
"""
from __future__ import annotations

import hashlib
import secrets
import threading
import time
from datetime import datetime, timezone
from urllib.parse import quote

TEST_PERSONS = {
    "lena": {"title": "Dr.", "given_name": "Lena", "family_name": "Gruber", "birthdate": "1984-03-12",
             "role": "Researcher, university"},
    "thomas": {"title": "Mag.", "given_name": "Thomas", "family_name": "Huber", "birthdate": "1979-11-02",
               "role": "Official, public health authority"},
    "sophie": {"title": "", "given_name": "Sophie", "family_name": "Berger", "birthdate": "1992-06-25",
               "role": "Data scientist, health-tech start-up"},
}
CODE_TTL_S = 120
SESSION_TTL_S = 8 * 3600


class IdentityError(ValueError):
    pass


class IdentityProvider:
    def __init__(self):
        self._codes: dict[str, tuple[dict, float]] = {}
        self._sessions: dict[str, tuple[dict, float]] = {}
        self._lock = threading.Lock()

    @staticmethod
    def persons() -> list[dict]:
        return [{"id": pid, "name": _name(p), "role": p["role"]} for pid, p in TEST_PERSONS.items()]

    def approve(self, person_id: str, state: str, redirect_uri: str) -> str:
        """The test person confirmed the sign-in: issue a one-time code and return the redirect target."""
        p = TEST_PERSONS.get(person_id)
        if p is None:
            raise IdentityError("unknown test person")
        if not redirect_uri.startswith("/") or redirect_uri.startswith("//"):
            raise IdentityError("redirect_uri must be a path of this application")  # no open redirects
        if not state or len(state) > 200:
            raise IdentityError("missing state")
        claims = {
            "name": _name(p),
            "given_name": p["given_name"],
            "family_name": p["family_name"],
            "bpk_gh": "GH:" + hashlib.sha256(f"GH|{person_id}|{p['birthdate']}".encode()).hexdigest()[:20],
            "eidas_loa": "high",
            "method": "ID Austria (simulated)",
            "auth_time": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }
        code = secrets.token_urlsafe(24)
        with self._lock:
            self._codes[code] = (claims, time.time() + CODE_TTL_S)
        sep = "&" if "?" in redirect_uri else "?"
        return f"{redirect_uri}{sep}code={quote(code)}&state={quote(state)}"

    def exchange(self, code: str) -> tuple[str, dict]:
        """Token endpoint: each code works once and only for a short time."""
        with self._lock:
            claims, expires = self._codes.pop(code, (None, 0.0))
            if claims is None or expires < time.time():
                raise IdentityError("invalid or expired code")
            token = secrets.token_urlsafe(32)
            self._sessions[token] = (claims, time.time() + SESSION_TTL_S)
        return token, claims

    def session(self, token: str | None) -> dict | None:
        if not token:
            return None
        with self._lock:
            claims, expires = self._sessions.get(token, (None, 0.0))
            if claims is None or expires < time.time():
                self._sessions.pop(token, None)
                return None
            return claims

    def logout(self, token: str | None) -> None:
        with self._lock:
            self._sessions.pop(token or "", None)


def _name(p: dict) -> str:
    return " ".join(x for x in (p["title"], p["given_name"], p["family_name"]) if x)
