"""Voice tests — SSML rendering is hermetic; SAPI synth is Windows-guarded."""

from __future__ import annotations

import sys

import pytest

from aero.voice.speech_intent import SpeechIntent, render_ssml
from aero.voice.tts import SapiTTS


def test_ssml_is_wellformed_and_has_prosody():
    ssml = render_ssml(SpeechIntent.neutral("hello there"))
    assert ssml.startswith("<speak")
    assert "<prosody" in ssml and "hello there" in ssml
    # parseable XML
    import xml.dom.minidom as m
    m.parseString(ssml)


def test_tone_presets_shift_delivery():
    excited = render_ssml(SpeechIntent.from_tone("lets go", "excited"))
    low = render_ssml(SpeechIntent.from_tone("lets go", "low"))
    # excited is faster and higher-pitched; low is calmer/lower-pitched
    assert "x-fast" in excited or "fast" in excited
    assert "pitch=\"+" in excited     # raised pitch
    assert "pitch=\"-" in low         # lowered pitch


def test_pause_before_becomes_break():
    intent = SpeechIntent(text="okay that was clean", pause_before_ms=600)
    ssml = render_ssml(intent)
    assert "<break time=\"600ms\"/>" in ssml


def test_trailing_adds_ellipsis_break():
    intent = SpeechIntent(text="i think we approached this backwards", trailing=0.8)
    ssml = render_ssml(intent)
    assert "..." in ssml and "<break" in ssml


def test_emphasis_wraps_words():
    intent = SpeechIntent(text="we are not doing that", emphasis_words=["not"])
    ssml = render_ssml(intent)
    assert "<emphasis" in ssml


def test_text_is_xml_escaped():
    ssml = render_ssml(SpeechIntent.neutral("me & you < everyone"))
    assert "&amp;" in ssml and "&lt;" in ssml


def test_carried_fields_do_not_crash_rendering():
    # affective fields nudge knobs but must never break SSML
    intent = SpeechIntent(text="hmm", sarcasm=0.9, amusement=0.9, concern=0.9,
                          hesitation=0.9, laugh_intensity=0.9, certainty=0.1)
    import xml.dom.minidom as m
    m.parseString(render_ssml(intent))


def test_sapi_health_matches_platform():
    assert SapiTTS().health_check() == (sys.platform == "win32")


@pytest.mark.skipif(sys.platform != "win32", reason="SAPI is Windows-only")
def test_sapi_synthesizes_wav(tmp_path):
    out = tmp_path / "s.wav"
    res = SapiTTS().synthesize(SpeechIntent.from_tone("testing one two", "serious"), str(out))
    assert res.ok, res.error
    assert out.exists() and out.stat().st_size > 1000
