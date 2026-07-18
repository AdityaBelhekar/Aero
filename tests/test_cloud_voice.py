"""Cloud voice adapters — ElevenLabs/Sarvam/Cartesia TTS, Deepgram/Sarvam STT.

Hermetic: the one network method per adapter is monkeypatched; tests assert the
request shape and the parsed/written output. No real API calls.
"""

from __future__ import annotations

import base64
import io
import wave

from aero.perception.cloud_stt import DeepgramSTT, SarvamSTT, build_cloud_stt
from aero.voice.cloud_tts import (
    CartesiaTTS,
    ElevenLabsTTS,
    SarvamTTS,
    build_cloud_tts,
)
from aero.voice.speech_intent import SpeechIntent


def _wav_bytes(samples=800, rate=16000):
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(rate)
        w.writeframes(b"\x00\x01" * samples)
    return buf.getvalue()


# -- TTS: health + no-key --------------------------------------------------
def test_tts_unhealthy_without_key():
    assert ElevenLabsTTS(None).health_check() is False
    assert SarvamTTS(None).health_check() is False
    assert CartesiaTTS(None).health_check() is False


def test_tts_synthesize_refuses_without_key(tmp_path):
    r = ElevenLabsTTS(None).synthesize(SpeechIntent("hi"), str(tmp_path / "o.wav"))
    assert not r.ok and "no API key" in r.error


# -- ElevenLabs: pcm -> wav wrap -------------------------------------------
def test_elevenlabs_request_and_wav_output(tmp_path, monkeypatch):
    tts = ElevenLabsTTS("el-key", voice_id="VOICE1", rate=16000)
    seen = {}
    def fake_send(url, headers, data):
        seen["url"] = url; seen["headers"] = headers; seen["data"] = data
        return b"\x00\x01" * 400        # raw PCM16
    monkeypatch.setattr(tts, "_send", fake_send)
    out = tmp_path / "o.wav"
    res = tts.synthesize(SpeechIntent("chal bhai"), str(out))
    assert res.ok
    assert "text-to-speech/VOICE1" in seen["url"] and "pcm_16000" in seen["url"]
    assert seen["headers"]["xi-api-key"] == "el-key"
    assert b"chal bhai" in seen["data"]
    # output is a valid WAV (pcm was wrapped)
    with wave.open(str(out), "rb") as w:
        assert w.getframerate() == 16000


# -- Sarvam TTS: base64 wav ------------------------------------------------
def test_sarvam_tts_decodes_base64(tmp_path, monkeypatch):
    tts = SarvamTTS("sv-key", language="mr-IN", speaker="anushka")
    wav = _wav_bytes()
    def fake_send(url, headers, data):
        assert "text-to-speech" in url
        assert headers["api-subscription-key"] == "sv-key"
        import json
        body = json.loads(data)
        assert body["target_language_code"] == "mr-IN" and body["inputs"] == ["namaskar"]
        return ('{"audios":["' + base64.b64encode(wav).decode() + '"]}').encode()
    monkeypatch.setattr(tts, "_send", fake_send)
    out = tmp_path / "s.wav"
    assert tts.synthesize(SpeechIntent("namaskar"), str(out)).ok
    assert out.read_bytes() == wav


# -- Cartesia --------------------------------------------------------------
def test_cartesia_request_shape(tmp_path, monkeypatch):
    tts = CartesiaTTS("ct-key", voice_id="V", model_id="sonic-2")
    seen = {}
    def fake_send(url, headers, data):
        seen["url"] = url; seen["headers"] = headers
        import json
        seen["body"] = json.loads(data)
        return _wav_bytes()
    monkeypatch.setattr(tts, "_send", fake_send)
    assert tts.synthesize(SpeechIntent("yo"), str(tmp_path / "c.wav")).ok
    assert seen["url"].endswith("/tts/bytes")
    assert seen["headers"]["X-API-Key"] == "ct-key" and "Cartesia-Version" in seen["headers"]
    assert seen["body"]["voice"] == {"mode": "id", "id": "V"}
    assert seen["body"]["output_format"]["container"] == "wav"


def test_build_cloud_tts_dispatch():
    assert isinstance(build_cloud_tts("elevenlabs", "k"), ElevenLabsTTS)
    assert isinstance(build_cloud_tts("sarvam", "k"), SarvamTTS)
    assert isinstance(build_cloud_tts("cartesia", "k"), CartesiaTTS)


# -- STT: Deepgram ---------------------------------------------------------
def test_deepgram_parses_transcript(tmp_path, monkeypatch):
    audio = tmp_path / "a.wav"; audio.write_bytes(_wav_bytes())
    stt = DeepgramSTT("dg-key", model="nova-2")
    seen = {}
    def fake_send(url, headers, data):
        seen["url"] = url; seen["headers"] = headers
        return {"results": {"channels": [{"alternatives": [
            {"transcript": "bhai deadline kal aahe"}]}]}}
    monkeypatch.setattr(stt, "_send", fake_send)
    t = stt.transcribe(str(audio), language="en")
    assert t.text == "bhai deadline kal aahe"
    assert "model=nova-2" in seen["url"] and "language=en" in seen["url"]
    assert seen["headers"]["Authorization"] == "Token dg-key"


def test_deepgram_empty_without_key(tmp_path):
    audio = tmp_path / "a.wav"; audio.write_bytes(_wav_bytes())
    assert DeepgramSTT(None).transcribe(str(audio)).text == ""
    assert DeepgramSTT(None).health_check() is False


# -- STT: Sarvam (multipart) -----------------------------------------------
def test_sarvam_stt_multipart_and_parse(tmp_path, monkeypatch):
    audio = tmp_path / "clip.wav"; audio.write_bytes(_wav_bytes())
    stt = SarvamSTT("sv-key")
    seen = {}
    def fake_send(url, headers, data):
        seen["url"] = url; seen["ctype"] = headers["Content-Type"]; seen["data"] = data
        return {"transcript": "mala vatat", "language_code": "mr-IN"}
    monkeypatch.setattr(stt, "_send", fake_send)
    t = stt.transcribe(str(audio))
    assert t.text == "mala vatat" and t.language == "mr-IN"
    assert "speech-to-text-translate" in seen["url"]
    assert seen["ctype"].startswith("multipart/form-data; boundary=")
    assert b'filename="clip.wav"' in seen["data"] and b"saaras:v2" in seen["data"]


def test_build_cloud_stt_dispatch():
    assert isinstance(build_cloud_stt("deepgram", "k"), DeepgramSTT)
    assert isinstance(build_cloud_stt("sarvam", "k"), SarvamSTT)
