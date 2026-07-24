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
    # User-defined/overridden voice engine profiles, overlaid on the built-in
    # catalog (voice.catalog.registry). Maps engine id -> partial VoiceProfile.
    voice_engines: dict = field(default_factory=dict)
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
    # Which brain sees images (AERO-VIS-602). Empty -> auto: the active brain if
    # it supports vision, else the first vision-capable profile with a key.
    vision_profile: str = ""
    # OAuth app client IDs per provider (AERO-BRAIN-305). Providers whose login
    # needs a registered app (Hugging Face, GitHub) read their client_id here;
    # OpenRouter's app-less PKCE needs none. Client IDs aren't secret.
    oauth_client_ids: dict = field(default_factory=dict)
    # Privacy guard: refuse a non-private (cloud) primary and keep everything on
    # the local reflex brain. Off by default so an explicitly-chosen cloud brain
    # still works; on = "personal talk never leaves the device".
    brain_private_only: bool = False
    # -- Control App: personality dials (AERO-APP-206) ---------------------
    # How Aero behaves, tuned by the human. Persona *identity* stays fixed in
    # prompts/persona.py (never collapses, AERO-PERS-004); these dial the knobs
    # the PRD says adapt: chattiness, roast intensity, formality, quiet hours,
    # language mix. Stored here (portable) so a model swap can't change them.
    persona: dict = field(default_factory=lambda: dict(DEFAULT_PERSONA_DIALS))
    # -- Control App: capability grants + kill switch (AERO-APP-205) -------
    # Scope -> granted?. Full consent enforcement is M12 (Little Hands); M10
    # stores + surfaces the grants and the global kill switch for the UI.
    permissions: dict = field(default_factory=dict)
    killswitch: bool = False  # True = Aero takes no actions at all (panic off)
    # -- Body / robot profile (AERO-BODY-804) -----------------------------
    # When Aero runs as a physical robot. Keys: enabled(bool), platform(auto|pi),
    # hardware({leds,servos,display_face}). Empty -> desktop (no body).
    robot: dict = field(default_factory=dict)
    # -- Proactivity (M4 / PRD §7) ----------------------------------------
    # The impulse gate's learned state + master switch. Keys:
    #   enabled(bool, default True), threshold_offset(float, feedback-learned
    #   global bump), threshold_offset_by_app({app: float}, per-context bumps).
    # Interruption feedback routes here (AERO-FBK-003); relationship feedback
    # goes to the vault's relationship_state instead. Empty -> defaults.
    proactive: dict = field(default_factory=dict)


# Personality dials with safe, conservative defaults. Numeric dials are 0..1;
# quiet_hours is [start_hour, end_hour) in local time (Aero stays quiet then).
DEFAULT_PERSONA_DIALS: dict = {
    "chattiness": 0.5,      # 0 = only speaks when spoken to, 1 = very talkative
    "roast_level": 0.2,     # starts low; the relationship model earns more
    "formality": 0.3,       # 0 = pure slang, 1 = buttoned-up
    "energy": 0.6,          # baseline response energy
    "language_mix": "auto", # auto | english | hinglish | marathi-mix
    "quiet_hours": [1, 8],  # no proactive speech 1am–8am by default
}

# Capability scopes the Control App can grant/revoke (AERO-APP-205). These are the
# surfaces M12's consent gate will enforce; M10 just records the grant state.
PERMISSION_SCOPES: tuple[str, ...] = (
    "apps",       # launch/close applications
    "files",      # read/organise files in an allowed folder
    "media",      # control media playback
    "browser",    # open URLs / tabs
    "shell",      # run shell commands (high-risk; off by default)
    "games",      # game connectors (Minecraft, etc.)
    "screen",     # screen capture / OCR (Eyes)
    "camera",     # camera (local-only)
    "mcp",        # tools bridged from MCP servers (AERO-ACT-506)
)


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


# -- persona dials + permissions helpers (M10) -----------------------------
def merged_persona(s: VoiceSettings) -> dict:
    """Persona dials with defaults filled in for any missing/newly-added key, so
    old settings files keep working as dials are introduced."""
    return {**DEFAULT_PERSONA_DIALS, **(s.persona or {})}


