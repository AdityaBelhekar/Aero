"""Cloud brain (online boost tier) — hermetic tests (HTTP + env mocked)."""

from __future__ import annotations

import pytest

from aero.cognition.cloud_backend import (PROVIDERS, CloudCognition,
                                          resolve_api_key)
from aero.cognition.service import ChatMessage
from aero.config import Config


def test_provider_alias_resolves_to_url():
    c = CloudCognition("m", base_url="groq", api_key="k")
    assert c.base_url == PROVIDERS["groq"]
    # a full URL passes through (trailing slash stripped)
    c2 = CloudCognition("m", base_url="https://x.ai/v1/", api_key="k")
    assert c2.base_url == "https://x.ai/v1"


def test_api_key_from_env(monkeypatch):
    monkeypatch.delenv("AERO_BRAIN_API_KEY", raising=False)
    for e in ("GROQ_API_KEY", "OPENAI_API_KEY", "OPENROUTER_API_KEY", "GEMINI_API_KEY"):
        monkeypatch.delenv(e, raising=False)
    assert resolve_api_key() is None
    monkeypatch.setenv("GROQ_API_KEY", "gk-123")
    assert resolve_api_key() == "gk-123"
    assert resolve_api_key("explicit") == "explicit"  # explicit wins


def _openai_reply(text, pt=10, ct=5):
    return {"choices": [{"message": {"content": text}}],
            "usage": {"prompt_tokens": pt, "completion_tokens": ct}}


def test_chat_parses_openai_shape(monkeypatch):
    c = CloudCognition("llama", base_url="groq", api_key="k")
    captured = {}

    def fake_post(path, payload):
        captured["path"] = path
        captured["payload"] = payload
        return _openai_reply("  yo bhai  ")

    monkeypatch.setattr(c, "_post", fake_post)
    res = c.chat([ChatMessage("user", "sup")], temperature=0.8, max_tokens=120)
    assert res.text == "yo bhai"                      # stripped
    assert captured["path"] == "/chat/completions"
    assert captured["payload"]["max_tokens"] == 120
    assert captured["payload"]["model"] == "llama"
    assert res.stats.completion_tokens == 5


def test_complete_json_parses_and_sets_json_mode(monkeypatch):
    c = CloudCognition("m", base_url="groq", api_key="k")
    seen = {}

    def fake_post(path, payload):
        seen["payload"] = payload
        return _openai_reply('{"ok": true}')

    monkeypatch.setattr(c, "_post", fake_post)
    parsed, res = c.complete_json([ChatMessage("user", "x")])
    assert parsed == {"ok": True}
    assert seen["payload"]["response_format"] == {"type": "json_object"}


def test_complete_json_bad_json_returns_none(monkeypatch):
    c = CloudCognition("m", base_url="groq", api_key="k")
    monkeypatch.setattr(c, "_post", lambda p, pl: _openai_reply("not json"))
    parsed, res = c.complete_json([ChatMessage("user", "x")])
    assert parsed is None and res.text == "not json"


def test_health_check_false_without_key(monkeypatch):
    monkeypatch.delenv("AERO_BRAIN_API_KEY", raising=False)
    for e in ("GROQ_API_KEY", "OPENAI_API_KEY", "OPENROUTER_API_KEY", "GEMINI_API_KEY"):
        monkeypatch.delenv(e, raising=False)
    assert CloudCognition("m", base_url="groq").health_check() is False


# -- settings wiring -------------------------------------------------------
def test_brain_settings_roundtrip(tmp_path):
    from aero import settings as st
    cfg = Config(home=tmp_path)
    s = st.load(cfg)
    assert s.brain == "local"  # privacy-first default
    s.brain = "cloud"; s.cloud_provider = "openai"; s.cloud_model = "gpt-4o-mini"
    st.save(s, cfg)
    r = st.load(cfg)
    assert r.brain == "cloud" and r.cloud_provider == "openai" and r.cloud_model == "gpt-4o-mini"


def test_build_brain_selects(tmp_path, monkeypatch):
    from aero import settings as st
    from aero.cognition.ollama_backend import OllamaCognition
    cfg = Config(home=tmp_path)
    assert isinstance(st.build_brain(cfg), OllamaCognition)          # default local
    s = st.load(cfg); s.brain = "cloud"; st.save(s, cfg)
    assert isinstance(st.build_brain(cfg), CloudCognition)           # persisted cloud
    assert isinstance(st.build_brain(cfg, force="local"), OllamaCognition)  # override
