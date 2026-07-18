"""Local discovery + account/OAuth login framework (AERO-BRAIN-305). Hermetic."""

from __future__ import annotations

from aero.cognition.account import AccountLogin, LoginError, new_pkce
from aero.cognition.discovery import discover_local, running_local


# -- local discovery -------------------------------------------------------
def test_discover_all_local_reported():
    found = discover_local(probe=lambda url: None)   # nothing running
    ids = {d["id"] for d in found}
    assert {"local", "lmstudio", "llamacpp", "jan", "vllm", "localai"} <= ids
    assert all(d["running"] is False for d in found)


def test_discover_marks_running_and_models():
    def probe(url):
        if "1234" in url:  # LM Studio up
            return {"data": [{"id": "qwen2.5-7b"}, {"id": "llama-3.1-8b"}]}
        if "11434" in url:  # Ollama up
            return {"models": [{"name": "gemma4:e4b"}]}
        return None
    found = {d["id"]: d for d in discover_local(probe=probe)}
    assert found["lmstudio"]["running"] and found["lmstudio"]["models"] == \
        ["qwen2.5-7b", "llama-3.1-8b"]
    assert found["local"]["running"] and found["local"]["models"] == ["gemma4:e4b"]
    assert found["vllm"]["running"] is False


def test_running_local_filters():
    def probe(url):
        return {"data": []} if "1337" in url else None  # only Jan
    up = running_local(probe=probe)
    assert [d["id"] for d in up] == ["jan"]


def test_ollama_probes_native_endpoint():
    seen = []
    discover_local(probe=lambda url: seen.append(url) or None)
    assert any("11434/api/tags" in u for u in seen)     # ollama native
    assert any("1234/v1/models" in u for u in seen)     # lmstudio openai-style


# -- pkce ------------------------------------------------------------------
def test_pkce_pair_stable_challenge():
    v, c = new_pkce()
    from aero.cognition.account import _challenge
    assert _challenge(v) == c and v != c


# -- login start -----------------------------------------------------------
def test_start_oauth_provider_builds_auth_url():
    s = AccountLogin("openrouter").start(verifier="fixedverifier123")
    assert s.method == "pkce"
    assert s.url.startswith("https://openrouter.ai/auth?")
    assert "code_challenge=" in s.url and "code_challenge_method=S256" in s.url
    assert s.verifier == "fixedverifier123"


def test_start_key_provider_points_to_signup():
    s = AccountLogin("openai").start()
    assert s.method == "key"
    assert s.url.startswith("https://platform.openai.com")
    assert "--set-key openai" in s.instructions


def test_start_local_provider_needs_no_login():
    s = AccountLogin("lmstudio").start()
    assert s.method == "none"


def test_start_unknown_provider_raises():
    try:
        AccountLogin("nope").start()
    except LoginError:
        pass
    else:
        raise AssertionError("expected LoginError")


# -- login complete (token exchange) ---------------------------------------
def test_complete_exchanges_code_and_stores_key(monkeypatch):
    from aero.cognition import keys

    stored = {}
    def fake_set_key(pid, k):
        stored[pid] = k
        return True
    monkeypatch.setattr(keys, "set_key", fake_set_key)

    posted = {}
    def poster(url, body):
        posted["url"] = url
        posted["body"] = body
        return {"key": "sk-or-realkey123"}

    login = AccountLogin("openrouter", poster=poster)
    res = login.complete("authcode", "verifier123")
    assert res["ok"] and res["stored_in_keyring"] is True
    assert stored["openrouter"] == "sk-or-realkey123"
    assert posted["body"]["code"] == "authcode"
    assert posted["body"]["code_verifier"] == "verifier123"
    assert "openrouter.ai/api/v1/auth/keys" in posted["url"]


def test_complete_no_key_returned():
    login = AccountLogin("openrouter", poster=lambda u, b: {"error": "denied"})
    res = login.complete("code", "v")
    assert res["ok"] is False


def test_complete_on_non_oauth_provider_raises():
    try:
        AccountLogin("openai", poster=lambda u, b: {}).complete("c", "v")
    except LoginError:
        pass
    else:
        raise AssertionError("expected LoginError")
