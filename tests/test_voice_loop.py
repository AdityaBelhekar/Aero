"""Voice-loop tests — hermetic. Fake STT/agent/TTS; no audio, no models."""

from __future__ import annotations

from aero.perception.stt import STTService, Transcript
from aero.voice.loop import VoiceLoop, looks_garbled
from aero.voice.speech_intent import intent_from_text
from aero.voice.tts import TTSService, SpeechResult


class FakeSTT(STTService):
    def __init__(self, transcript: Transcript):
        self.model_name = "fake"
        self._t = transcript

    def transcribe(self, audio_path, *, language=None):
        return self._t

    def health_check(self):
        return True


class FakeTTS(TTSService):
    def __init__(self):
        self.voice_name = "fake"
        self.spoken = []

    def synthesize(self, intent, out_path):
        return SpeechResult(out_path, 0.0)

    def speak(self, intent):
        self.spoken.append(intent.text)
        return SpeechResult(None, 0.0)

    def health_check(self):
        return True


class FakeAgent:
    def __init__(self):
        self.heard = []

    def respond(self, text):
        self.heard.append(text)
        return f"reply to: {text}"


def _loop(transcript=None, tts=None):
    return VoiceLoop(FakeAgent(),
                     FakeSTT(transcript or Transcript(text="hi")),
                     tts or FakeTTS())


def test_garbled_guard():
    assert looks_garbled(Transcript(text="")) is True
    assert looks_garbled(Transcript(text="x" * 500, seconds_audio=2.0)) is True  # 250 c/s
    assert looks_garbled(Transcript(text="bhai kaisa hai", seconds_audio=3.0)) is False


def test_handle_text_routes_through_agent_and_tts():
    tts = FakeTTS()
    loop = _loop(tts=tts)
    turn = loop.handle_text("bhai coffee kasa", speak=True)
    assert turn.reply == "reply to: bhai coffee kasa"
    assert tts.spoken == ["reply to: bhai coffee kasa"]


def test_handle_text_can_stay_silent():
    tts = FakeTTS()
    loop = _loop(tts=tts)
    loop.handle_text("hi", speak=False)
    assert tts.spoken == []


def test_handle_wav_transcribes_then_responds():
    loop = _loop(transcript=Transcript(text="mala coffee havi", seconds_audio=2.0))
    turn = loop.handle_wav("x.wav", speak=False)
    assert turn.ok
    assert turn.heard == "mala coffee havi"
    assert "reply to: mala coffee havi" == turn.reply


def test_handle_wav_rejects_garbled():
    loop = _loop(transcript=Transcript(text="", seconds_audio=2.0))
    turn = loop.handle_wav("x.wav", speak=False)
    assert turn.ok is False
    assert turn.reply == ""


def test_intent_from_text_varies():
    assert intent_from_text("okay that was clean!").energy > 0.7
    assert intent_from_text("i think we approached this backwards...").trailing > 0.5
    neutral = intent_from_text("haan theek hai")
    assert 0.4 < neutral.energy < 0.7
