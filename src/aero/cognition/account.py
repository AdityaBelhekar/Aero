"""Account login — connect a brain by signing in, not just pasting a key (AERO-BRAIN-305).

The legitimate half of "log in through any AI": for providers with a real
token-issuing OAuth flow, Aero runs it and stores the genuine API token it hands
back in the OS keyring — same as a pasted key thereafter. Three real flows are
supported so users get actual choice of "sign in with X":

  * ``pkce``     — app-less (OpenRouter). No client_id to register. Browser →
                   callback code → exchange for an API key.
  * ``authcode`` — standard OAuth2 + PKCE (Hugging Face). Needs a registered app's
                   client_id. Browser → callback code → exchange.
  * ``device``   — device flow (GitHub Models). No callback server: the user types
                   a short code at a URL and Aero polls for the token.

Client IDs (not secret) live in ``settings.oauth_client_ids``. Every HTTP call is
injected, so the flows are tested without the network; the interactive glue (open
browser / poll) is thin.

NOT here: driving a consumer ChatGPT/Claude subscription via a scraped web
session — that violates those providers' ToS.
"""

from __future__ import annotations

import base64
import hashlib
import json
import secrets
import time
import urllib.parse
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass

from aero import settings as st
from aero.cognition import keys
from aero.cognition.providers import provider
from aero.config import Config

# poster(url, json_body, headers?) -> parsed response dict.
Poster = Callable[..., dict]

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
    method: str            # "pkce" | "authcode" | "device" | "key" | "none"
    url: str = ""          # browser URL (authorize / verification / signup)
    verifier: str = ""     # PKCE verifier to hold until complete()
    instructions: str = ""
    # device flow only:
    user_code: str = ""    # the short code the user types
    device_code: str = ""  # opaque handle Aero polls with
    interval: int = 5      # seconds between polls
    error: str = ""        # set when the flow can't start (e.g. missing client_id)

    def to_dict(self) -> dict:
        return {"provider": self.provider, "method": self.method, "url": self.url,
                "instructions": self.instructions, "verifier": self.verifier or None,
                "user_code": self.user_code or None,
                "device_code": self.device_code or None,
                "interval": self.interval, "error": self.error or None}


class LoginError(Exception):
    pass


def _default_post(url: str, body: dict, headers: dict | None = None) -> dict:
    # OAuth token endpoints usually want form-encoding + Accept: application/json.
    data = urllib.parse.urlencode(body).encode("utf-8")
    hdrs = {"Content-Type": "application/x-www-form-urlencoded",
            "Accept": "application/json", **(headers or {})}
    req = urllib.request.Request(url, data=data, headers=hdrs, method="POST")
    with urllib.request.urlopen(req, timeout=15.0) as resp:
        return json.loads(resp.read().decode("utf-8"))


