"""brain.providers/discover/login_* control ops (AERO-BRAIN-305). Hermetic."""

from __future__ import annotations

from aero.config import Config
from aero.control import ControlService


def test_brain_providers_op(tmp_path):
    r = ControlService(Config(home=tmp_path)).dispatch("brain.providers")
    assert r["ok"]
    by = {p["id"]: p for p in r["result"]["providers"]}
    assert by["local"]["kind"] == "local" and by["local"]["key_set"] is True
    assert by["openrouter"]["auth"] == "oauth" and by["openrouter"]["aggregator"]
    assert by["openai"]["auth"] == "key"


def test_brain_providers_key_state(tmp_path, monkeypatch):
    from aero.cognition import keys
    monkeypatch.setattr(keys, "_keyring", lambda: None)
    for e in ("OPENAI_API_KEY", "GROQ_API_KEY", "AERO_BRAIN_API_KEY",
              "GEMINI_API_KEY", "OPENROUTER_API_KEY"):
        monkeypatch.delenv(e, raising=False)
    by = {p["id"]: p for p in
          ControlService(Config(home=tmp_path)).dispatch("brain.providers")["result"]["providers"]}
    assert by["openai"]["key_set"] is False       # cloud, no key
    assert by["lmstudio"]["key_set"] is True       # local, needs none


def test_brain_discover_op(tmp_path):
    r = ControlService(Config(home=tmp_path)).dispatch("brain.discover")
    assert r["ok"]
    ids = {d["id"] for d in r["result"]["local"]}
    assert {"local", "lmstudio", "vllm"} <= ids


def test_brain_login_start_oauth(tmp_path):
    r = ControlService(Config(home=tmp_path)).dispatch(
        "brain.login_start", {"provider": "openrouter"})
    assert r["ok"] and r["result"]["method"] == "pkce"
    assert "openrouter.ai/auth" in r["result"]["url"]
    assert r["result"]["verifier"]


def test_brain_login_start_key_provider(tmp_path):
    r = ControlService(Config(home=tmp_path)).dispatch(
        "brain.login_start", {"provider": "openai"})
    assert r["result"]["method"] == "key"
    assert "--set-key openai" in r["result"]["instructions"]


def test_brain_login_start_missing_provider(tmp_path):
    r = ControlService(Config(home=tmp_path)).dispatch("brain.login_start", {})
    assert r["ok"] is False and "provider" in r["error"]
