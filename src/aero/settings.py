"""User-tunable settings (voice engine + chosen voice), persisted as JSON.

Kept separate from the memory vault: these are preferences, not memories, and the
user edits them directly. Stored at ``AERO_HOME/settings.json``.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

from aero.config import Config


@dataclass
class VoiceSettings:
    engine: str = "sapi"          # 'sapi' | 'svara' | 'parler' | 'kokoro'
    svara_voice: str = "hi_male"  # which of Svara's 38 profiles
    svara_base_url: str = "http://localhost:8080/v1"
    kokoro_voice: str = "am_michael"  # Kokoro voice (fast natural English)
    stt_model: str = "small"      # Whisper size ("small"...) or "indic" (IndicConformer)
    # Brain tier: 'local' (gemma4:e4b, private, ~5-11s/turn on CPU) or 'cloud'
    # (OpenAI-compatible online brain, sub-second — but the prompt leaves the
    # device). Local is the privacy-first default. API key comes from the
    # environment (see cloud_backend.API_KEY_ENVS), never persisted here.
    #
    # v0.3 "Open Aero" (AERO-BRAIN-301) generalises this into a registry: any
    # named brain profile is selectable. The legacy ``brain``/``cloud_*`` fields
    # below still work and are migrated on read — 'cloud' maps to the profile
    # named by ``cloud_provider`` (model overridden by ``cloud_model``).
    brain: str = "local"
    cloud_provider: str = "groq"  # alias in cloud_backend.PROVIDERS, or a full URL
    cloud_model: str = "llama-3.3-70b-versatile"
    # Active brain profile id (registry.py). Empty -> derive from legacy ``brain``.
    brain_profile: str = ""
    # User-defined brain profiles, overlaid on the built-ins (registry.registry).
    # Maps profile id -> partial BrainProfile field dict.
    brains: dict = field(default_factory=dict)
    # Two-speed router (AERO-BRAIN-303): the cheap/private brain used for reflex
    # + consolidation tagging, and the strong brain used for chat. Empty ->
    # single-brain mode (both = the active profile).
    reflex_profile: str = ""
    primary_profile: str = ""
    # Privacy guard: refuse a non-private (cloud) primary and keep everything on
    # the local reflex brain. Off by default so an explicitly-chosen cloud brain
    # still works; on = "personal talk never leaves the device".
    brain_private_only: bool = False


def _path(cfg: Config) -> Path:
    return cfg.home / "settings.json"


def load(cfg: Config | None = None) -> VoiceSettings:
    cfg = cfg or Config.load()
    p = _path(cfg)
    if not p.exists():
        return VoiceSettings()
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        return VoiceSettings(**{k: v for k, v in data.items()
                                if k in VoiceSettings().__dict__})
    except (json.JSONDecodeError, TypeError, OSError):
        return VoiceSettings()


def save(settings: VoiceSettings, cfg: Config | None = None) -> None:
    cfg = cfg or Config.load()
    cfg.ensure_dirs()
    _path(cfg).write_text(json.dumps(asdict(settings), indent=2), encoding="utf-8")


def build_tts(cfg: Config | None = None):
    """Construct the TTS backend the user has selected."""
    from aero.voice.tts import SapiTTS

    s = load(cfg)
    if s.engine == "svara":
        from aero.voice.svara_tts import SvaraTTS
        return SvaraTTS(s.svara_voice, base_url=s.svara_base_url)
    if s.engine == "parler":
        from aero.voice.parler_tts import ParlerTTS
        return ParlerTTS()
    if s.engine == "kokoro":
        from aero.voice.kokoro_tts import KokoroTTS
        return KokoroTTS(s.kokoro_voice)
    return SapiTTS()


def build_stt(cfg: Config | None = None, *, model: str | None = None):
    """Construct the selected STT backend. ``model`` overrides the persisted
    choice (used by `aero voice --model ...`)."""
    from aero.perception.indic_stt import build_stt as _build
    s = load(cfg)
    return _build(model or s.stt_model)


def resolve_brain_profile(s: VoiceSettings, which: str | None = None):
    """Resolve the active brain to a concrete ``BrainProfile`` (AERO-BRAIN-301).

    ``which`` (a profile id, or the legacy 'local'/'cloud', or a bare provider
    alias) overrides the persisted selection for one call. Resolution order:

      1. explicit ``which`` if given, else ``s.brain_profile``, else legacy ``s.brain``
      2. legacy 'cloud' -> the profile named by ``s.cloud_provider``, with its
         model overridden by ``s.cloud_model`` (back-compat with v0.2 settings)
      3. a known profile id -> that profile from the registry
      4. anything else -> an ad-hoc OpenAI-adapter profile aimed at ``which`` as
         a base URL (so a raw endpoint still works without pre-registration)
    """
    from aero.cognition.registry import BrainProfile, registry

    reg = registry(s.brains)
    sel = which or s.brain_profile or s.brain or "local"

    if sel == "cloud":  # legacy two-way setting
        from dataclasses import replace
        base = reg.get(s.cloud_provider)
        if base is not None:
            return replace(base, model=s.cloud_model)
        return BrainProfile(id="cloud", adapter="openai",
                            model=s.cloud_model, base_url=s.cloud_provider,
                            key_env="AERO_BRAIN_API_KEY", cost_tier="paid")
    if sel == "local":
        return reg["local"]
    if sel in reg:
        return reg[sel]
    # Unknown id -> treat as a raw OpenAI-compatible base URL.
    return BrainProfile(id=sel, adapter="openai", model=s.cloud_model,
                        base_url=sel, key_env="AERO_BRAIN_API_KEY",
                        cost_tier="paid")


def build_brain(cfg: Config | None = None, *, force: str | None = None):
    """Construct the selected cognition backend from its registry profile.

    'local' -> gemma4 via Ollama (private default); any other profile ->
    OpenAI-compatible brain (cloud provider or local LiteLLM proxy). ``force``
    overrides the persisted choice for one call (e.g. `--brain groq`)."""
    from aero.cognition.keys import resolve_key
    from aero.cognition.registry import build_from_profile

    s = load(cfg)
    profile = resolve_brain_profile(s, force)
    return build_from_profile(profile, api_key=resolve_key(profile))


def build_router(cfg: Config | None = None, *, force: str | None = None):
    """Construct Aero's brain as a two-speed router (AERO-BRAIN-303) when the
    user has configured distinct reflex/primary profiles; otherwise a plain
    single brain (so this is a safe drop-in for build_brain).

    ``force`` pins the *primary* (conversational) brain for one call — reflex
    still handles tagging, so `--brain groq` makes you talk to Groq while
    consolidation stays cheap/local."""
    from aero.cognition.keys import resolve_key
    from aero.cognition.registry import build_from_profile
    from aero.cognition.router import BrainRouter

    s = load(cfg)

    # No two-speed config and no override -> single brain (today's behaviour).
    if not s.reflex_profile and not s.primary_profile and not force:
        return build_brain(cfg)

    reflex_prof = resolve_brain_profile(s, s.reflex_profile or None)
    primary_prof = resolve_brain_profile(s, force or s.primary_profile or None)
    reflex = build_from_profile(reflex_prof, api_key=resolve_key(reflex_prof))
    # Same profile for both roles -> single-brain router (no second backend).
    if primary_prof.id == reflex_prof.id:
        return BrainRouter(reflex, None, private_only=s.brain_private_only)
    primary = build_from_profile(primary_prof, api_key=resolve_key(primary_prof))
    return BrainRouter(
        reflex, primary,
        private_only=s.brain_private_only,
        primary_is_private=primary_prof.is_private,
    )
