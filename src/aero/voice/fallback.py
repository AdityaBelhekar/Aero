"""Voice fallback chain — degrade, never die (AERO-VOX-404, v0.3 Rule 9).

Every paid/cloud voice must have a free/local backstop. If the chosen engine is
unreachable (server down, out of credits, no key), Aero falls to a local engine
and tells the user once — it never hard-stalls the loop. These thin wrappers make
that automatic: they implement the same ``TTSService`` / ``STTService`` interface,
so callers keep using one engine and never know a swap happened.

Mirrors the brain router's fallback (M8): a healthy primary is preferred; a dead
one (probed lazily, cached) or an exception mid-call routes to the fallback and
sets ``last_fallback`` so the UI can say "cloud voice was down — used local".
"""

from __future__ import annotations

from aero.perception.stt import STTService, Transcript
from aero.voice.speech_intent import SpeechIntent
from aero.voice.tts import SpeechResult, TTSService


class FallbackTTS(TTSService):
    def __init__(self, primary: TTSService, fallback: TTSService):
        self.primary = primary
        self.fallback = fallback
        self.voice_name = getattr(primary, "voice_name", "fallback")
        self.last_fallback = False
        self._active: TTSService | None = None

    def _choose(self) -> TTSService:
        """Pick primary if healthy, else fallback. Cached; call reset() to re-probe."""
        if self._active is not None:
            return self._active
        try:
            healthy = self.primary.health_check()
        except Exception:
            healthy = False
        self._active = self.primary if healthy else self.fallback
        self.last_fallback = self._active is self.fallback
        return self._active

    def reset(self) -> None:
        self._active = None
        self.last_fallback = False

    def synthesize(self, intent: SpeechIntent, out_path: str) -> SpeechResult:
        engine = self._choose()
        try:
            return engine.synthesize(intent, out_path)
        except Exception as e:
            if engine is self.primary:  # primary blew up mid-call -> degrade
                self.last_fallback = True
                self._active = self.fallback
                return self.fallback.synthesize(intent, out_path)
            return SpeechResult(audio_path=None, seconds_compute=0.0, ok=False,
                                error=str(e))

    def speak(self, intent: SpeechIntent) -> SpeechResult:
        engine = self._choose()
        try:
            return engine.speak(intent)
        except Exception as e:
            if engine is self.primary:
                self.last_fallback = True
                self._active = self.fallback
                return self.fallback.speak(intent)
            return SpeechResult(audio_path=None, seconds_compute=0.0, ok=False,
                                error=str(e))

    def health_check(self) -> bool:
        try:
            if self.primary.health_check():
                return True
        except Exception:
            pass
        try:
            return self.fallback.health_check()
        except Exception:
            return False


class FallbackSTT(STTService):
    def __init__(self, primary: STTService, fallback: STTService):
        self.primary = primary
        self.fallback = fallback
        self.model_name = getattr(primary, "model_name", "fallback")
        self.last_fallback = False
        self._active: STTService | None = None

    def _choose(self) -> STTService:
        if self._active is not None:
            return self._active
        try:
            healthy = self.primary.health_check()
        except Exception:
            healthy = False
        self._active = self.primary if healthy else self.fallback
        self.last_fallback = self._active is self.fallback
        return self._active

    def reset(self) -> None:
        self._active = None
        self.last_fallback = False

    def transcribe(self, audio_path: str, *, language: str | None = None) -> Transcript:
        engine = self._choose()
        try:
            return engine.transcribe(audio_path, language=language)
        except Exception:
            if engine is self.primary:
                self.last_fallback = True
                self._active = self.fallback
                return self.fallback.transcribe(audio_path, language=language)
            raise

    def health_check(self) -> bool:
        try:
            if self.primary.health_check():
                return True
        except Exception:
            pass
        try:
            return self.fallback.health_check()
        except Exception:
            return False
