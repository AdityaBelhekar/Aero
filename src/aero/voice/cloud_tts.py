"""Cloud TTS adapters — ElevenLabs, Sarvam (Bulbul), Cartesia (AERO-VOX-402).

Each implements the same ``TTSService`` interface as the local engines, so they're
drop-in in the voice catalog and behind the fallback chain. Keys resolve from the
``aero-voice`` keyring (or an env var); a keyless adapter reports unhealthy, so
``FallbackTTS`` degrades to a local voice automatically.

The single network method (``_send``) is isolated per adapter so the request
shaping is unit-tested without hitting the provider. These are written to each
API's documented shape but have NOT been run live here — a key + one real call is
the remaining step.
"""

from __future__ import annotations

import base64
import io
import json
import time
import urllib.request
import wave
from pathlib import Path

from aero.voice.speech_intent import SpeechIntent
from aero.voice.tts import SpeechResult, TTSService


def _pcm16_to_wav(pcm: bytes, rate: int, channels: int = 1) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(channels)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(pcm)
    return buf.getvalue()


def play_wav(path: str) -> None:
    """Best-effort cross-platform playback (used by speak())."""
    import shutil
    import subprocess
    import sys
    try:
        if sys.platform == "win32":
            import winsound
            winsound.PlaySound(path, winsound.SND_FILENAME)
            return
        for player in ("afplay", "ffplay", "aplay", "paplay"):
            exe = shutil.which(player)
            if exe:
                args = [exe, "-nodisp", "-autoexit", path] if player == "ffplay" \
                    else [exe, path]
                subprocess.run(args, capture_output=True, timeout=120)
                return
    except Exception:
        pass


class _CloudTTS(TTSService):
    """Shared plumbing: write bytes, play, health from key presence."""

    def __init__(self, api_key: str | None, voice_name: str, *, timeout: float = 60.0):
        self.api_key = api_key
        self.voice_name = voice_name
        self.timeout = timeout

    def _send(self, url: str, headers: dict, data: bytes) -> bytes:
        req = urllib.request.Request(url, data=data, headers=headers, method="POST")
        with urllib.request.urlopen(req, timeout=self.timeout) as r:
            return r.read()

    # subclasses implement: _audio_for(text) -> bytes (a WAV)
    def _audio_for(self, text: str) -> bytes:  # pragma: no cover - overridden
        raise NotImplementedError

    def synthesize(self, intent: SpeechIntent, out_path: str) -> SpeechResult:
        if not self.api_key:
            return SpeechResult(None, 0.0, ok=False, error="no API key")
        t0 = time.perf_counter()
        try:
            audio = self._audio_for(intent.text)
            Path(out_path).write_bytes(audio)
        except Exception as e:
            return SpeechResult(None, time.perf_counter() - t0, ok=False, error=str(e))
        return SpeechResult(out_path, time.perf_counter() - t0)

    def speak(self, intent: SpeechIntent) -> SpeechResult:
        import tempfile
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            wav = f.name
        res = self.synthesize(intent, wav)
        if res.ok:
            play_wav(wav)
        try:
            Path(wav).unlink()
        except OSError:
            pass
        return res

    def health_check(self) -> bool:
        return bool(self.api_key)


class ElevenLabsTTS(_CloudTTS):
    def __init__(self, api_key=None, *, voice_id="21m00Tcm4TlvDq8ikWAM",
                 model_id="eleven_multilingual_v2",
                 base_url="https://api.elevenlabs.io/v1", rate=16000):
        super().__init__(api_key, voice_id)
        self.voice_id = voice_id
        self.model_id = model_id
        self.base_url = base_url.rstrip("/")
        self.rate = rate

    def _audio_for(self, text: str) -> bytes:
        url = (f"{self.base_url}/text-to-speech/{self.voice_id}"
               f"?output_format=pcm_{self.rate}")
        headers = {"xi-api-key": self.api_key, "Content-Type": "application/json"}
        body = json.dumps({"text": text, "model_id": self.model_id}).encode("utf-8")
        pcm = self._send(url, headers, body)     # raw PCM16
        return _pcm16_to_wav(pcm, self.rate)


