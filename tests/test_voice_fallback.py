"""Voice fallback chain + voice keyring + catalog-routed builders (AERO-VOX-404)."""

from __future__ import annotations

from aero.config import Config
from aero.perception.stt import STTService, Transcript
from aero.voice.fallback import FallbackSTT, FallbackTTS
from aero.voice.speech_intent import SpeechIntent
from aero.voice.tts import SpeechResult, TTSService


class FakeTTS(TTSService):
    def __init__(self, name, *, healthy=True, raise_on_call=False):
        self.voice_name = name
        self._healthy = healthy
        self._raise = raise_on_call
        self.calls = 0

    def synthesize(self, intent, out_path):
        self.calls += 1
        if self._raise:
            raise RuntimeError("engine down")
        return SpeechResult(audio_path=f"{self.voice_name}.wav", seconds_compute=0.1)

    def speak(self, intent):
        return self.synthesize(intent, "x")

    def health_check(self):
        return self._healthy


class FakeSTT(STTService):
    def __init__(self, name, *, healthy=True, raise_on_call=False):
        self.model_name = name
        self._healthy = healthy
        self._raise = raise_on_call

    def transcribe(self, audio_path, *, language=None):
        if self._raise:
            raise RuntimeError("stt down")
        return Transcript(text=self.model_name)

    def health_check(self):
        return self._healthy


INTENT = SpeechIntent("hi")


# -- TTS fallback ----------------------------------------------------------
def test_tts_uses_primary_when_healthy():
    f = FallbackTTS(FakeTTS("cloud"), FakeTTS("local"))
    assert f.synthesize(INTENT, "o").audio_path == "cloud.wav"
    assert f.last_fallback is False


def test_tts_falls_back_when_primary_unhealthy():
    f = FallbackTTS(FakeTTS("cloud", healthy=False), FakeTTS("local"))
    assert f.synthesize(INTENT, "o").audio_path == "local.wav"
    assert f.last_fallback is True


def test_tts_falls_back_when_primary_raises_midcall():
    f = FallbackTTS(FakeTTS("cloud", raise_on_call=True), FakeTTS("local"))
    assert f.synthesize(INTENT, "o").audio_path == "local.wav"
    assert f.last_fallback is True


def test_tts_reset_reprobes():
    primary = FakeTTS("cloud", healthy=False)
    f = FallbackTTS(primary, FakeTTS("local"))
    f.synthesize(INTENT, "o")            # picks local
    assert f.last_fallback is True
    primary._healthy = True
    f.reset()
    assert f.synthesize(INTENT, "o").audio_path == "cloud.wav"
    assert f.last_fallback is False


def test_tts_health_true_if_either_up():
    assert FallbackTTS(FakeTTS("c", healthy=False), FakeTTS("l")).health_check()
    assert not FallbackTTS(FakeTTS("c", healthy=False),
                           FakeTTS("l", healthy=False)).health_check()


# -- STT fallback ----------------------------------------------------------
def test_stt_falls_back():
    f = FallbackSTT(FakeSTT("turbo", healthy=False), FakeSTT("small"))
    assert f.transcribe("a.wav").text == "small"
    assert f.last_fallback is True


def test_stt_primary_raises_midcall():
    f = FallbackSTT(FakeSTT("turbo", raise_on_call=True), FakeSTT("small"))
    assert f.transcribe("a.wav").text == "small"


# -- voice keyring ---------------------------------------------------------
def test_voice_key_roundtrip(monkeypatch):
    from aero.cognition import keys
    from aero.voice.catalog import registry

    class FakeKeyring:
        def __init__(self): self.store = {}
        def get_password(self, s, n): return self.store.get((s, n))
        def set_password(self, s, n, v): self.store[(s, n)] = v
        def delete_password(self, s, n): self.store.pop((s, n), None)

    fake = FakeKeyring()
    monkeypatch.setattr(keys, "_keyring", lambda: fake)
    el = registry()["elevenlabs"]
    assert keys.resolve_voice_key(el) is None            # no key yet
    assert keys.set_voice_key("elevenlabs", "el-secret")
    assert keys.resolve_voice_key(el) == "el-secret"
    assert keys.delete_voice_key("elevenlabs")


def test_voice_key_local_is_none(monkeypatch):
    from aero.cognition import keys
    from aero.voice.catalog import registry
    monkeypatch.setattr(keys, "_keyring", lambda: None)
    assert keys.resolve_voice_key(registry()["kokoro"]) is None  # local, keyless


def test_voice_key_env_fallback(monkeypatch):
    from aero.cognition import keys
    from aero.voice.catalog import registry
    monkeypatch.setattr(keys, "_keyring", lambda: None)
    monkeypatch.setenv("SARVAM_API_KEY", "sv-env")
    assert keys.resolve_voice_key(registry()["sarvam_tts"]) == "sv-env"


# -- catalog-routed builders (behaviour preserved) -------------------------
def test_build_tts_still_selects_by_catalog_id(tmp_path):
    from aero import settings as st
    from aero.voice.tts import SapiTTS
    cfg = Config(home=tmp_path)
    assert isinstance(st.build_tts(cfg), SapiTTS)         # default engine
    s = st.load(cfg); s.engine = "kokoro"; st.save(s, cfg)
    assert type(st.build_tts(cfg)).__name__ == "KokoroTTS"


def test_build_tts_with_fallback_wraps_nonlocal(tmp_path):
    from aero import settings as st
    from aero.voice.fallback import FallbackTTS
    from aero.voice.tts import SapiTTS
    cfg = Config(home=tmp_path)
    # default is SAPI -> no wrap (already the backstop)
    assert isinstance(st.build_tts_with_fallback(cfg), SapiTTS)
    s = st.load(cfg); s.engine = "kokoro"; st.save(s, cfg)
    assert isinstance(st.build_tts_with_fallback(cfg), FallbackTTS)
