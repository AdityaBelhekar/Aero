"""Voice activity detection + endpointing — the turn-taking brain of the loop.

Real-time conversation means Aero decides *on its own* when you've started and
finished speaking — no push-to-talk button. That's two jobs:

  1. VAD: is this 30 ms frame speech or silence? (``VAD`` interface)
  2. Endpointing: given a stream of speech/silence flags, where does one utterance
     begin and end? (``VADSegmenter`` — a pure state machine)

The segmenter is deliberately pure (frames in, utterance-bytes out) so the whole
turn-taking logic is unit-testable with a scripted fake VAD, no audio hardware.

Default VAD is ``EnergyVAD`` — dependency-free RMS thresholding, good enough for a
quiet room + single speaker, so the loop runs today with nothing extra.
``SileroVAD`` is the optional quality upgrade (better in noise).
"""

from __future__ import annotations

import math
from abc import ABC, abstractmethod
from collections import deque
from dataclasses import dataclass


class VAD(ABC):
    @abstractmethod
    def is_speech(self, frame: bytes, sample_rate: int) -> bool:
        """True if this PCM16 frame contains speech."""


def frame_rms(frame: bytes) -> float:
    """RMS energy of a PCM16 frame, normalised to 0..1. Dependency-free."""
    n = len(frame) // 2
    if n == 0:
        return 0.0
    total = 0
    # int16 little-endian; sum of squares without numpy.
    import struct
    samples = struct.unpack(f"<{n}h", frame[: n * 2])
    for s in samples:
        total += s * s
    return math.sqrt(total / n) / 32768.0


class EnergyVAD(VAD):
    """RMS-threshold VAD. Dependency-free default. ``threshold`` is 0..1 RMS;
    tune up in a noisy room. ``calibrate`` can set it from ambient samples."""

    def __init__(self, threshold: float = 0.02):
        self.threshold = threshold

    def is_speech(self, frame: bytes, sample_rate: int) -> bool:
        return frame_rms(frame) > self.threshold

    def calibrate(self, ambient_frames: list[bytes], *, margin: float = 3.0) -> float:
        """Set threshold to `margin`x the ambient noise floor. Returns it."""
        if ambient_frames:
            floor = max((frame_rms(f) for f in ambient_frames), default=0.0)
            self.threshold = max(0.01, floor * margin)
        return self.threshold


class SileroVAD(VAD):
    """Optional high-quality neural VAD (Silero, via the silero-vad package).

    Lazy + optional: importing this module never requires it. Falls back to
    raising on use if not installed — callers should prefer EnergyVAD unless the
    dependency is present."""

    def __init__(self, threshold: float = 0.5):
        self.threshold = threshold
        self._model = None

    def _ensure(self):
        if self._model is None:
            from silero_vad import load_silero_vad  # optional dep
            self._model = load_silero_vad(onnx=True)
        return self._model

    def is_speech(self, frame: bytes, sample_rate: int) -> bool:
        import numpy as np
        model = self._ensure()
        audio = np.frombuffer(frame, dtype="<i2").astype("float32") / 32768.0
        # Silero expects 512 samples @16k / 256 @8k; pad/trim to the window.
        win = 512 if sample_rate >= 16000 else 256
        if len(audio) < win:
            audio = np.pad(audio, (0, win - len(audio)))
        prob = float(model(audio[:win], sample_rate))
        return prob >= self.threshold


@dataclass
class SegmenterConfig:
    sample_rate: int = 16000
    frame_ms: int = 30
    start_ms: int = 150      # continuous speech needed to open an utterance
    end_silence_ms: int = 700  # trailing silence that closes it (turn boundary)
    preroll_ms: int = 240    # audio kept from just before speech started
    max_ms: int = 15000      # hard cap on one utterance
    min_utt_ms: int = 250    # drop blips shorter than this (noise)


class VADSegmenter:
    """Pure endpointing state machine. Feed frames via ``push``; it returns the
    utterance's PCM bytes when it detects the end of a turn, else ``None``."""

    def __init__(self, vad: VAD, config: SegmenterConfig | None = None):
        self.vad = vad
        self.cfg = config or SegmenterConfig()
        self._preroll = deque(maxlen=max(1, self.cfg.preroll_ms // self.cfg.frame_ms))
        self._reset()

    def _reset(self) -> None:
        self.triggered = False
        self.voiced: list[bytes] = []
        self.speech_ms = 0
        self.silence_ms = 0

    @property
    def in_speech(self) -> bool:
        return self.triggered

    def push(self, frame: bytes) -> bytes | None:
        speech = self.vad.is_speech(frame, self.cfg.sample_rate)
        c = self.cfg

        if not self.triggered:
            self._preroll.append(frame)
            self.speech_ms = self.speech_ms + c.frame_ms if speech else 0
            if self.speech_ms >= c.start_ms:
                self.triggered = True
                self.voiced = list(self._preroll)   # include the lead-in
                self._preroll.clear()
                self.silence_ms = 0
            return None

        # In an utterance: accumulate until enough trailing silence (or max len).
        self.voiced.append(frame)
        self.silence_ms = 0 if speech else self.silence_ms + c.frame_ms
        total_ms = len(self.voiced) * c.frame_ms
        if self.silence_ms >= c.end_silence_ms or total_ms >= c.max_ms:
            utt = b"".join(self.voiced)
            self._reset()
            if len(utt) >= (c.min_utt_ms * c.sample_rate // 1000) * 2:  # *2: 16-bit
                return utt
        return None