class SarvamTTS(_CloudTTS):
    """Sarvam Bulbul — Indic-native, code-switch. Returns base64 WAV."""

    def __init__(self, api_key=None, *, speaker="anushka", language="hi-IN",
                 model="bulbul:v2", base_url="https://api.sarvam.ai"):
        super().__init__(api_key, speaker)
        self.speaker = speaker
        self.language = language
        self.model = model
        self.base_url = base_url.rstrip("/")

    def _audio_for(self, text: str) -> bytes:
        url = f"{self.base_url}/text-to-speech"
        headers = {"api-subscription-key": self.api_key,
                   "Content-Type": "application/json"}
        body = json.dumps({"inputs": [text], "target_language_code": self.language,
                           "speaker": self.speaker, "model": self.model}).encode("utf-8")
        raw = json.loads(self._send(url, headers, body).decode("utf-8"))
        audios = raw.get("audios") or []
        if not audios:
            raise RuntimeError(f"sarvam returned no audio: {raw}")
        return base64.b64decode(audios[0])       # already a WAV


class CartesiaTTS(_CloudTTS):
    def __init__(self, api_key=None, *, voice_id="a0e99841-438c-4a64-b679-ae501e7d6091",
                 model_id="sonic-2", base_url="https://api.cartesia.ai",
                 version="2024-06-10", rate=16000):
        super().__init__(api_key, voice_id)
        self.voice_id = voice_id
        self.model_id = model_id
        self.base_url = base_url.rstrip("/")
        self.version = version
        self.rate = rate

    def _audio_for(self, text: str) -> bytes:
        url = f"{self.base_url}/tts/bytes"
        headers = {"X-API-Key": self.api_key, "Cartesia-Version": self.version,
                   "Content-Type": "application/json"}
        body = json.dumps({
            "model_id": self.model_id, "transcript": text,
            "voice": {"mode": "id", "id": self.voice_id},
            "output_format": {"container": "wav", "encoding": "pcm_s16le",
                              "sample_rate": self.rate},
        }).encode("utf-8")
        return self._send(url, headers, body)     # WAV bytes


class GoogleTTS(_CloudTTS):
    """Google Cloud Text-to-Speech (Neural2/WaveNet). Auth via the X-goog-api-key
    header (no key in the URL). LINEAR16 audio, wrapped to WAV if needed."""

    def __init__(self, api_key=None, *, voice="en-US-Neural2-D", language="en-US",
                 base_url="https://texttospeech.googleapis.com/v1", rate=16000):
        super().__init__(api_key, voice)
        self.voice = voice
        self.language = language
        self.base_url = base_url.rstrip("/")
        self.rate = rate

    def _audio_for(self, text: str) -> bytes:
        url = f"{self.base_url}/text:synthesize"
        headers = {"X-goog-api-key": self.api_key, "Content-Type": "application/json"}
        body = json.dumps({
            "input": {"text": text},
            "voice": {"languageCode": self.language, "name": self.voice},
            "audioConfig": {"audioEncoding": "LINEAR16", "sampleRateHertz": self.rate},
        }).encode("utf-8")
        raw = json.loads(self._send(url, headers, body).decode("utf-8"))
        content = raw.get("audioContent")
        if not content:
            raise RuntimeError(f"google tts returned no audio: {raw}")
        audio = base64.b64decode(content)
        # LINEAR16 comes back as a WAV (RIFF) already; wrap only if it's bare PCM.
        return audio if audio[:4] == b"RIFF" else _pcm16_to_wav(audio, self.rate)


def build_cloud_tts(backend: str, api_key: str | None, *, voice: str | None = None):
    """Construct a cloud TTS adapter by catalog backend key."""
    if backend == "elevenlabs":
        return ElevenLabsTTS(api_key, **({"voice_id": voice} if voice else {}))
    if backend == "sarvam":
        return SarvamTTS(api_key, **({"speaker": voice} if voice else {}))
    if backend == "cartesia":
        return CartesiaTTS(api_key, **({"voice_id": voice} if voice else {}))
    if backend == "google":
        return GoogleTTS(api_key, **({"voice": voice} if voice else {}))
    raise ValueError(f"unknown cloud TTS backend: {backend}")
