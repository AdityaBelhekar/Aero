"""The voice marketplace — a catalog of swappable STT + TTS engines (AERO-VOX-401/402).

Aero already switches between SAPI/Svara/Parler/Kokoro (mouth) and
Whisper/IndicConformer/Moonshine (ears) through an if-ladder. v0.3 formalises that
into a **catalog** — the same registry-of-profiles pattern the brain uses (M8) —
so the human browses engines (mixing free/local and paid/cloud), picks per role,
and third-party engines drop in without touching call sites.

A ``VoiceProfile`` is provider-agnostic capability metadata: what it does, what it
costs, what languages it covers, whether it streams (first-audio-out fast, which
keeps the real-time loop snappy and the avatar's mouth moving), whether it can act
on emotion, and which env var / keyring entry holds its key. Local engines are
private and free; cloud engines need a key and leave the device.

This module is metadata only — constructing an engine lives in the builders
(settings.build_tts / build_stt), which look profiles up here. The cloud adapters
(ElevenLabs/Sarvam/Cartesia TTS, Deepgram/Sarvam STT) are now implemented; a future
catalogued engine can still ship as ``implemented=False`` to appear in the
marketplace before its adapter is written.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

Role = str        # "tts" | "stt"
CostTier = str    # "free-local" | "paid" | "freemium"


@dataclass(frozen=True)
class VoiceProfile:
    id: str
    role: Role                       # "tts" or "stt"
    backend: str                     # builder key (sapi/svara/kokoro/whisper/...)
    cost_tier: CostTier = "paid"
    local: bool = False              # runs on-device (private, no key)
    streaming: bool = False          # emits audio/partials incrementally
    emotion: bool = False            # TTS can act on SpeechIntent affect
    languages: tuple[str, ...] = ()  # ISO-ish codes; () = many/unspecified
    key_env: str | None = None       # env var / keyring name for the API key
    default_model: str = ""          # engine-specific voice or model id
    implemented: bool = True         # is the backend adapter written?
    label: str = ""

    @property
    def private(self) -> bool:
        return self.local


# -- Built-in catalog ------------------------------------------------------
# Local first (free, private, no key), then cloud (paid, needs a key). All the
# cloud engines below have working adapters; a not-yet-built one would carry
# implemented=False to show in the marketplace without being selectable.
_TTS: tuple[VoiceProfile, ...] = (
    VoiceProfile(id="kokoro", role="tts", backend="kokoro", cost_tier="free-local",
                 local=True, streaming=False, languages=("en",),
                 default_model="am_michael",
                 label="Kokoro-82M — fast natural English, CPU-friendly (ONNX)"),
    VoiceProfile(id="svara", role="tts", backend="svara", cost_tier="free-local",
                 local=True, emotion=True,
                 languages=("en", "hi", "mr", "bn", "ta", "te"),
                 default_model="hi_male",
                 label="Svara-TTS — 38 Indian voices, 19 languages (server)"),
    VoiceProfile(id="parler", role="tts", backend="parler", cost_tier="free-local",
                 local=True, emotion=True, languages=("en", "hi", "mr"),
                 label="Indic Parler-TTS — describe-the-voice, code-mix (heavy)"),
    VoiceProfile(id="sapi", role="tts", backend="sapi", cost_tier="free-local",
                 local=True, languages=("en",),
                 label="Windows SAPI — robotic placeholder, zero-download"),
    # -- cloud (need a key; leave the device) --
    VoiceProfile(id="elevenlabs", role="tts", backend="elevenlabs", cost_tier="paid",
                 streaming=True, emotion=True, key_env="ELEVENLABS_API_KEY",
                 label="ElevenLabs — top quality, streaming, emotion (English-first)"),
    VoiceProfile(id="sarvam_tts", role="tts", backend="sarvam", cost_tier="paid",
                 streaming=True, emotion=True, languages=("hi", "mr", "en", "ta"),
                 key_env="SARVAM_API_KEY",
                 label="Sarvam Bulbul — Indic-native, code-switch, streaming"),
    VoiceProfile(id="cartesia", role="tts", backend="cartesia", cost_tier="paid",
                 streaming=True, key_env="CARTESIA_API_KEY",
                 label="Cartesia Sonic — very low latency streaming"),
    VoiceProfile(id="google_tts", role="tts", backend="google", cost_tier="paid",
                 languages=("en", "hi", "mr", "ta", "te", "bn"),
                 key_env="GOOGLE_API_KEY", default_model="en-US-Neural2-D",
                 label="Google Cloud TTS — Neural2/WaveNet, 50+ languages"),
)

_STT: tuple[VoiceProfile, ...] = (
    VoiceProfile(id="whisper-small", role="stt", backend="small",
                 cost_tier="free-local", local=True,
                 languages=("en", "hi", "mr"),
                 label="Whisper small — code-switch (Devanagari out), PTT default"),
    VoiceProfile(id="whisper-turbo", role="stt", backend="models/turbo",
                 cost_tier="free-local", local=True, languages=("en", "hi", "mr"),
                 label="Whisper large-v3-turbo — most accurate, GPU wants"),
    VoiceProfile(id="moonshine", role="stt", backend="moonshine/base",
                 cost_tier="free-local", local=True, streaming=True,
                 languages=("en",),
                 label="Moonshine — fast English, pure ONNX, low-latency CPU"),
    VoiceProfile(id="indic", role="stt", backend="indic", cost_tier="free-local",
                 local=True, languages=("mr", "hi", "en"),
                 label="IndicConformer — Marathi/Indic (needs NeMo fork)"),
    # -- cloud --
    VoiceProfile(id="sarvam_stt", role="stt", backend="sarvam", cost_tier="paid",
                 streaming=True, languages=("hi", "mr", "en"),
                 key_env="SARVAM_API_KEY",
                 label="Sarvam Saaras — best code-switch STT (cloud)"),
    VoiceProfile(id="deepgram", role="stt", backend="deepgram", cost_tier="paid",
                 streaming=True, key_env="DEEPGRAM_API_KEY",
                 label="Deepgram Nova — fast streaming STT"),
    VoiceProfile(id="google_stt", role="stt", backend="google", cost_tier="paid",
                 languages=("en", "hi", "mr", "ta", "te", "bn"),
                 key_env="GOOGLE_API_KEY",
                 label="Google Cloud STT — 125+ languages"),
)

BUILTIN_TTS: dict[str, VoiceProfile] = {p.id: p for p in _TTS}
BUILTIN_STT: dict[str, VoiceProfile] = {p.id: p for p in _STT}
BUILTIN_VOICE: dict[str, VoiceProfile] = {**BUILTIN_TTS, **BUILTIN_STT}


def registry(custom: dict[str, dict] | None = None) -> dict[str, VoiceProfile]:
    """Built-in catalog overlaid with user-defined/overridden profiles."""
    reg = dict(BUILTIN_VOICE)
    for pid, data in (custom or {}).items():
        fields = {k: v for k, v in {**data, "id": pid}.items()
                  if k in VoiceProfile.__dataclass_fields__}
        base = reg.get(pid)
        reg[pid] = replace(base, **fields) if base else VoiceProfile(**fields)
    return reg


def catalog(role: str | None = None, *, custom: dict | None = None,
            implemented_only: bool = False) -> list[VoiceProfile]:
    """The marketplace listing, optionally filtered by role / implemented."""
    out = list(registry(custom).values())
    if role:
        out = [p for p in out if p.role == role]
    if implemented_only:
        out = [p for p in out if p.implemented]
    return out
