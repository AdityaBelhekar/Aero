"""Svara-TTS backend + settings tests — hermetic (HTTP layer mocked)."""

from __future__ import annotations

from pathlib import Path

from aero.config import Config
from aero.voice.speech_intent import SpeechIntent
from aero.voice.svara_tts import SvaraTTS, describe_voice, voices


def test_38_voice_profiles():
    vs = voices()
    assert len(vs) == 38
    assert "hi_male" in vs and "mr_male" in vs and "en_female" in vs
    # each language has exactly male + female
    assert vs.count("hi_male") == 1 and vs.count("hi_female") == 1


def test_describe_voice():
    assert describe_voice("hi_male") == "Hindi (male)"
    assert describe_voice("mr_female") == "Marathi (female)"
    assert describe_voice("en_male") == "Indian English (male)"


def test_synthesize_posts_and_writes(tmp_path, monkeypatch):
    captured = {}

    def fake_request(text, out_path):
        captured["text"] = text
        Path(out_path).write_bytes(b"RIFFfake-wav-bytes")

    tts = SvaraTTS("hi_male")
    monkeypatch.setattr(tts, "_speech_request", fake_request)
    out = tmp_path / "o.wav"
    res = tts.synthesize(SpeechIntent.neutral("chal bhai"), str(out))
    assert res.ok
    assert captured["text"] == "chal bhai"
    assert out.read_bytes().startswith(b"RIFF")


def test_synthesize_reports_server_down(tmp_path, monkeypatch):
    def boom(text, out_path):
        raise OSError("connection refused")

    tts = SvaraTTS("hi_male")
    monkeypatch.setattr(tts, "_speech_request", boom)
    res = tts.synthesize(SpeechIntent.neutral("x"), str(tmp_path / "o.wav"))
    assert res.ok is False
    assert "connection refused" in res.error


def test_set_voice():
    tts = SvaraTTS("hi_male")
    tts.set_voice("mr_male")
    assert tts.voice_name == "mr_male"


# -- settings persistence --------------------------------------------------
def test_settings_roundtrip(tmp_path):
    from aero import settings as st
    cfg = Config(home=tmp_path)
    s = st.load(cfg)
    assert s.engine == "sapi"  # default
    s.engine = "svara"
    s.svara_voice = "mr_male"
    st.save(s, cfg)
    reloaded = st.load(cfg)
    assert reloaded.engine == "svara"
    assert reloaded.svara_voice == "mr_male"


def test_build_tts_selects_engine(tmp_path):
    from aero import settings as st
    from aero.voice.svara_tts import SvaraTTS as _Svara
    from aero.voice.tts import SapiTTS
    cfg = Config(home=tmp_path)
    assert isinstance(st.build_tts(cfg), SapiTTS)   # default
    s = st.load(cfg); s.engine = "svara"; s.svara_voice = "hi_male"; st.save(s, cfg)
    built = st.build_tts(cfg)
    assert isinstance(built, _Svara)
    assert built.voice_name == "hi_male"
