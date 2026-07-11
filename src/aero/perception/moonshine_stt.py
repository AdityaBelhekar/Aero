"""Moonshine STT — Aero's fast English ear (low-latency, CPU).

Moonshine (Useful Sensors / moonshine-ai) is an English-only ASR built for
edge/real-time: tiny (26M/58M), pure ONNX (no torch), and designed for
sub-second latency on CPU — a better fit than Whisper for a snappy voice loop
once Aero is English-focused. Devanagari/code-switch is out of scope by design
(that's what the AI4Bharat path was for); this is the English speed play.

Runs via ``moonshine-onnx`` (import ``moonshine_onnx``), an optional dependency:
importing this module never requires it. Weights auto-download from HuggingFace
on first use. Kept behind the same ``STTService`` interface, so
``aero voice --model moonshine`` selects it with no caller changes.
"""

from __future__ import annotations

import contextlib
import time
import wave

from aero.perception.stt import STTService, Transcript

DEFAULT_MODEL = "moonshine/base"   # "moonshine/tiny" (fastest) | "moonshine/base"


def _wav_seconds(audio_path: str) -> float:
    """Duration of a PCM WAV, dependency-free. 0.0 if unreadable."""
    try:
        with contextlib.closing(wave.open(audio_path, "rb")) as w:
            frames, rate = w.getnframes(), w.getframerate()
            return frames / rate if rate else 0.0
    except (wave.Error, OSError, EOFError):
        return 0.0


class MoonshineSTT(STTService):
    """Local Moonshine via moonshine-onnx. ``model_name`` is 'moonshine/tiny'
    (26M, fastest) or 'moonshine/base' (58M, more accurate)."""

    def __init__(self, model_name: str = DEFAULT_MODEL):
        self.model_name = model_name

    def transcribe(self, audio_path: str, *, language: str | None = None) -> Transcript:
        import moonshine_onnx  # lazy: optional dependency

        t0 = time.perf_counter()
        out = moonshine_onnx.transcribe(audio_path, self.model_name)
        compute = time.perf_counter() - t0
        # moonshine returns a list like ['the text']; tolerate a bare string too.
        if isinstance(out, (list, tuple)):
            text = (out[0] if out else "")
        else:
            text = out or ""
        return Transcript(
            text=text.strip(),
            language="en",                       # English-only model
            seconds_audio=_wav_seconds(audio_path),
            seconds_compute=compute,
        )

    def health_check(self) -> bool:
        try:
            import moonshine_onnx  # noqa: F401
            return True
        except Exception:
            return False