def is_quiet_hours(s: VoiceSettings, hour: int) -> bool:
    """True if ``hour`` (0–23, local) falls in Aero's quiet window — used later to
    suppress proactive speech (M12+). Handles windows that wrap midnight."""
    qh = merged_persona(s).get("quiet_hours") or [1, 8]
    start, end = int(qh[0]), int(qh[1])
    if start == end:
        return False
    if start < end:
        return start <= hour < end
    return hour >= start or hour < end  # wraps past midnight


# -- proactivity helpers (M4) ----------------------------------------------
def proactive_enabled(s: VoiceSettings) -> bool:
    """Whether the proactive loop runs at all. Default on — structural silence
    keeps it quiet regardless, so 'on' just means Aero is allowed to notice."""
    return bool((s.proactive or {}).get("enabled", True))


def proactive_threshold_offset(s: VoiceSettings, app: str | None = None) -> float:
    """Feedback-learned gate-threshold bump (AERO-PRO-005): the global offset plus
    any per-app offset for the currently-active app. Positive = quieter Aero."""
    p = s.proactive or {}
    off = float(p.get("threshold_offset", 0.0) or 0.0)
    if app:
        off += float((p.get("threshold_offset_by_app") or {}).get(app, 0.0) or 0.0)
    return off


def permission_granted(s: VoiceSettings, scope: str) -> bool:
    """Whether a capability scope is currently granted. The kill switch overrides
    everything to off (AERO-SAFE / panic). Default-deny for unknown scopes."""
    if s.killswitch:
        return False
    return bool((s.permissions or {}).get(scope, False))


def _construct_tts(backend: str, s: VoiceSettings):
    """Build a TTS engine from its catalog ``backend`` key. Imports are lazy so
    the base install stays dependency-free."""
    from aero.voice.tts import SapiTTS
    if backend == "svara":
        from aero.voice.svara_tts import SvaraTTS
        return SvaraTTS(s.svara_voice, base_url=s.svara_base_url)
    if backend == "parler":
        from aero.voice.parler_tts import ParlerTTS
        return ParlerTTS()
    if backend == "kokoro":
        from aero.voice.kokoro_tts import KokoroTTS
        return KokoroTTS(s.kokoro_voice)
    return SapiTTS()


_CLOUD_TTS = ("elevenlabs", "sarvam", "cartesia", "google")
_CLOUD_STT = ("deepgram", "sarvam", "google")


def build_tts(cfg: Config | None = None):
    """Construct the TTS engine the user selected, resolved through the voice
    catalog (M11): ``s.engine`` is a catalog id -> its backend -> the engine.
    Cloud backends (ElevenLabs/Sarvam/Cartesia) get a key from the voice keyring.
    Unknown ids fall through to the id-as-backend (back-compat)."""
    from aero.voice.catalog import registry as _vreg
    s = load(cfg)
    prof = _vreg(s.voice_engines).get(s.engine)
    backend = prof.backend if prof else s.engine
    if prof is not None and prof.role == "tts" and backend in _CLOUD_TTS:
        from aero.cognition.keys import resolve_voice_key
        from aero.voice.cloud_tts import build_cloud_tts
        return build_cloud_tts(backend, resolve_voice_key(prof))
    return _construct_tts(backend, s)


def build_tts_with_fallback(cfg: Config | None = None):
    """TTS wrapped so a dead cloud/local engine degrades to SAPI (AERO-VOX-404).
    The voice loop uses this; the bare ``build_tts`` stays exact for callers that
    want a specific engine."""
    from aero.voice.fallback import FallbackTTS
    from aero.voice.tts import SapiTTS
    primary = build_tts(cfg)
    if isinstance(primary, SapiTTS):
        return primary  # already the local backstop; nothing to fall back to
    return FallbackTTS(primary, SapiTTS())


def build_stt(cfg: Config | None = None, *, model: str | None = None):
    """Construct the selected STT backend. ``model`` overrides the persisted
    choice (used by `aero voice --model ...`). A catalog id resolves to its
    backend; anything else (a whisper size / model id) passes straight through."""
    from aero.perception.indic_stt import build_stt as _build
    from aero.voice.catalog import registry as _vreg
    s = load(cfg)
    choice = model or s.stt_model
    prof = _vreg(s.voice_engines).get(choice)
    backend = prof.backend if prof else choice
    if prof is not None and prof.role == "stt" and backend in _CLOUD_STT:
        from aero.cognition.keys import resolve_voice_key
        from aero.perception.cloud_stt import build_cloud_stt
        return build_cloud_stt(backend, resolve_voice_key(prof))
    return _build(backend)


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
