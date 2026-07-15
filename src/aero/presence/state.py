"""AvatarState — the small serialisable payload the daemon streams to the overlay.

This is the whole contract between Aero's cognition/voice loop and whatever renders
the character (AERO-PRES-101/102). The overlay is a *thin client*: it receives an
``AvatarState`` and plays the matching clip(s); it holds no logic of its own. Keep
this JSON tiny — it goes over the IPC on every state change and every audio frame
during speech.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum


class AnimationState(str, Enum):
    """The top-level thing Aero is doing right now (AERO-PRES-102). Drives which
    *family* of clips the overlay plays; ``Emotion`` colours it."""

    IDLE = "idle"          # ambient/fidget — he's just there, alive not frozen
    LISTENING = "listening"  # mic is hot (push-to-talk held, or wake detected)
    THINKING = "thinking"    # the brain is generating
    SPEAKING = "speaking"    # TTS audio is playing (lip-sync active)


class Emotion(str, Enum):
    """Affective colour for the current state, mapped from SpeechIntent
    (emotion.py). Neutral is the resting default."""

    NEUTRAL = "neutral"
    HAPPY = "happy"
    TEASING = "teasing"
    EXCITED = "excited"
    TIRED = "tired"
    CONCERNED = "concerned"
    ANNOYED = "annoyed"


@dataclass
class AvatarState:
    """One frame of "what the character should be doing". Serialised to JSON and
    pushed to the overlay."""

    animation: AnimationState = AnimationState.IDLE
    emotion: Emotion = Emotion.NEUTRAL
    #: Name of the clip the overlay should play for this state/emotion. Resolved
    #: from the RigManifest so the overlay needs no mapping knowledge.
    clip: str = ""
    #: A one-shot action clip to fire once now (wave, facepalm, point) then return
    #: to the base state. None most of the time.
    action: str | None = None
    #: Lip-sync drive during SPEAKING: 0..1 mouth-open amplitude for the current
    #: audio frame (AERO-PRES-104). 0 when not speaking. Phoneme/viseme timing, if
    #: the TTS engine provides it, can ride in ``viseme`` instead.
    mouth_open: float = 0.0
    viseme: str | None = None
    #: Free-form tags the overlay may use for extra flourish (e.g. "night",
    #: "gaming") — from the ambient scheduler's world-state read.
    tags: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["animation"] = self.animation.value
        d["emotion"] = self.emotion.value
        return d

    def to_json(self) -> str:
        import json
        return json.dumps(self.to_dict(), separators=(",", ":"))

    @classmethod
    def from_dict(cls, d: dict) -> "AvatarState":
        return cls(
            animation=AnimationState(d.get("animation", "idle")),
            emotion=Emotion(d.get("emotion", "neutral")),
            clip=d.get("clip", ""),
            action=d.get("action"),
            mouth_open=float(d.get("mouth_open", 0.0)),
            viseme=d.get("viseme"),
            tags=list(d.get("tags", [])),
        )
