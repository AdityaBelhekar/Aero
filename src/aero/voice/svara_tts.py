"""Svara-TTS backend — Aero's real (offline-capable) voice.

Svara-TTS (kenpath/svara-tts-v1) is an Orpheus-style multilingual Indic TTS with
38 voice profiles across 19 Indian languages. Its official interface is an
OpenAI-compatible speech endpoint, so — exactly like Ollama for the LLM — Aero
talks to a **Svara server** over HTTP and stays a thin client. The heavy model
runs in its own process (on a GPU it's fast; on CPU it's slow but works), which
keeps Aero light and lets the server live wherever the compute is.

Voice selection is first-class: `voices()` lists the 38 profiles and the chosen
one is passed per request. Set up the server per docs/SVARA_SETUP.md; until it's
reachable, `health_check()` is False and the voice loop falls back to SAPI.
"""

from __future__ import annotations

import json
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

from aero.voice.speech_intent import SpeechIntent
from aero.voice.tts import SpeechResult, TTSService

DEFAULT_BASE_URL = "http://localhost:8080/v1"

# 19 languages Svara supports; each has a male and a female profile -> 38 voices.
SVARA_LANGUAGES = {
    "en": "Indian English",
    "hi": "Hindi",
    "mr": "Marathi",
    "bn": "Bengali",
    "ta": "Tamil",
    "te": "Telugu",
    "kn": "Kannada",
    "ml": "Malayalam",
    "gu": "Gujarati",
    "pa": "Punjabi",
    "or": "Odia",
    "as": "Assamese",
    "ur": "Urdu",
    "sa": "Sanskrit",
    "ne": "Nepali",
    "kok": "Konkani",
    "mai": "Maithili",
    "sd": "Sindhi",
    "doi": "Dogri",
}


def voices() -> list[str]:
    """All 38 Svara voice profiles as `{lang}_{gender}` ids."""
    out = []
    for code in SVARA_LANGUAGES:
        out.append(f"{code}_male")
        out.append(f"{code}_female")
    return out


def describe_voice(voice: str) -> str:
    code, _, gender = voice.partition("_")
    lang = SVARA_LANGUAGES.get(code, code)
    return f"{lang} ({gender or '?'})"


# Aero is a young Indian male — these are the natural default candidates.
AERO_VOICE_CANDIDATES = ["hi_male", "mr_male", "en_male"]
DEFAULT_VOICE = "hi_male"


class SvaraTTS(TTSService):
    def __init__(
        self,
        voice: str = DEFAULT_VOICE,
        *,
        base_url: str = DEFAULT_BASE_URL,
        model: str = "svara-tts-v1",
        timeout: float = 120.0,
    ):
        self.voice_name = voice
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout = timeout

    def set_voice(self, voice: str) -> None:
        self.voice_name = voice

    # -- HTTP --------------------------------------------------------------
    def _speech_request(self, text: str, out_path: str) -> None:
        payload = {
            "model": self.model,
            "voice": self.voice_name,
            "input": text,
            "response_format": "wav",
        }
        req = urllib.request.Request(
            f"{self.base_url}/audio/speech",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=self.timeout) as resp:
            audio = resp.read()
        Path(out_path).write_bytes(audio)

    # -- TTSService --------------------------------------------------------
    def synthesize(self, intent: SpeechIntent, out_path: str) -> SpeechResult:
        # Svara's expressiveness is driven by the text + voice profile; the
        # SpeechIntent's affective fields are carried but not all mapped yet
        # (Svara exposes light emotion/style control — a later refinement).
        t0 = time.perf_counter()
        try:
            self._speech_request(intent.text, out_path)
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            return SpeechResult(None, time.perf_counter() - t0, ok=False, error=str(e))
        return SpeechResult(out_path, time.perf_counter() - t0)

    def speak(self, intent: SpeechIntent) -> SpeechResult:
        import sys
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            wav = f.name
        res = self.synthesize(intent, wav)
        if res.ok and sys.platform == "win32":
            try:
                import winsound
                winsound.PlaySound(wav, winsound.SND_FILENAME)
            except Exception as e:
                res = SpeechResult(wav, res.seconds_compute, ok=False, error=str(e))
        try:
            Path(wav).unlink()
        except OSError:
            pass
        return res

    def health_check(self) -> bool:
        """True if a Svara server is reachable (the /models endpoint responds)."""
        try:
            req = urllib.request.Request(f"{self.base_url}/models", method="GET")
            with urllib.request.urlopen(req, timeout=5.0):
                return True
        except (urllib.error.URLError, TimeoutError, OSError):
            return False
