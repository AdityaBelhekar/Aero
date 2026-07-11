"""Continuous microphone stream for the real-time loop.

Unlike ``mic.Recorder`` (push-to-talk, ffmpeg-to-file), this yields a live stream
of fixed-size PCM16 frames so the VAD can decide turn boundaries as you speak.

Uses ``sounddevice`` (PortAudio) — the clean way to do frame-level capture in
Python — kept optional: importing this module never requires it, and
``available()`` reports whether it's usable so the loop can fall back to
push-to-talk. 16 kHz mono int16 matches both Moonshine and Whisper.
"""

from __future__ import annotations

import contextlib
import queue
import wave
from pathlib import Path


def pcm16_to_wav(pcm: bytes, path: str, sample_rate: int = 16000) -> str:
    """Write raw PCM16 mono bytes to a WAV file (for the STT backends)."""
    with contextlib.closing(wave.open(path, "wb")) as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sample_rate)
        w.writeframes(pcm)
    return path


class MicStream:
    def __init__(
        self,
        *,
        sample_rate: int = 16000,
        frame_ms: int = 30,
        device: int | str | None = None,
    ):
        self.sample_rate = sample_rate
        self.frame_ms = frame_ms
        self.frame_samples = sample_rate * frame_ms // 1000
        self.device = device
        self._q: queue.Queue[bytes] = queue.Queue()
        self._stream = None

    def available(self) -> bool:
        try:
            import sounddevice  # noqa: F401
            return True
        except Exception:
            return False

    def _callback(self, indata, frames, time_info, status):  # sounddevice thread
        # indata is int16 mono; hand raw bytes to the consumer.
        self._q.put(bytes(indata))

    def start(self) -> None:
        import sounddevice as sd
        self._stream = sd.RawInputStream(
            samplerate=self.sample_rate,
            blocksize=self.frame_samples,
            device=self.device,
            channels=1,
            dtype="int16",
            callback=self._callback,
        )
        self._stream.start()

    def frames(self):
        """Yield PCM16 frames until ``stop`` is called. Blocks on the mic queue."""
        while self._stream is not None:
            try:
                yield self._q.get(timeout=0.5)
            except queue.Empty:
                continue

    def stop(self) -> None:
        s, self._stream = self._stream, None
        if s is not None:
            with contextlib.suppress(Exception):
                s.stop(); s.close()
