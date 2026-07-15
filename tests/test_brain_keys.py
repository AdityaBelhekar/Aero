"""Keyring-backed key vault (AERO-BRAIN-304). Hermetic — keyring is faked.

Covers the store/delete paths and graceful degradation when no keyring backend
is installed (env-only fallback).
"""

from __future__ import annotations

from aero.cognition import keys
from aero.cognition.registry import BUILTIN_PROFILES


class FakeKeyring:
    """In-memory stand-in for the ``keyring`` module."""

    def __init__(self):
        self.store: dict[tuple[str, str], str] = {}

    def get_password(self, service, name):
        return self.store.get((service, name))

    def set_password(self, service, name, value):
        self.store[(service, name)] = value

    def delete_password(self, service, name):
        if (service, name) in self.store:
            del self.store[(service, name)]
        else:
            raise KeyError("not found")


def test_available_reflects_backend(monkeypatch):
    monkeypatch.setattr(keys, "_keyring", lambda: None)
    assert keys.keyring_available() is False
    monkeypatch.setattr(keys, "_keyring", lambda: FakeKeyring())
    assert keys.keyring_available() is True


def test_set_and_resolve_roundtrip(monkeypatch):
    fake = FakeKeyring()
    monkeypatch.setattr(keys, "_keyring", lambda: fake)
    assert keys.set_key("openai", "sk-stored") is True
    assert keys.resolve_key(BUILTIN_PROFILES["openai"]) == "sk-stored"


def test_delete_key(monkeypatch):
    fake = FakeKeyring()
    monkeypatch.setattr(keys, "_keyring", lambda: fake)
    keys.set_key("groq", "gk-1")
    assert keys.resolve_key(BUILTIN_PROFILES["groq"]) == "gk-1"
    assert keys.delete_key("groq") is True
    # gone from keyring; with no env set, resolves to None
    for e in ("AERO_BRAIN_API_KEY", "GROQ_API_KEY", "OPENAI_API_KEY",
              "OPENROUTER_API_KEY", "GEMINI_API_KEY"):
        monkeypatch.delenv(e, raising=False)
    assert keys.resolve_key(BUILTIN_PROFILES["groq"]) is None


def test_set_key_without_backend_returns_false(monkeypatch):
    monkeypatch.setattr(keys, "_keyring", lambda: None)
    assert keys.set_key("openai", "x") is False
    assert keys.delete_key("openai") is False


def test_env_fallback_when_no_backend(monkeypatch):
    monkeypatch.setattr(keys, "_keyring", lambda: None)
    monkeypatch.setenv("GROQ_API_KEY", "gk-env")
    assert keys.resolve_key(BUILTIN_PROFILES["groq"]) == "gk-env"


def test_broken_backend_degrades_to_env(monkeypatch):
    class BrokenKeyring:
        def get_password(self, *a):
            raise RuntimeError("no secret service running")
    monkeypatch.setattr(keys, "_keyring", lambda: BrokenKeyring())
    monkeypatch.setenv("OPENAI_API_KEY", "sk-env")
    # keyring raises -> fall through to env, don't crash
    assert keys.resolve_key(BUILTIN_PROFILES["openai"]) == "sk-env"
