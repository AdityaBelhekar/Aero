"""Cloud STT adapters — Deepgram, Sarvam (Saaras) (AERO-VOX-402).

Same ``STTService`` interface as the local Whisper/Moonshine/Indic backends, so
they drop into the voice catalog and behind ``FallbackSTT``. Keys resolve from the
``aero-voice`` keyring (or env); keyless -> unhealthy -> fallback to a local model.

Written to each API's documented shape; the single network method is isolated so
request shaping is unit-tested. Not run live here — a key + one real clip is the
remaining step.
"""

from __future__ import annotations

import json
import time
import urllib.request
import uuid
from pathlib import Path

from aero.perception.stt import STTService, Transcript

_CTYPE = {".wav": "audio/wav", ".mp3": "audio/mpeg", ".m4a": "audio/mp4",
          ".flac": "audio/flac", ".ogg": "audio/ogg", ".webm": "audio/webm"}


def _content_type(path: str) -> str:
    return _CTYPE.get(Path(path).suffix.lower(), "audio/wav")


def _audio_seconds(path: str) -> float:
    try:
        import wave
        with wave.open(path, "rb") as w:
            return w.getnframes() / float(w.getframerate() or 1)
    except Exception:
        return 0.0


class DeepgramSTT(STTService):
    model_name = "deepgram-nova"

    def __init__(self, api_key=None, *, model="nova-2",
                 base_url="https://api.deepgram.com/v1", timeout: float = 60.0):
        self.api_key = api_key
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def _send(self, url: str, headers: dict, data: bytes) -> dict:
        req = urllib.request.Request(url, data=data, headers=headers, method="POST")
        with urllib.request.urlopen(req, timeout=self.timeout) as r:
            return json.loads(r.read().decode("utf-8"))

    def transcribe(self, audio_path: str, *, language: str | None = None) -> Transcript:
        if not self.api_key:
            return Transcript(text="", language=language)
        from urllib.parse import urlencode
        params = {"model": self.model, "smart_format": "true"}
        if language:
            params["language"] = language
        url = f"{self.base_url}/listen?{urlencode(params)}"
        headers = {"Authorization": f"Token {self.api_key}",
                   "Content-Type": _content_type(audio_path)}
        t0 = time.perf_counter()
        raw = self._send(url, headers, Path(audio_path).read_bytes())
        elapsed = time.perf_counter() - t0
        alt = (raw.get("results", {}).get("channels", [{}])[0]
               .get("alternatives", [{}])[0])
        return Transcript(text=alt.get("transcript", "") or "", language=language,
                          seconds_audio=_audio_seconds(audio_path),
                          seconds_compute=elapsed)

    def health_check(self) -> bool:
        return bool(self.api_key)


class SarvamSTT(STTService):
    """Sarvam Saaras — speech-to-text-translate, best code-switch (Indic)."""

    model_name = "sarvam-saaras"

    def __init__(self, api_key=None, *, model="saaras:v2",
                 base_url="https://api.sarvam.ai", timeout: float = 60.0):
        self.api_key = api_key
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def _multipart(self, audio_path: str, fields: dict) -> tuple[bytes, str]:
        boundary = uuid.uuid4().hex
        parts: list[bytes] = []
        for k, v in fields.items():
            parts.append(f"--{boundary}\r\nContent-Disposition: form-data; "
                         f"name=\"{k}\"\r\n\r\n{v}\r\n".encode())
        fname = Path(audio_path).name
        parts.append(f"--{boundary}\r\nContent-Disposition: form-data; "
                     f"name=\"file\"; filename=\"{fname}\"\r\n"
                     f"Content-Type: {_content_type(audio_path)}\r\n\r\n".encode())
        parts.append(Path(audio_path).read_bytes())
        parts.append(f"\r\n--{boundary}--\r\n".encode())
        return b"".join(parts), boundary

    def _send(self, url: str, headers: dict, data: bytes) -> dict:
        req = urllib.request.Request(url, data=data, headers=headers, method="POST")
        with urllib.request.urlopen(req, timeout=self.timeout) as r:
            return json.loads(r.read().decode("utf-8"))

    def transcribe(self, audio_path: str, *, language: str | None = None) -> Transcript:
        if not self.api_key:
            return Transcript(text="", language=language)
        body, boundary = self._multipart(audio_path, {"model": self.model})
        url = f"{self.base_url}/speech-to-text-translate"
        headers = {"api-subscription-key": self.api_key,
                   "Content-Type": f"multipart/form-data; boundary={boundary}"}
        t0 = time.perf_counter()
        raw = self._send(url, headers, body)
        return Transcript(text=raw.get("transcript", "") or "",
                          language=raw.get("language_code") or language,
                          seconds_audio=_audio_seconds(audio_path),
                          seconds_compute=time.perf_counter() - t0)

    def health_check(self) -> bool:
        return bool(self.api_key)


def build_cloud_stt(backend: str, api_key: str | None):
    if backend == "deepgram":
        return DeepgramSTT(api_key)
    if backend == "sarvam":
        return SarvamSTT(api_key)
    raise ValueError(f"unknown cloud STT backend: {backend}")
