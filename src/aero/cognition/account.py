"""Account login — connect a brain by logging in, not just pasting a key (AERO-BRAIN-305).

The legitimate half of "log in through any AI": for providers that expose a real
token-issuing OAuth flow, Aero runs it and stores the **genuine API key** it hands
back in the OS keyring — same as a pasted key from there on. **OpenRouter** is the
flagship: its OAuth-PKCE flow issues a key that reaches hundreds of models, so
"log in once → any model" works without touching anyone's subscription.

Flow (PKCE):
  1. ``start()``   — make a code_verifier/challenge, return the auth URL to open.
  2. user approves in the browser; the provider redirects to the callback with a code.
  3. ``complete(code, verifier)`` — exchange code+verifier for an API key, store it.

The HTTP exchange is injected (``poster``), so the framework is testable now; the
interactive bits (open the browser, catch the callback) are the Control-App /
CLI's job. Key-auth and local providers get honest instructions instead of a flow.

NOT here: any path that drives a consumer ChatGPT/Claude subscription via a
scraped web session — that violates those providers' ToS.
"""

from __future__ import annotations

import base64
import hashlib
import json
import secrets
import urllib.parse
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass

from aero.cognition import keys
from aero.cognition.providers import provider

# poster(url, json_body) -> parsed response dict.
Poster = Callable[[str, dict], dict]

DEFAULT_CALLBACK = "http://localhost:8385/callback"


def _b64url(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _challenge(verifier: str) -> str:
    return _b64url(hashlib.sha256(verifier.encode("ascii")).digest())


def new_pkce() -> tuple[str, str]:
    """(code_verifier, code_challenge) for an OAuth-PKCE login."""
    verifier = _b64url(secrets.token_bytes(32))
    return verifier, _challenge(verifier)


@dataclass
class LoginStart:
    provider: str
    method: str            # "pkce" | "key" | "none"
    url: str = ""          # browser URL (authorize, or the signup page)
    verifier: str = ""     # PKCE verifier to hold until complete()
    instructions: str = ""

    def to_dict(self) -> dict:
        return {"provider": self.provider, "method": self.method, "url": self.url,
                "instructions": self.instructions,
                "verifier": self.verifier or None}


class LoginError(Exception):
    pass


def _default_post(url: str, body: dict) -> dict:
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(url, data=data,
                                 headers={"Content-Type": "application/json"},
                                 method="POST")
    with urllib.request.urlopen(req, timeout=15.0) as resp:
        return json.loads(resp.read().decode("utf-8"))


class AccountLogin:
    def __init__(self, provider_id: str, *, poster: Poster | None = None):
        self.pid = provider_id
        self._post = poster or _default_post

    def start(self, *, callback_url: str = DEFAULT_CALLBACK,
              verifier: str | None = None) -> LoginStart:
        p = provider(self.pid)
        if p is None:
            raise LoginError(f"unknown provider: {self.pid}")

        if p.auth == "oauth":
            if verifier:
                v, chal = verifier, _challenge(verifier)
            else:
                v, chal = new_pkce()
            q = urllib.parse.urlencode({
                "callback_url": callback_url,
                "code_challenge": chal,
                "code_challenge_method": "S256",
            })
            return LoginStart(
                self.pid, "pkce", url=f"{p.oauth['auth_url']}?{q}", verifier=v,
                instructions="open the URL, approve, and Aero will capture the "
                             "returned code to finish login")
        if p.auth == "key":
            return LoginStart(
                self.pid, "key", url=p.signup_url,
                instructions=f"get a key from the URL, then: "
                             f"aero brain --set-key {self.pid} <key>")
        return LoginStart(self.pid, "none",
                          instructions="local provider — no login needed")

    def complete(self, code: str, verifier: str) -> dict:
        """Exchange the callback code for an API key and store it in the keyring."""
        p = provider(self.pid)
        if p is None or p.auth != "oauth":
            raise LoginError(f"{self.pid} does not use OAuth login")
        resp = self._post(p.oauth["token_url"],
                          {"code": code, "code_verifier": verifier,
                           "code_challenge_method": "S256"})
        key = resp.get("key") or resp.get("api_key")
        if not key:
            return {"ok": False, "error": "provider returned no key"}
        stored = keys.set_key(self.pid, key)
        return {"ok": True, "provider": self.pid, "stored_in_keyring": stored,
                "key_preview": key[:6] + "…" if len(key) > 6 else "set",
                "hint": None if stored else
                "no keyring backend — set an env var instead"}
