"""The brain registry — named, swappable model profiles (AERO-BRAIN-301).

v0.2 had a two-way ``brain`` string: ``local`` (gemma4 via Ollama) or ``cloud``
(one OpenAI-compatible endpoint). v0.3 "Open Aero" widens that seam: *any* brain
is just a named **profile**, and switching Aero's mind is picking a profile — a
Control-App click later, a CLI flag today, never a code change.

A profile is provider-agnostic on purpose (Rule 8 — "the core is provider-agnostic;
no vendor name appears anywhere except behind an adapter"). Two adapters cover the
whole world:

  * ``ollama``  -> local models via ``OllamaCognition`` (private, offline default)
  * ``openai``  -> anything speaking the OpenAI ``/chat/completions`` API via
                   ``CloudCognition``: hosted providers (Groq, OpenAI, OpenRouter,
                   Gemini), *and* a local LiteLLM proxy that fans out to ~100 more.

Personality lives in the vault + persona prompt, never the weights (AERO-ID-002),
so swapping the profile changes only *how smart / fast / expensive / private* Aero
is — never *who* he is.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

from aero.cognition.service import CognitionService

# Cost tiers are informational — they drive the router's privacy/cost policy
# (AERO-BRAIN-303) and the Control App's cost meter, not behaviour here.
CostTier = str  # "free-local" | "free-cloud" | "paid" | "proxy"


@dataclass(frozen=True)
class BrainProfile:
    """One selectable brain. ``id`` is the stable handle the user references."""

    id: str
    adapter: str                     # "ollama" | "openai"
    model: str
    base_url: str = ""               # openai adapter: endpoint or a CloudCognition alias
    key_env: str | None = None       # env var holding the API key (None = keyless/local)
    cost_tier: CostTier = "paid"
    supports_vision: bool = False
    label: str = ""                  # human-friendly one-liner for `aero brain`

    @property
    def is_local(self) -> bool:
        """True if this brain runs on-device (Ollama, or an OpenAI adapter aimed
        at localhost). A *local* brain keeps the turn private; note a LiteLLM
        proxy is local-hosted but forwards to the cloud, so it is NOT private —
        see :attr:`is_private`."""
        if self.adapter == "ollama":
            return True
        return any(h in self.base_url for h in ("localhost", "127.0.0.1", "0.0.0.0"))

    @property
    def is_private(self) -> bool:
        """True only if the prompt never leaves the device. Ollama qualifies; a
        local proxy does not (it relays to a remote provider)."""
        return self.adapter == "ollama"


# -- Built-in profiles -----------------------------------------------------
# Ordered by "how much we do for the user": local needs nothing; the cloud
# presets need a key; litellm needs a running proxy. base_url for the openai
# adapter accepts a CloudCognition provider alias (resolved there) or a full URL.
_BUILTINS: tuple[BrainProfile, ...] = (
    BrainProfile(
        id="local", adapter="ollama", model="gemma4:e4b",
        cost_tier="free-local",
        label="gemma4:e4b via Ollama — private, offline, ~5-11s/turn on CPU",
    ),
    BrainProfile(
        id="groq", adapter="openai", model="llama-3.3-70b-versatile",
        base_url="groq", key_env="GROQ_API_KEY", cost_tier="free-cloud",
        label="Groq llama-3.3-70b — free, real-time (prompt leaves device)",
    ),
    BrainProfile(
        id="openai", adapter="openai", model="gpt-4o-mini",
        base_url="openai", key_env="OPENAI_API_KEY", cost_tier="paid",
        supports_vision=True,
        label="OpenAI gpt-4o-mini — paid, fast, vision-capable",
    ),
    BrainProfile(
        id="openrouter", adapter="openai", model="meta-llama/llama-3.3-70b-instruct",
        base_url="openrouter", key_env="OPENROUTER_API_KEY", cost_tier="paid",
        label="OpenRouter — one key, hundreds of models",
    ),
    BrainProfile(
        id="gemini", adapter="openai", model="gemini-2.0-flash",
        base_url="gemini", key_env="GEMINI_API_KEY", cost_tier="free-cloud",
        supports_vision=True,
        label="Google Gemini 2.0 Flash — free tier, vision-capable",
    ),
    BrainProfile(
        # AERO-BRAIN-302: a local LiteLLM proxy is the recommended power path —
        # CloudCognition already speaks OpenAI, so one base URL unlocks ~100
        # providers with zero adapter code. Keyless to Aero (the proxy holds the
        # real keys); local-hosted but forwards to the cloud, so not private.
        id="litellm", adapter="openai", model="gpt-4o-mini",
        base_url="http://localhost:4000", key_env=None, cost_tier="proxy",
        label="LiteLLM proxy (localhost:4000) — ~100 providers behind one seam",
    ),
)

BUILTIN_PROFILES: dict[str, BrainProfile] = {p.id: p for p in _BUILTINS}


def registry(custom: dict[str, dict] | None = None) -> dict[str, BrainProfile]:
    """The full profile registry: built-ins overlaid with the user's custom
    profiles (from settings). A custom entry sharing a built-in id overrides it,
    so a user can, e.g., point ``openai`` at a different model without new code."""
    reg = dict(BUILTIN_PROFILES)
    for pid, data in (custom or {}).items():
        fields = {k: v for k, v in {**data, "id": pid}.items()
                  if k in BrainProfile.__dataclass_fields__}
        base = reg.get(pid)
        reg[pid] = replace(base, **fields) if base else BrainProfile(**fields)
    return reg


def build_from_profile(
    profile: BrainProfile, *, api_key: str | None = None
) -> CognitionService:
    """Instantiate the CognitionService a profile describes.

    ``api_key`` (already resolved by the caller, e.g. from keyring/env) is passed
    to cloud adapters; the ollama adapter ignores it. Imports are lazy so the
    base install stays dependency-free and importing the registry never drags in
    a backend."""
    if profile.adapter == "ollama":
        from aero.cognition.ollama_backend import OllamaCognition
        return OllamaCognition(profile.model)
    if profile.adapter == "openai":
        from aero.cognition.cloud_backend import CloudCognition
        return CloudCognition(
            profile.model,
            base_url=profile.base_url or "openai",
            api_key=api_key,
        )
    raise ValueError(f"unknown brain adapter: {profile.adapter!r}")
