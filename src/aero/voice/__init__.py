"""Aero's voice — speech intent and TTS.

Aero's mind never sends plain text straight to the speech model (PRD Section 30).
A ``SpeechIntent`` sits in between, carrying *how* to say it — energy, pace,
pauses, amusement — so the same words can land as serious, teasing, or concerned.
The TTS backend performs that intent; it's swappable (SAPI today, Svara-TTS /
Aero Voice later) like the cognition and STT layers.
"""

from aero.voice.speech_intent import SpeechIntent, render_ssml
from aero.voice.tts import SapiTTS, TTSService

__all__ = ["SpeechIntent", "render_ssml", "TTSService", "SapiTTS"]
