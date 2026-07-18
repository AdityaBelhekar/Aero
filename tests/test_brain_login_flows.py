"""Generalized OAuth login flows: pkce / authcode / device (AERO-BRAIN-305)."""

from __future__ import annotations

from aero import settings as st
from aero.cognition.account import AccountLogin


def _login(pid, *, client_id=None, poster=None):
    s = st.VoiceSettings(oauth_client_ids={pid: client_id} if client_id else {})
    return AccountLogin(pid, settings=s, poster=poster)


# -- Hugging Face: authcode + client_id ------------------------------------
def test_huggingface_start_needs_client_id():
    s = _login("huggingface").start()
    assert s.error and "client_id" in s.error and "oauth-client huggingface" in s.error


def test_huggingface_start_with_client_id():
    s = _login("huggingface", client_id="hf-app-123").start(verifier="v123")
    assert s.method == "authcode"
    assert s.url.startswith("https://huggingface.co/oauth/authorize?")
    assert "client_id=hf-app-123" in s.url
    assert "response_type=code" in s.url and "code_challenge=" in s.url


def test_huggingface_complete_exchanges(monkeypatch):
    from aero.cognition import keys
    stored = {}
    monkeypatch.setattr(keys, "set_key", lambda p, k: stored.setdefault(p, k) is None)
    seen = {}
    def poster(url, body):
        seen.update(body); seen["url"] = url
        return {"access_token": "hf_realtoken"}
    res = _login("huggingface", client_id="hf-app-123", poster=poster).complete("c", "v")
    assert res["ok"] and stored["huggingface"] == "hf_realtoken"
    assert seen["grant_type"] == "authorization_code"
    assert seen["client_id"] == "hf-app-123"


# -- GitHub: device flow ---------------------------------------------------
def test_github_start_device_returns_user_code():
    def poster(url, body):
        assert "device/code" in url
        return {"device_code": "dev123", "user_code": "WXYZ-1234",
                "verification_uri": "https://github.com/login/device", "interval": 5}
    s = _login("github", client_id="gh-app", poster=poster).start()
    assert s.method == "device"
    assert s.user_code == "WXYZ-1234" and s.device_code == "dev123"
    assert "github.com/login/device" in s.url


def test_github_poll_pending_then_success(monkeypatch):
    from aero.cognition import keys
    stored = {}
    monkeypatch.setattr(keys, "set_key", lambda p, k: stored.setdefault(p, k) is None)
    calls = {"n": 0}
    def poster(url, body):
        calls["n"] += 1
        if calls["n"] == 1:
            return {"error": "authorization_pending"}
        return {"access_token": "gho_token"}
    login = _login("github", client_id="gh-app", poster=poster)
    assert login.poll("dev123") == {"ok": False, "pending": True,
                                    "error": "authorization_pending"}
    res = login.poll("dev123")
    assert res["ok"] and stored["github"] == "gho_token"


def test_device_start_needs_client_id():
    s = _login("github").start()
    assert s.error and "client_id" in s.error


# -- OpenRouter still app-less (no client_id) ------------------------------
def test_openrouter_pkce_needs_no_client_id():
    s = _login("openrouter").start(verifier="v")
    assert s.method == "pkce" and not s.error
    assert "openrouter.ai/auth" in s.url


# -- token endpoint prefers key > access_token -----------------------------
def test_store_prefers_api_key_field():
    from aero.cognition import keys
    stored = {}
    import unittest.mock as m
    with m.patch.object(keys, "set_key", lambda p, k: stored.setdefault(p, k) is None):
        res = _login("openrouter", poster=lambda u, b: {"key": "sk-or-x"}).complete("c", "v")
    assert res["ok"] and stored["openrouter"] == "sk-or-x"
