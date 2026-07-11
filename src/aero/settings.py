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
    engine: str = "sapi"          # 'sapi' (placeholder) | 'svara' (real Aero Voice)
    svara_voice: str = "hi_male"  # which of Svara's 38 profiles
    svara_base_url: str = "http://localhost:8080/v1"


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
    from aero.voice.svara_tts import SvaraTTS
    from aero.voice.tts import SapiTTS

    s = load(cfg)
    if s.engine == "svara":
        return SvaraTTS(s.svara_voice, base_url=s.svara_base_url)
    return SapiTTS()
