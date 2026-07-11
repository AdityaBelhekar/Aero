"""Kokoro TTS backend — Aero's fast, natural English voice.

Kokoro-82M is a tiny (82M param) open-weight TTS that punches far above its size:
natural prosody, and **faster-than-realtime on CPU** — the opposite of Parler's
277x. This is the real Aero voice for an English-focused, CPU-only box.

Runs via ``kokoro-onnx`` (ONNX Runtime), an optional dependency: importing this
module never requires it. ONNX also means the model can use an integrated GPU via
onnxruntime-directml — a genuine speedup here, unlike the 0.9B Parler.

Two model files (downloaded once, gitignored under models/kokoro/):
  kokoro-v1.0.onnx   (~310 MB)   voices-v1.0.bin   (~26 MB)
See docs/CLOUD_BRAIN_SETUP.md's sibling note or docs/KOKORO_SETUP.md.

Kokoro exposes ``voice`` + ``speed`` (no emotion model), so SpeechIntent maps its
pace onto speed; the affective fields are carried but not yet expressible — same
forward-compatible contract as the other backends.
"""

from __future__ import annotations

import sys
import tempfile
import time
from pathlib import Path

from aero.voice.speech_intent import SpeechIntent
from aero.voice.tts import SpeechResult, TTSService

DEFAULT_DIR = Path("models/kokoro")
MODEL_FILE = "kokoro-v1.0.onnx"
VOICES_FILE = "voices-v1.0.bin"
SAMPLE_RATE = 24000

# A curated subset for Aero (young, warm male). Full list: Kokoro-82M VOICES.md.
KOKORO_VOICES = [
    "am_michael", "am_adam", "am_echo", "am_eric", "am_fenrir", "am_liam",
    "am_onyx", "am_puck",                         # American male
    "bm_george", "bm_lewis", "bm_daniel", "bm_fable",  # British male
    "af_heart", "af_bella", "af_sarah", "af_nicole",   # American female
    "bf_emma", "bf_isabella",                     # British female
]
# Aero is a young Indian male; Kokoro has no Indian voice, so a warm young
# American/British male is the closest fit.
DEFAULT_VOICE = "am_michael"


def _intent_to_speed(intent: SpeechIntent) -> float:
    """Map SpeechIntent.pace (0..1, 0.5=neutral) to Kokoro speed (~0.7..1.4).

    Neutral pace -> ~1.05 (a touch lively); slow -> deliberate; fast -> rushed.
    Energy nudges it slightly so excited replies come out a hair quicker."""
    speed = 0.85 + intent.pace * 0.4 + (intent.energy - 0.5) * 0.1
    return max(0.7, min(1.4, round(speed, 3)))


class KokoroTTS(TTSService):
    def __init__(
        self,
        voice: str = DEFAULT_VOICE,
        *,
        model_path: str | Path | None = None,
        voices_path: str | Path | None = None,
        lang: str = "en-us",
    ):
        self.voice_name = voice
        self.lang = lang
        self.model_path = Path(model_path) if model_path else DEFAULT_DIR / MODEL_FILE
        self.voices_path = Path(voices_path) if voices_path else DEFAULT_DIR / VOICES_FILE
        self._kokoro = None

    def set_voice(self, voice: str) -> None:
        self.voice_name = voice

    # -- model (lazy) ------------------------------------------------------
    def _ensure_model(self):
        if self._kokoro is None:
            from kokoro_onnx import Kokoro  # lazy: optional dependency
            self._kokoro = Kokoro(str(self.model_path), str(self.voices_path))
        return self._kokoro

    def _render(self, text: str, voice: str, speed: float, out_path: str) -> None:
        """Synthesize and write a WAV. Isolated so tests mock the heavy path."""
        import soundfile as sf
        kokoro = self._ensure_model()
        samples, sr = kokoro.create(text, voice=voice, speed=speed, lang=self.lang)
        sf.write(out_path, samples, sr)

    # -- TTSService --------------------------------------------------------
    def synthesize(self, intent: SpeechIntent, out_path: str) -> SpeechResult:
        speed = _intent_to_speed(intent)
        t0 = time.perf_counter()
        try:
            self._render(intent.text, self.voice_name, speed, out_path)
        except Exception as e:  # model/file/synthesis failure
            return SpeechResult(None, time.perf_counter() - t0, ok=False, error=str(e))
        return SpeechResult(out_path, time.perf_counter() - t0)

    def speak(self, intent: SpeechIntent) -> SpeechResult:
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
        """True only if the package is importable AND the model files exist —
        Kokoro can't synthesize without the weights, so the voice loop falls back
        to SAPI cleanly when they're missing."""
        try:
            import kokoro_onnx  # noqa: F401
            import soundfile  # noqa: F401
        except Exception:
            return False
        return self.model_path.is_file() and self.voices_path.is_file()