class AccountLogin:
    def __init__(self, provider_id: str, *, cfg: Config | None = None,
                 settings=None, poster: Poster | None = None):
        self.pid = provider_id
        self.cfg = cfg or Config.load()
        self._settings = settings
        self._post = poster or _default_post

    def _client_id(self) -> str | None:
        s = self._settings if self._settings is not None else st.load(self.cfg)
        return (s.oauth_client_ids or {}).get(self.pid)

    # -- start -------------------------------------------------------------
    def start(self, *, callback_url: str = DEFAULT_CALLBACK,
              verifier: str | None = None) -> LoginStart:
        p = provider(self.pid)
        if p is None:
            raise LoginError(f"unknown provider: {self.pid}")

        if p.auth == "key":
            return LoginStart(self.pid, "key", url=p.signup_url,
                              instructions=f"get a key, then: aero brain --set-key "
                                           f"{self.pid} <key>")
        if p.auth == "none":
            return LoginStart(self.pid, "none",
                              instructions="local provider — no login needed")

        flow = p.oauth.get("flow", "pkce")
        if p.oauth.get("needs_client_id") and not self._client_id():
            return LoginStart(self.pid, flow,
                              error=f"{self.pid} login needs a registered app. "
                                    f"Create one ({p.signup_url}) and set its id: "
                                    f"aero brain --oauth-client {self.pid} <client_id>")

        if flow == "device":
            return self._start_device(p)
        return self._start_browser(p, flow, callback_url, verifier)

    def _start_browser(self, p, flow, callback_url, verifier) -> LoginStart:
        v, chal = (verifier, _challenge(verifier)) if verifier else new_pkce()
        params = {"callback_url": callback_url, "code_challenge": chal,
                  "code_challenge_method": "S256"}
        if flow == "authcode":  # standard OAuth2 params
            params = {"response_type": "code", "client_id": self._client_id(),
                      "redirect_uri": callback_url, "scope": p.oauth.get("scope", ""),
                      "code_challenge": chal, "code_challenge_method": "S256"}
        url = f"{p.oauth['auth_url']}?{urllib.parse.urlencode(params)}"
        return LoginStart(self.pid, flow, url=url, verifier=v,
                          instructions="open the URL, approve, and Aero captures "
                                       "the returned code to finish login")

    def _start_device(self, p) -> LoginStart:
        resp = self._post(p.oauth["device_url"],
                          {"client_id": self._client_id(),
                           "scope": p.oauth.get("scope", "")})
        if "device_code" not in resp:
            return LoginStart(self.pid, "device",
                              error=f"device login failed to start: {resp}")
        return LoginStart(
            self.pid, "device",
            url=resp.get("verification_uri", ""),
            user_code=resp.get("user_code", ""),
            device_code=resp["device_code"],
            interval=int(resp.get("interval", 5)),
            instructions=f"go to {resp.get('verification_uri')} and enter "
                         f"{resp.get('user_code')}")

    # -- complete ----------------------------------------------------------
    def complete(self, code: str, verifier: str) -> dict:
        """Exchange a callback code (pkce/authcode) for a token and store it."""
        p = provider(self.pid)
        if p is None or p.auth != "oauth":
            raise LoginError(f"{self.pid} does not use OAuth login")
        flow = p.oauth.get("flow", "pkce")
        body: dict = {"code": code, "code_verifier": verifier,
                      "code_challenge_method": "S256"}
        if flow == "authcode":
            body.update({"grant_type": "authorization_code",
                         "client_id": self._client_id(),
                         "redirect_uri": DEFAULT_CALLBACK})
        resp = self._post(p.oauth["token_url"], body)
        return self._store_token(resp)

    def poll(self, device_code: str) -> dict:
        """One poll of a device-flow token endpoint. Returns pending/ok/error."""
        p = provider(self.pid)
        resp = self._post(p.oauth["token_url"],
                          {"client_id": self._client_id(), "device_code": device_code,
                           "grant_type": "urn:ietf:params:oauth:grant-type:device_code"})
        if resp.get("error") in ("authorization_pending", "slow_down"):
            return {"ok": False, "pending": True, "error": resp["error"]}
        return self._store_token(resp)

    def _store_token(self, resp: dict) -> dict:
        token = resp.get("key") or resp.get("api_key") or resp.get("access_token")
        if not token:
            return {"ok": False, "error": resp.get("error_description")
                    or resp.get("error") or "provider returned no token"}
        stored = keys.set_key(self.pid, token)
        return {"ok": True, "provider": self.pid, "stored_in_keyring": stored,
                "key_preview": token[:6] + "…" if len(token) > 6 else "set",
                "hint": None if stored else
                "no keyring backend — set an env var instead"}


def interactive_login(provider_id: str, *, cfg: Config | None = None, port: int = 8385,
                      open_browser: bool = True, timeout: float = 300.0) -> dict:
    """Run a full OAuth login from the terminal (best-effort). Handles all three
    flows: pkce/authcode capture the callback on a one-shot localhost server;
    device flow prints a code and polls."""
    import webbrowser

    login = AccountLogin(provider_id, cfg=cfg)
    callback = f"http://localhost:{port}/callback"
    start = login.start(callback_url=callback)
    if start.error:
        return {"ok": False, "error": start.error}
    if start.method not in ("pkce", "authcode", "device"):
        return {"ok": False, "error": f"{provider_id} has no OAuth login",
                "instructions": start.instructions, "url": start.url}

    if start.method == "device":
        print(f"To sign in: open {start.url} and enter code {start.user_code}")
        if open_browser:
            try:
                webbrowser.open(start.url)
            except Exception:
                pass
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            res = login.poll(start.device_code)
            if res.get("ok") or not res.get("pending"):
                return res
            time.sleep(start.interval)
        return {"ok": False, "error": "timed out waiting for device authorization"}

    # pkce / authcode -> capture the callback
    import http.server
    import threading
    captured: dict[str, str] = {}

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802
            from urllib.parse import parse_qs, urlparse
            captured["code"] = (parse_qs(urlparse(self.path).query).get("code")
                                or [""])[0]
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(b"<h2>Aero: login received. You can close this tab.</h2>")

        def log_message(self, *a):
            pass

    server = http.server.HTTPServer(("127.0.0.1", port), Handler)
    server.timeout = timeout
    print(f"Opening {provider_id} login… if the browser doesn't open, visit:\n{start.url}")
    if open_browser:
        try:
            webbrowser.open(start.url)
        except Exception:
            pass
    t = threading.Thread(target=server.handle_request, daemon=True)
    t.start()
    t.join(timeout)
    server.server_close()
    if not captured.get("code"):
        return {"ok": False, "error": "timed out waiting for the login callback"}
    return login.complete(captured["code"], start.verifier)
