"""AI4Bharat backends (IndicConformer STT + Indic Parler-TTS) — hermetic tests.

The heavy models (NeMo / parler_tts) are mocked exactly like test_svara mocks the
HTTP layer, so these run with zero downloads and no optional deps installed.
"""

from __future__ import annotations

import wave
from pathlib import Path

import pytest

from aero.config import Config
from aero.perception.indic_stt import IndicConformerSTT, build_stt
from aero.perception.stt import FasterWhisperBackend
from aero.voice.parler_tts import (AERO_BASE_VOICE, ParlerTTS,
                                    _intent_to_description)
from aero.voice.speech_intent import SpeechIntent


def _tiny_wav(path: Path, seconds: float = 0.5, rate: int = 16000) -> Path:
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(b"\x00\x00" * int(seconds * rate))
    return path


# -- IndicConformer STT ----------------------------------------------------
class _FakeNemoModel:
    def __init__(self, out="नमस्ते जग"):
        self.out = out
        self.cur_decoder = None
        self.last_kwargs = None

    def transcribe(self, paths, **kwargs):
        self.last_kwargs = kwargs
        return [self.out]


def test_decoder_validation():
    with pytest.raises(ValueError):
        IndicConformerSTT(decoder="beam")
    IndicConformerSTT(decoder="ctc")   # ok
    IndicConformerSTT(decoder="rnnt")  # ok


def test_health_check_false_without_nemo():
    # NeMo is not installed in the main test env -> health_check is False.
    assert IndicConformerSTT().health_check() is False


def test_transcribe_wiring(tmp_path, monkeypatch):
    wav = _tiny_wav(tmp_path / "a.wav", seconds=0.5)
    fake = _FakeNemoModel("मी ठीक आहे")
    stt = IndicConformerSTT(decoder="rnnt", language_id="mr")
    monkeypatch.setattr(stt, "_ensure_model", lambda: fake)

    t = stt.transcribe(str(wav))
    assert t.text == "मी ठीक आहे"
    assert t.language == "mr"
    assert abs(t.seconds_audio - 0.5) < 0.01     # duration read from the WAV
    assert fake.cur_decoder == "rnnt"            # decoder pushed to the model
    assert fake.last_kwargs.get("language_id") == "mr"


def test_transcribe_handles_hypothesis_object(tmp_path, monkeypatch):
    wav = _tiny_wav(tmp_path / "a.wav")

    class Hyp:  # NeMo sometimes returns objects with a .text attr, not str
        text = "  hello जग  "

    class M(_FakeNemoModel):
        def transcribe(self, paths, **kwargs):
            return [Hyp()]

    stt = IndicConformerSTT()
    monkeypatch.setattr(stt, "_ensure_model", lambda: M())
    assert stt.transcribe(str(wav)).text == "hello जग"


def test_language_override_is_restored(tmp_path, monkeypatch):
    wav = _tiny_wav(tmp_path / "a.wav")
    fake = _FakeNemoModel()
    stt = IndicConformerSTT(language_id="mr")
    monkeypatch.setattr(stt, "_ensure_model", lambda: fake)
    stt.transcribe(str(wav), language="hi")
    assert fake.last_kwargs.get("language_id") == "hi"  # used the override
    assert stt.language_id == "mr"                       # but restored after


def test_build_stt_factory():
    assert isinstance(build_stt("indic"), IndicConformerSTT)
    assert isinstance(build_stt("small"), FasterWhisperBackend)


# -- Indic Parler-TTS ------------------------------------------------------
def test_intent_to_description_neutral_is_base():
    assert _intent_to_description(SpeechIntent.neutral("hi")) == AERO_BASE_VOICE


def test_intent_to_description_maps_delivery():
    d = _intent_to_description(SpeechIntent(text="x", energy=0.9, pace=0.8,
                                            emotional_tone="amused"))
    assert "animated" in d and "quick" in d and "amused" in d
    calm = _intent_to_description(SpeechIntent(text="x", energy=0.2, pace=0.3))
    assert "calm" in calm and "slowly" in calm


def test_synthesize_renders_and_passes_description(tmp_path, monkeypatch):
    captured = {}

    def fake_render(text, description, out_path):
        captured["text"] = text
        captured["description"] = description
        Path(out_path).write_bytes(b"RIFFfake")

    tts = ParlerTTS()
    monkeypatch.setattr(tts, "_render", fake_render)
    out = tmp_path / "o.wav"
    res = tts.synthesize(SpeechIntent(text="chal bhai", energy=0.9), str(out))
    assert res.ok
    assert captured["text"] == "chal bhai"
    assert "animated" in captured["description"]
    assert out.read_bytes().startswith(b"RIFF")


def test_synthesize_reports_failure(tmp_path, monkeypatch):
    def boom(text, description, out_path):
        raise RuntimeError("model OOM")

    tts = ParlerTTS()
    monkeypatch.setattr(tts, "_render", boom)
    res = tts.synthesize(SpeechIntent.neutral("x"), str(tmp_path / "o.wav"))
    assert res.ok is False
    assert "model OOM" in res.error


def test_parler_health_check_false_without_deps():
    assert ParlerTTS().health_check() is False


# -- settings wiring -------------------------------------------------------
def test_settings_parler_and_stt_roundtrip(tmp_path):
    from aero import settings as st
    cfg = Config(home=tmp_path)
    s = st.load(cfg)
    assert s.engine == "sapi" and s.stt_model == "small"  # defaults
    s.engine = "parler"
    s.stt_model = "indic"
    st.save(s, cfg)
    r = st.load(cfg)
    assert r.engine == "parler" and r.stt_model == "indic"


def test_build_tts_selects_parler(tmp_path):
    from aero import settings as st
    cfg = Config(home=tmp_path)
    s = st.load(cfg); s.engine = "parler"; st.save(s, cfg)
    assert isinstance(st.build_tts(cfg), ParlerTTS)


def test_build_stt_from_settings(tmp_path):
    from aero import settings as st
    cfg = Config(home=tmp_path)
    s = st.load(cfg); s.stt_model = "indic"; st.save(s, cfg)
    assert isinstance(st.build_stt(cfg), IndicConformerSTT)
    assert isinstance(st.build_stt(cfg, model="small"), FasterWhisperBackend)
