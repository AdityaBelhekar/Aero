"""Brain registry, profile resolution, and key handling — hermetic tests.

No network, no keyring backend required (keyring is mocked/absent).
"""

from __future__ import annotations

from aero.cognition.cloud_backend import CloudCognition
from aero.cognition.keys import resolve_key
from aero.cognition.ollama_backend import OllamaCognition
from aero.cognition.registry import (
    BUILTIN_PROFILES,
    BrainProfile,
    build_from_profile,
    registry,
)
from aero.config import Config


# -- built-ins & registry overlay -----------------------------------------
def test_builtins_present_and_shaped():
    reg = registry()
    for pid in ("local", "groq", "openai", "openrouter", "gemini", "litellm"):
        assert pid in reg
    assert reg["local"].adapter == "ollama"
    assert reg["groq"].adapter == "openai"


def test_local_is_private_cloud_is_not():
    reg = registry()
    assert reg["local"].is_local and reg["local"].is_private
    assert not reg["groq"].is_local and not reg["groq"].is_private
    # LiteLLM proxy: local-hosted but forwards to the cloud -> local, not private
    assert reg["litellm"].is_local and not reg["litellm"].is_private


def test_custom_profile_overrides_builtin():
    reg = registry({"openai": {"model": "gpt-4o"}})
    assert reg["openai"].model == "gpt-4o"          # overridden
    assert reg["openai"].key_env == "OPENAI_API_KEY"  # rest inherited


def test_custom_profile_new_id():
    reg = registry({"mistral": {"adapter": "openai", "model": "mistral-large",
                                "base_url": "https://api.mistral.ai/v1",
                                "key_env": "MISTRAL_API_KEY"}})
    assert reg["mistral"].model == "mistral-large"
    assert reg["mistral"].adapter == "openai"


def test_registry_does_not_mutate_builtins():
    registry({"local": {"model": "something-else"}})
    assert BUILTIN_PROFILES["local"].model == "gemma4:e4b"


# -- build_from_profile ----------------------------------------------------
def test_build_ollama_profile():
    llm = build_from_profile(BUILTIN_PROFILES["local"])
    assert isinstance(llm, OllamaCognition)
    assert llm.model_name == "gemma4:e4b"


def test_build_openai_profile_resolves_alias_and_key():
    llm = build_from_profile(BUILTIN_PROFILES["groq"], api_key="k-123")
    assert isinstance(llm, CloudCognition)
    assert "groq.com" in llm.base_url
    assert llm.api_key == "k-123"


def test_build_unknown_adapter_raises():
    bad = BrainProfile(id="x", adapter="telepathy", model="brainwave")
    try:
        build_from_profile(bad)
    except ValueError as e:
        assert "adapter" in str(e)
    else:
        raise AssertionError("expected ValueError")


# -- key resolution --------------------------------------------------------
def test_resolve_key_local_is_none():
    assert resolve_key(BUILTIN_PROFILES["local"]) is None


def test_resolve_key_from_profile_env(monkeypatch):
    for e in ("AERO_BRAIN_API_KEY", "GROQ_API_KEY", "OPENAI_API_KEY",
              "OPENROUTER_API_KEY", "GEMINI_API_KEY"):
        monkeypatch.delenv(e, raising=False)
    monkeypatch.setattr("aero.cognition.keys._keyring", lambda: None)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-openai")
    assert resolve_key(BUILTIN_PROFILES["openai"]) == "sk-openai"


def test_resolve_key_prefers_keyring(monkeypatch):
    class FakeKeyring:
        def get_password(self, service, name):
            return "kr-secret" if name == "openai" else None
    monkeypatch.setattr("aero.cognition.keys._keyring", lambda: FakeKeyring())
    monkeypatch.setenv("OPENAI_API_KEY", "sk-env")
    assert resolve_key(BUILTIN_PROFILES["openai"]) == "kr-secret"  # keyring wins


# -- settings resolution (legacy back-compat) ------------------------------
def test_resolve_legacy_local(tmp_path):
    from aero import settings as st
    s = st.load(Config(home=tmp_path))
    assert s.brain == "local"
    prof = st.resolve_brain_profile(s)
    assert prof.id == "local" and prof.adapter == "ollama"


def test_resolve_legacy_cloud_maps_to_provider(tmp_path):
    from aero import settings as st
    s = st.load(Config(home=tmp_path))
    s.brain = "cloud"; s.cloud_provider = "groq"; s.cloud_model = "llama-3.3-70b-versatile"
    prof = st.resolve_brain_profile(s)
    assert prof.adapter == "openai"
    assert prof.model == "llama-3.3-70b-versatile"
    assert "groq.com" in build_from_profile(prof, api_key="k").base_url


def test_resolve_force_overrides(tmp_path):
    from aero import settings as st
    s = st.load(Config(home=tmp_path))
    assert st.resolve_brain_profile(s, "gemini").id == "gemini"
    assert st.resolve_brain_profile(s, "local").id == "local"


def test_build_brain_selects_by_profile(tmp_path):
    from aero import settings as st
    cfg = Config(home=tmp_path)
    assert isinstance(st.build_brain(cfg), OllamaCognition)              # default local
    s = st.load(cfg); s.brain_profile = "groq"; st.save(s, cfg)
    assert isinstance(st.build_brain(cfg), CloudCognition)              # persisted profile
    assert isinstance(st.build_brain(cfg, force="local"), OllamaCognition)  # override
