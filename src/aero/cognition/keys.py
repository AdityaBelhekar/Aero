"""API-key resolution for brain profiles (AERO-BRAIN-304).

Keys are secrets — they never belong in ``settings.json`` (which the user edits
and syncs) or in the memory vault. Resolution order, most to least secure:

  1. OS keyring (Secret Service / libsecret on Linux, Keychain on macOS,
     Credential Manager on Windows) — used when the optional ``keyring`` package
     is installed. This is the recommended store; ``aero brain --set-key`` writes
     here.
  2. the profile's declared ``key_env`` environment variable
  3. a small set of well-known fallback env vars (back-compat with v0.2)

Keyring is optional: with it absent, Aero degrades to env vars (Rule 9 —
"degrade, never die") and simply tells the user how to install it. This module is
stdlib-only unless keyring is present.
"""

from __future__ import annotations

import os

from aero.cognition.registry import BrainProfile

# Service name under which keys are filed in the OS keyring.
KEYRING_SERVICE = "aero-brain"

# Back-compat fallbacks (v0.2 read these directly). Checked after the profile's
# own key_env so a profile-specific key always wins.
_FALLBACK_ENVS = (
    "AERO_BRAIN_API_KEY", "GROQ_API_KEY", "OPENAI_API_KEY",
    "OPENROUTER_API_KEY", "GEMINI_API_KEY",
)


def _keyring():
    """Return the ``keyring`` module if installed and usable, else None. A broken
    backend (no Secret Service running, etc.) must not crash Aero — we treat it
    as absent and fall through to env vars."""
    try:
        import keyring  # type: ignore
        return keyring
    except Exception:
        return None


def keyring_available() -> bool:
    return _keyring() is not None


def resolve_key(profile: BrainProfile) -> str | None:
    """The API key for ``profile``, or None. Local/keyless brains (Ollama, a
    LiteLLM proxy) legitimately have no key — callers treat None accordingly."""
    if profile.is_local and profile.key_env is None:
        return None  # local Ollama needs no key

    kr = _keyring()
    if kr is not None:
        try:
            val = kr.get_password(KEYRING_SERVICE, profile.id)
            if val:
                return val
        except Exception:
            pass  # unusable backend -> fall through to env

    if profile.key_env:
        val = os.environ.get(profile.key_env)
        if val:
            return val

    for env in _FALLBACK_ENVS:
        val = os.environ.get(env)
        if val:
            return val
    return None


def set_key(profile_id: str, key: str) -> bool:
    """Store a key in the OS keyring under ``profile_id``. Returns False if no
    keyring backend is available (caller should tell the user to install it or
    use an env var)."""
    kr = _keyring()
    if kr is None:
        return False
    try:
        kr.set_password(KEYRING_SERVICE, profile_id, key)
        return True
    except Exception:
        return False


def delete_key(profile_id: str) -> bool:
    """Remove a stored key. Returns True if a key was deleted."""
    kr = _keyring()
    if kr is None:
        return False
    try:
        kr.delete_password(KEYRING_SERVICE, profile_id)
        return True
    except Exception:
        return False
