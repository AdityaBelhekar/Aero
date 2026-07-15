"""Map a SpeechIntent to an avatar Emotion (AERO-PRES-102).

Aero's face should show what his voice is doing. ``SpeechIntent`` already carries
the affective read of a reply (energy, amusement, concern, sarcasm, …) for TTS;
the avatar reuses exactly that so voice and face stay in sync — no second, diverging
emotion model. The named ``emotional_tone`` is the strong signal; the numeric
fields break ties and cover the ``neutral`` tone.
"""

from __future__ import annotations

from aero.presence.state import Emotion
from aero.voice.speech_intent import SpeechIntent

# SpeechIntent.emotional_tone strings -> avatar Emotion.
_TONE_MAP: dict[str, Emotion] = {
    "amused": Emotion.HAPPY,
    "happy": Emotion.HAPPY,
    "teasing": Emotion.TEASING,
    "excited": Emotion.EXCITED,
    "serious": Emotion.NEUTRAL,
    "concerned": Emotion.CONCERNED,
    "annoyed": Emotion.ANNOYED,
    "low": Emotion.TIRED,
    "tired": Emotion.TIRED,
    "neutral": Emotion.NEUTRAL,
}


def emotion_from_intent(intent: SpeechIntent | None) -> Emotion:
    """Best avatar Emotion for a speech intent. None -> NEUTRAL."""
    if intent is None:
        return Emotion.NEUTRAL

    tone = (intent.emotional_tone or "neutral").lower()
    mapped = _TONE_MAP.get(tone)
    if mapped is not None and mapped is not Emotion.NEUTRAL:
        return mapped

    # Tone was neutral/serious/unknown — let the numeric affect decide, strongest
    # signal first.
    if intent.concern > 0.5:
        return Emotion.CONCERNED
    if intent.laugh_intensity > 0.5 or intent.amusement > 0.6:
        return Emotion.HAPPY
    if intent.sarcasm > 0.4:
        return Emotion.TEASING
    if intent.energy >= 0.75:
        return Emotion.EXCITED
    if intent.energy <= 0.35:
        return Emotion.TIRED
    return mapped or Emotion.NEUTRAL
