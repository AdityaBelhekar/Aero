"""Lip-sync feed — TTS audio → the avatar's mouth (AERO-VOX-403, bridges M9↔M11).

The avatar's ``AvatarState.mouth_open`` (0..1, M9) has to move with whatever voice
is speaking. This is the amplitude path that drives it: take the TTS engine's PCM
audio and produce a mouth-open value per animation frame. It's a plain envelope
follower (RMS per frame → gated, gained, clamped) — no ML, no dependency beyond
the stdlib ``wave``/``array`` — so it runs on any engine's output (Kokoro, Svara,
Parler, or a streaming cloud voice) and is fully testable on synthetic PCM.

Two modes, one contract:
  * **streaming** — call ``frame_amplitude(chunk)`` on each audio chunk as it
    arrives and pass the result to ``PresenceDriver.tick(speaking=True,
    mouth_open=...)``. First-audio-out-fast engines keep the mouth moving as
    sound starts.
  * **whole-clip** — a non-streaming engine returns a WAV; ``envelope_for_wav``
    gives the whole per-frame track to play alongside the audio.

If a TTS engine ever emits phoneme/viseme timing, prefer that (crisper) and carry
it in ``AvatarState.viseme``; this amplitude path is the always-available default.
"""

from __future__ import annotations

import math
import wave
from array import array

_INT16_MAX = 32768.0


def pcm16_to_samples(data: bytes) -> array:
    """Parse little-endian 16-bit PCM bytes into signed-int samples."""
    samples = array("h")
    # trim a dangling odd byte so frombytes never raises
    if len(data) % 2:
        data = data[:-1]
    samples.frombytes(data)
    return samples


def _rms_normalised(samples) -> float:
    """RMS of int16 samples as a 0..1 fraction of full scale."""
    if not samples:
        return 0.0
    total = 0.0
    for s in samples:
        total += float(s) * float(s)
    return math.sqrt(total / len(samples)) / _INT16_MAX


class LipSync:
    """Envelope follower: audio amplitude -> mouth openness.

    ``gain`` maps typical speech RMS (~0.05–0.2 of full scale) up into the mouth's
    0..1 range; ``gate`` snaps near-silence shut so the mouth rests closed between
    words. Deterministic (no adaptive state) so frames are reproducible.
    """

    def __init__(self, *, fps: int = 30, gain: float = 6.0, gate: float = 0.02):
        self.fps = fps
        self.gain = gain
        self.gate = gate

    def frame_amplitude(self, samples) -> float:
        """Mouth-open value (0..1) for one frame's worth of samples. Accepts an
        ``array``/list of int16, or raw PCM16 bytes."""
        if isinstance(samples, (bytes, bytearray)):
            samples = pcm16_to_samples(bytes(samples))
        rms = _rms_normalised(samples)
        if rms < self.gate:
            return 0.0
        return max(0.0, min(1.0, rms * self.gain))

    def envelope(self, samples, sample_rate: int, *, fps: int | None = None) -> list[float]:
        """Per-frame mouth-open track over a whole sample buffer."""
        if isinstance(samples, (bytes, bytearray)):
            samples = pcm16_to_samples(bytes(samples))
        fps = fps or self.fps
        hop = max(1, sample_rate // fps)
        return [self.frame_amplitude(samples[i:i + hop])
                for i in range(0, len(samples), hop)]


def read_wav(path: str) -> tuple[array, int]:
    """Read a (mono-ised) int16 sample buffer + sample rate from a WAV file. Uses
    only the stdlib; averages channels to mono and left-shifts 8-bit if needed."""
    with wave.open(path, "rb") as w:
        n_ch = w.getnchannels()
        width = w.getsampwidth()
        rate = w.getframerate()
        raw = w.readframes(w.getnframes())

    if width == 2:
        samples = pcm16_to_samples(raw)
    elif width == 1:  # unsigned 8-bit -> signed 16-bit
        samples = array("h", ((b - 128) << 8 for b in raw))
    else:  # 24/32-bit: take the high 2 bytes of each frame as int16
        step = width
        samples = array("h")
        for i in range(0, len(raw) - step + 1, step):
            samples.append(int.from_bytes(raw[i + step - 2:i + step], "little", signed=True))

    if n_ch > 1:  # downmix to mono by averaging channels
        mono = array("h")
        for i in range(0, len(samples) - n_ch + 1, n_ch):
            mono.append(int(sum(samples[i:i + n_ch]) / n_ch))
        samples = mono
    return samples, rate


def envelope_for_wav(path: str, *, fps: int = 30, gain: float = 6.0) -> list[float]:
    """Convenience: the whole per-frame mouth-open track for a WAV file."""
    samples, rate = read_wav(path)
    return LipSync(fps=fps, gain=gain).envelope(samples, rate)
