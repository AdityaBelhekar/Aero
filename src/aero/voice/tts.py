"""Text-to-speech — Aero's mouth.

``TTSService`` is the swappable interface (SAPI today, Svara-TTS / Aero Voice
later — PRD Section 29). It takes a ``SpeechIntent``, not raw text, so delivery is
under Aero's control.

The default ``SapiTTS`` drives the built-in Windows Speech engine via a
PowerShell shim (System.Speech), which speaks SSML rendered from the intent. It's
a placeholder voice — not the young-Indian-male Aero Voice — but it makes the
entire speak path real and testable today with zero downloads. Swapping in
Svara-TTS later means implementing one more backend; nothing else changes.
"""

from __future__ import annotations

import subprocess
import sys
import tempfile
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path

from aero.voice.speech_intent import SpeechIntent, render_ssml

_IS_WINDOWS = sys.platform == "win32"


@dataclass
class SpeechResult:
    audio_path: str | None
    seconds_compute: float
    ok: bool = True
    error: str | None = None


class TTSService(ABC):
    voice_name: str

    @abstractmethod
    def synthesize(self, intent: SpeechIntent, out_path: str) -> SpeechResult:
        """Render the intent to a WAV file at out_path."""

    @abstractmethod
    def speak(self, intent: SpeechIntent) -> SpeechResult:
        """Synthesize and play through the speakers (blocking)."""

    @abstractmethod
    def health_check(self) -> bool:
        ...


# PowerShell shim: read SSML from a file and write a WAV. Kept as a here-doc so
# SSML escaping never has to survive the command line.
_PS_SYNTH = r"""
Add-Type -AssemblyName System.Speech
$ssml = Get-Content -Raw -Path "{ssml_path}"
$synth = New-Object System.Speech.Synthesis.SpeechSynthesizer
$synth.SetOutputToWaveFile("{wav_path}")
try {{ $synth.SpeakSsml($ssml) }} catch {{ $synth.Speak($ssml) }}
$synth.Dispose()
"""


class SapiTTS(TTSService):
    """Windows SAPI via System.Speech. Placeholder voice; real path is Svara."""

    def __init__(self, voice_name: str = "sapi-default"):
        self.voice_name = voice_name

    def _run_synth(self, ssml: str, wav_path: str) -> None:
        with tempfile.NamedTemporaryFile("w", suffix=".ssml", delete=False,
                                         encoding="utf-8") as f:
            f.write(ssml)
            ssml_path = f.name
        script = _PS_SYNTH.format(ssml_path=ssml_path.replace("\\", "\\\\"),
                                  wav_path=wav_path.replace("\\", "\\\\"))
        try:
            subprocess.run(
                ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
                check=True, capture_output=True, timeout=60,
            )
        finally:
            try:
                Path(ssml_path).unlink()
            except OSError:
                pass

    def synthesize(self, intent: SpeechIntent, out_path: str) -> SpeechResult:
        if not _IS_WINDOWS:
            return SpeechResult(None, 0.0, ok=False, error="SAPI is Windows-only")
        ssml = render_ssml(intent)
        t0 = time.perf_counter()
        try:
            self._run_synth(ssml, out_path)
        except Exception as e:  # subprocess / SAPI failure
            return SpeechResult(None, time.perf_counter() - t0, ok=False, error=str(e))
        return SpeechResult(out_path, time.perf_counter() - t0)

    def speak(self, intent: SpeechIntent) -> SpeechResult:
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            wav = f.name
        res = self.synthesize(intent, wav)
        if res.ok and _IS_WINDOWS:
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
        return _IS_WINDOWS
