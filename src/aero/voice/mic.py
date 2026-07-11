"""Microphone capture via ffmpeg (no extra Python audio deps).

ffmpeg is already a project dependency (used for audio conversion), and on
Windows its dshow input can record the mic directly. Push-to-talk: start
recording, the user presses Enter to stop, ffmpeg is told to finish cleanly and
leaves a valid 16 kHz mono WAV ready for Whisper.

If no mic / dshow is unavailable, the voice loop falls back to typed input, so
this never hard-blocks the companion.
"""

from __future__ import annotations

import re
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

_IS_WINDOWS = sys.platform == "win32"


@dataclass
class MicResult:
    wav_path: str | None
    ok: bool = True
    error: str | None = None


def list_mics() -> list[str]:
    """Return dshow audio input device names (Windows)."""
    if not _IS_WINDOWS:
        return []
    proc = subprocess.run(
        ["ffmpeg", "-hide_banner", "-list_devices", "true", "-f", "dshow", "-i", "dummy"],
        capture_output=True, text=True,
    )
    # Device list is emitted on stderr; audio devices are tagged "(audio)".
    names = []
    for line in proc.stderr.splitlines():
        if "(audio)" in line:
            m = re.search(r'"([^"]+)"', line)
            if m:
                names.append(m.group(1))
    return names


def default_mic() -> str | None:
    mics = list_mics()
    return mics[0] if mics else None


class Recorder:
    """Push-to-talk recorder. Start(), then stop() when the user is done."""

    def __init__(self, device: str | None = None):
        self.device = device or (default_mic() if _IS_WINDOWS else None)
        self._proc: subprocess.Popen | None = None
        self._wav: str | None = None

    def available(self) -> bool:
        return _IS_WINDOWS and self.device is not None

    def start(self) -> bool:
        if not self.available():
            return False
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            self._wav = f.name
        self._proc = subprocess.Popen(
            ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
             "-f", "dshow", "-i", f"audio={self.device}",
             "-ar", "16000", "-ac", "1", self._wav],
            stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        return True

    def stop(self) -> MicResult:
        if self._proc is None:
            return MicResult(None, ok=False, error="not recording")
        try:
            # 'q' tells ffmpeg to finish and finalize the WAV cleanly.
            if self._proc.stdin:
                self._proc.stdin.write(b"q")
                self._proc.stdin.flush()
            self._proc.wait(timeout=10)
        except Exception:
            self._proc.terminate()
        finally:
            proc = self._proc
            self._proc = None
        wav = self._wav
        if wav and Path(wav).exists() and Path(wav).stat().st_size > 1000:
            return MicResult(wav, ok=True)
        return MicResult(None, ok=False, error="no audio captured")
