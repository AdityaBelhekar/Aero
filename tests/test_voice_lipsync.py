"""Lip-sync feed: audio -> AvatarState.mouth_open (AERO-VOX-403). Synthetic PCM."""

from __future__ import annotations

import math
import wave
from array import array

from aero.voice.lipsync import LipSync, envelope_for_wav, pcm16_to_samples, read_wav


def _sine(freq: float, amp: float, n: int, rate: int = 16000) -> array:
    """int16 sine samples at fractional full-scale amplitude (0..1)."""
    peak = amp * 32767
    return array("h", (int(peak * math.sin(2 * math.pi * freq * i / rate))
                       for i in range(n)))


def test_silence_is_closed_mouth():
    ls = LipSync()
    assert ls.frame_amplitude(array("h", [0] * 800)) == 0.0


def test_loud_audio_opens_mouth():
    ls = LipSync()
    loud = _sine(150, 0.9, 800)
    assert ls.frame_amplitude(loud) > 0.8


def test_quiet_audio_partial_open():
    ls = LipSync()
    quiet = _sine(150, 0.06, 800)
    amp = ls.frame_amplitude(quiet)
    assert 0.0 < amp < 0.6


def test_gate_snaps_near_silence_shut():
    ls = LipSync(gate=0.05)
    faint = _sine(150, 0.01, 800)   # below gate
    assert ls.frame_amplitude(faint) == 0.0


def test_amplitude_clamped_to_one():
    ls = LipSync(gain=100.0)
    assert ls.frame_amplitude(_sine(150, 0.9, 800)) == 1.0


def test_accepts_raw_pcm_bytes():
    ls = LipSync()
    loud = _sine(150, 0.9, 800)
    assert ls.frame_amplitude(loud.tobytes()) > 0.8


def test_odd_byte_pcm_does_not_crash():
    # a dangling byte must be trimmed, not raise
    assert pcm16_to_samples(b"\x01\x02\x03") == array("h", [0x0201])


def test_envelope_tracks_loud_then_quiet():
    ls = LipSync(fps=10)
    rate = 16000
    loud = _sine(150, 0.9, rate)     # 1s loud
    silent = array("h", [0] * rate)  # 1s silence
    env = ls.envelope(loud + silent, rate)
    half = len(env) // 2
    assert sum(env[:half]) / half > 0.7    # loud half open
    assert sum(env[half:]) / (len(env) - half) < 0.05  # silent half closed


# -- WAV path --------------------------------------------------------------
def _write_wav(path, samples, rate=16000, n_ch=1):
    with wave.open(str(path), "wb") as w:
        w.setnchannels(n_ch)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(samples.tobytes())


def test_read_wav_mono(tmp_path):
    p = tmp_path / "a.wav"
    _write_wav(p, _sine(150, 0.5, 16000))
    samples, rate = read_wav(str(p))
    assert rate == 16000 and len(samples) == 16000


def test_read_wav_downmixes_stereo(tmp_path):
    p = tmp_path / "s.wav"
    # interleave L/R identical -> mono equals one channel
    mono = _sine(150, 0.5, 8000)
    stereo = array("h")
    for s in mono:
        stereo.append(s)
        stereo.append(s)
    _write_wav(p, stereo, n_ch=2)
    samples, _ = read_wav(str(p))
    assert len(samples) == 8000     # halved


def test_envelope_for_wav(tmp_path):
    p = tmp_path / "b.wav"
    _write_wav(p, _sine(150, 0.9, 16000))
    env = envelope_for_wav(str(p), fps=30)
    assert 30 <= len(env) <= 31     # ~1s at 30fps (+ a trailing partial window)
    assert max(env) > 0.8


# -- integration with the presence driver (M9) -----------------------------
def test_mouth_open_drives_avatar_state():
    import random

    from aero.presence import PresenceDriver
    from aero.voice.speech_intent import SpeechIntent

    driver = PresenceDriver(clock=lambda: 0.0, rng=random.Random(0))
    ls = LipSync()
    amp = ls.frame_amplitude(_sine(150, 0.9, 800))
    state = driver.tick(speaking=True, intent=SpeechIntent.from_tone("yo", "excited"),
                        mouth_open=amp)
    assert state.animation.value == "speaking"
    assert state.mouth_open > 0.8   # the mouth is open, in sync with the audio
