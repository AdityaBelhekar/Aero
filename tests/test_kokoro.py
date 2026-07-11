"""Kokoro TTS backend — hermetic tests (model + soundfile mocked)."""

from __future__ import annotations

from pathlib import Path

from aero.config import Config
from aero.voice.kokoro_tts import (DEFAULT_VOICE, KOKORO_VOICES, KokoroTTS,
                                   _intent_to_speed)
from aero.voice.speech_intent import SpeechIntent


def test_intent_to_speed_maps_pace():
    neutral = _intent_to_speed(SpeechIntent.neutral("x"))
    slow = _intent_to_speed(SpeechIntent(text="x", pace=0.0, energy=0.5))
    fast = _intent_to_speed(SpeechIntent(text="x", pace=1.0, energy=0.5))
    assert slow < neutral < fast
    assert 0.7 <= slow and fast <= 1.4          # clamped to Kokoro's sane range


def test_synthesize_renders_with_voice_and_speed(tmp_path, monkeypatch):
    captured = {}

    def fake_render(text, voice, speed, out_path):
        captured.update(text=text, voice=voice, speed=speed)
        Path(out_path).write_bytes(b"RIFFkokoro")

    tts = KokoroTTS("am_adam")
    monkeypatch.setattr(tts, "_render", fake_render)
    out = tmp_path / "o.wav"
    res = tts.synthesize(SpeechIntent(text="hey Aditya", pace=0.9), str(out))
    assert res.ok
    assert captured["text"] == "hey Aditya"
    assert captured["voice"] == "am_adam"
    assert captured["speed"] > 1.0              # fast pace -> faster speed
    assert out.read_bytes().startswith(b"RIFF")


def test_synthesize_reports_failure(tmp_path, monkeypatch):
    def boom(text, voice, speed, out_path):
        raise RuntimeError("missing model file")

    tts = KokoroTTS()
    monkeypatch.setattr(tts, "_render", boom)
    res = tts.synthesize(SpeechIntent.neutral("x"), str(tmp_path / "o.wav"))
    assert res.ok is False and "missing model file" in res.error


def test_health_check_false_without_model_files(tmp_path):
    # Point at non-existent files -> health_check is False even if pkg present.
    tts = KokoroTTS(model_path=tmp_path / "no.onnx", voices_path=tmp_path / "no.bin")
    assert tts.health_check() is False


def test_set_voice():
    tts = KokoroTTS()
    assert tts.voice_name == DEFAULT_VOICE
    tts.set_voice("bm_george")
    assert tts.voice_name == "bm_george"


def test_voice_catalog_has_male_voices():
    assert "am_michael" in KOKORO_VOICES and "bm_george" in KOKORO_VOICES
    assert DEFAULT_VOICE in KOKORO_VOICES


# -- settings wiring -------------------------------------------------------
def test_settings_kokoro_roundtrip(tmp_path):
    from aero import settings as st
    cfg = Config(home=tmp_path)
    s = st.load(cfg)
    s.engine = "kokoro"; s.kokoro_voice = "bm_george"
    st.save(s, cfg)
    r = st.load(cfg)
    assert r.engine == "kokoro" and r.kokoro_voice == "bm_george"


def test_build_tts_selects_kokoro(tmp_path):
    from aero import settings as st
    cfg = Config(home=tmp_path)
    s = st.load(cfg); s.engine = "kokoro"; s.kokoro_voice = "am_michael"; st.save(s, cfg)
    built = st.build_tts(cfg)
    assert isinstance(built, KokoroTTS)
    assert built.voice_name == "am_michael"
