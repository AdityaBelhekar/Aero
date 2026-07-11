"""Moonshine STT backend — hermetic tests (moonshine_onnx module mocked)."""

from __future__ import annotations

import sys
import types
import wave

from aero.perception.indic_stt import build_stt
from aero.perception.moonshine_stt import MoonshineSTT
from aero.perception.stt import FasterWhisperBackend


def _tiny_wav(path, seconds=0.5, rate=16000):
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(b"\x00\x00" * int(seconds * rate))
    return path


def _fake_moonshine(monkeypatch, out):
    mod = types.ModuleType("moonshine_onnx")
    calls = {}

    def transcribe(path, model):
        calls["path"] = path
        calls["model"] = model
        return out

    mod.transcribe = transcribe
    monkeypatch.setitem(sys.modules, "moonshine_onnx", mod)
    return calls


def test_transcribe_list_result(tmp_path, monkeypatch):
    wav = _tiny_wav(tmp_path / "a.wav", seconds=0.5)
    calls = _fake_moonshine(monkeypatch, ["hey Aditya, opening the code now"])
    stt = MoonshineSTT("moonshine/base")
    t = stt.transcribe(str(wav))
    assert t.text == "hey Aditya, opening the code now"
    assert t.language == "en"
    assert abs(t.seconds_audio - 0.5) < 0.01
    assert calls["model"] == "moonshine/base"


def test_transcribe_tolerates_bare_string(tmp_path, monkeypatch):
    wav = _tiny_wav(tmp_path / "a.wav")
    _fake_moonshine(monkeypatch, "  plain string result  ")
    assert MoonshineSTT().transcribe(str(wav)).text == "plain string result"


def test_transcribe_empty_list(tmp_path, monkeypatch):
    wav = _tiny_wav(tmp_path / "a.wav")
    _fake_moonshine(monkeypatch, [])
    assert MoonshineSTT().transcribe(str(wav)).text == ""


def test_health_check_false_without_pkg(monkeypatch):
    monkeypatch.setitem(sys.modules, "moonshine_onnx", None)  # import -> error
    assert MoonshineSTT().health_check() is False


def test_build_stt_factory_routes_moonshine():
    assert isinstance(build_stt("moonshine"), MoonshineSTT)
    assert build_stt("moonshine").model_name == "moonshine/base"   # default arch
    assert build_stt("moonshine/tiny").model_name == "moonshine/tiny"
    assert isinstance(build_stt("small"), FasterWhisperBackend)    # unchanged


def test_settings_stt_model_moonshine(tmp_path):
    from aero import settings as st
    from aero.config import Config
    cfg = Config(home=tmp_path)
    s = st.load(cfg); s.stt_model = "moonshine/tiny"; st.save(s, cfg)
    built = st.build_stt(cfg)
    assert isinstance(built, MoonshineSTT) and built.model_name == "moonshine/tiny"
