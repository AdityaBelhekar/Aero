"""User-tunable settings (voice engine + chosen voice), persisted as JSON.

Kept separate from the memory vault: these are preferences, not memories, and the
user edits them directly. Stored at ``AERO_HOME/settings.json``.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
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
    brain: str = "local"
    cloud_provider: str = "groq"  # alias in cloud_backend.PROVIDERS, or a full URL
    cloud_model: str = "llama-3.3-70b-versatile"


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


def build_brain(cfg: Config | None = None, *, force: str | None = None):
    """Construct the selected cognition backend. 'local' -> gemma4 via Ollama
    (private default); 'cloud' -> OpenAI-compatible online brain (real-time).
    ``force`` overrides the persisted choice for one call (e.g. `--brain cloud`)."""
    from aero.cognition.ollama_backend import OllamaCognition
    s = load(cfg)
    which = force or s.brain
    if which == "cloud":
        from aero.cognition.cloud_backend import CloudCognition
        return CloudCognition(s.cloud_model, base_url=s.cloud_provider)
    return OllamaCognition()
