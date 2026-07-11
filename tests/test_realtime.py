"""Real-time VAD loop — hermetic tests for the endpointing state machine and the
orchestrator core (no audio hardware; scripted VAD + fake STT/agent/TTS)."""

from __future__ import annotations

import struct

from aero.perception.stt import Transcript
from aero.voice.realtime import RealtimeLoop, RealtimeTurn
from aero.voice.vad import (EnergyVAD, SegmenterConfig, VAD, VADSegmenter,
                            frame_rms)

FRAME_MS = 30
SR = 16000
FRAME_BYTES = SR * FRAME_MS // 1000 * 2  # int16


def _silence() -> bytes:
    return b"\x00\x00" * (SR * FRAME_MS // 1000)


def _loud() -> bytes:
    n = SR * FRAME_MS // 1000
    return struct.pack(f"<{n}h", *([8000] * n))  # high-amplitude tone


# -- EnergyVAD -------------------------------------------------------------
def test_energy_vad_distinguishes_silence_and_speech():
    v = EnergyVAD(threshold=0.02)
    assert v.is_speech(_silence(), SR) is False
    assert v.is_speech(_loud(), SR) is True
    assert frame_rms(_silence()) == 0.0


def test_energy_vad_calibrates_up_from_ambient():
    v = EnergyVAD(threshold=0.02)
    # ambient a bit noisy -> threshold rises above it
    n = SR * FRAME_MS // 1000
    ambient = [struct.pack(f"<{n}h", *([500] * n))]
    thr = v.calibrate(ambient, margin=3.0)
    assert thr > frame_rms(ambient[0])


# -- Scripted VAD for the segmenter ---------------------------------------
class ScriptedVAD(VAD):
    """is_speech() returns booleans from a script, one per frame."""

    def __init__(self, script: list[bool]):
        self.script = list(script)
        self.i = 0

    def is_speech(self, frame, sample_rate):
        v = self.script[self.i] if self.i < len(self.script) else False
        self.i += 1
        return v


def _cfg():
    return SegmenterConfig(sample_rate=SR, frame_ms=FRAME_MS, start_ms=90,
                           end_silence_ms=150, preroll_ms=60, min_utt_ms=60)


def test_segmenter_emits_after_trailing_silence():
    # 3 speech frames (>=90ms start) then 5 silence frames (>=150ms end).
    script = [True] * 3 + [False] * 6
    seg = VADSegmenter(ScriptedVAD(script), _cfg())
    out = None
    for _ in range(len(script)):
        r = seg.push(_loud())
        if r is not None:
            out = r
    assert out is not None                     # an utterance was emitted
    assert not seg.in_speech                    # reset afterwards


def test_segmenter_ignores_short_blip():
    # one speech frame (30ms < 90ms start) never opens an utterance.
    seg = VADSegmenter(ScriptedVAD([True] + [False] * 8), _cfg())
    outs = [seg.push(_loud()) for _ in range(9)]
    assert all(o is None for o in outs)
    assert not seg.in_speech


def test_segmenter_preroll_included():
    seg = VADSegmenter(ScriptedVAD([True] * 3 + [False] * 6), _cfg())
    got = None
    for _ in range(9):
        r = seg.push(_loud())
        if r:
            got = r
    # utterance should carry more than just the 3 trigger frames (preroll+voiced)
    assert got is not None and len(got) >= FRAME_BYTES * 3


# -- Orchestrator core (handle_utterance) ---------------------------------
class FakeSTT:
    def __init__(self, text):
        self.model_name = "fake"
        self.text = text

    def transcribe(self, path, *, language=None):
        return Transcript(text=self.text, language="en",
                          seconds_audio=1.0, seconds_compute=0.1)

    def health_check(self):
        return True


class FakeAgent:
    def __init__(self):
        self.heard = []

    def respond(self, text):
        self.heard.append(text)
        return f"reply to: {text}"


class FakeTTS:
    def synthesize(self, intent, out_path):
        from aero.voice.tts import SpeechResult
        return SpeechResult(out_path, 0.1)

    def speak(self, intent):
        from aero.voice.tts import SpeechResult
        return SpeechResult(None, 0.1)

    def health_check(self):
        return True


def _loop(stt):
    return RealtimeLoop(FakeAgent(), stt, FakeTTS())


def test_handle_utterance_transcribes_and_responds():
    loop = _loop(FakeSTT("open the project folder"))
    turn = loop.handle_utterance(_loud() * 20)
    assert isinstance(turn, RealtimeTurn)
    assert turn.ok
    assert turn.heard == "open the project folder"
    assert turn.reply == "reply to: open the project folder"


def test_handle_utterance_rejects_garbled():
    # empty transcript -> looks_garbled -> not ok, agent not called.
    loop = _loop(FakeSTT("   "))
    turn = loop.handle_utterance(_loud() * 20)
    assert turn.ok is False and turn.reply == ""
    assert loop.agent.heard == []              # agent never bothered
