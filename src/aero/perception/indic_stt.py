"""AI4Bharat IndicConformer STT — Aero's Indic-specialised ear (spike S-3 follow-up).

The default Whisper backend (`stt.FasterWhisperBackend`) comprehends Aditya's
code-switched speech but pays ~1.5x realtime on CPU. This backend swaps in
AI4Bharat's IndicConformer (``indicconformer_stt_mr_hybrid_ctc_rnnt_large``) — a
120M-param Conformer trained on Indian languages, with a hybrid CTC/RNNT head so
you can trade accuracy (RNNT) for speed (CTC). Marathi-first, Devanagari output,
which gemma4 reads natively downstream.

It runs on NVIDIA **NeMo** (``nemo.collections.asr``), an optional heavy
dependency. Importing this module never requires NeMo — only constructing and
using the backend does, exactly like ``faster_whisper`` in the Whisper backend.
Kept behind the same ``STTService`` interface so `aero voice --stt indic` and the
S-3 probe select it with no caller changes.

Benchmark before adopting: run ``spikes/s3_stt_probe.py --backend indic`` against
Aditya's 10 real clips and judge by *reading the outputs* (WER vs Devanagari is
misleading — see spikes/S3_VERDICT.md), plus RTF (< 1.0 for live voice).
"""

from __future__ import annotations

import contextlib
import time
import wave
from pathlib import Path

from aero.perception.stt import STTService, Transcript

DEFAULT_MODEL = "ai4bharat/indicconformer_stt_mr_hybrid_ctc_rnnt_large"


def _wav_seconds(audio_path: str) -> float:
    """Duration of a PCM WAV, dependency-free. 0.0 if unreadable (RTF just N/A)."""
    try:
        with contextlib.closing(wave.open(audio_path, "rb")) as w:
            frames, rate = w.getnframes(), w.getframerate()
            return frames / rate if rate else 0.0
    except (wave.Error, OSError, EOFError):
        return 0.0


class IndicConformerSTT(STTService):
    """Local IndicConformer via NeMo.

    ``decoder`` picks the hybrid head: ``"ctc"`` is faster (single pass),
    ``"rnnt"`` is usually more accurate but slower — the S-3 benchmark decides
    which Aditya's voice + the CPU budget can afford. ``language_id`` biases the
    Indic language (``"mr"`` Marathi by default; the model is Marathi-primary).
    """

    def __init__(
        self,
        model_name: str = DEFAULT_MODEL,
        *,
        decoder: str = "ctc",          # "ctc" (fast) | "rnnt" (accurate)
        language_id: str = "mr",
        device: str = "cpu",
        download_root: str | None = None,
    ):
        if decoder not in ("ctc", "rnnt"):
            raise ValueError(f"decoder must be 'ctc' or 'rnnt', got {decoder!r}")
        self.model_name = model_name
        self.decoder = decoder
        self.language_id = language_id
        self.device = device
        self.download_root = download_root
        self._model = None

    def _load(self):
        import nemo.collections.asr as nemo_asr  # lazy: optional heavy dep

        # A local .nemo path loads offline (no network) — used after a resilient
        # pre-download on flaky connections. See docs/AI4BHARAT_SETUP.md.
        if self.model_name.endswith(".nemo") and Path(self.model_name).is_file():
            return nemo_asr.models.ASRModel.restore_from(
                self.model_name, map_location=self.device
            )

        # `from_pretrained` guesses the weight filename from the repo id. This
        # repo is named ..._ctc_rnnt_large but ships ..._rnnt_large.nemo (the
        # hybrid .nemo carries both heads), so the guess 404s. Fall back to
        # locating the actual .nemo and restoring from it.
        try:
            return nemo_asr.models.ASRModel.from_pretrained(
                self.model_name, map_location=self.device
            )
        except Exception:
            from huggingface_hub import hf_hub_download, list_repo_files

            nemo_files = [f for f in list_repo_files(self.model_name)
                          if f.endswith(".nemo")]
            if not nemo_files:
                raise
            local = hf_hub_download(
                repo_id=self.model_name, filename=nemo_files[0],
                local_dir=self.download_root,
            )
            return nemo_asr.models.ASRModel.restore_from(
                local, map_location=self.device
            )

    def _ensure_model(self):
        if self._model is None:
            model = self._load()
            model.freeze()
            model = model.to(self.device)
            self._model = model
        return self._model

    def _decode(self, model, audio_path: str) -> str:
        # AI4Bharat's hybrid exposes `cur_decoder` + a `language_id` kwarg. Older
        # NeMo builds lack the kwarg; degrade gracefully rather than crash.
        model.cur_decoder = self.decoder
        try:
            out = model.transcribe(
                [audio_path], batch_size=1, language_id=self.language_id
            )
        except TypeError:
            out = model.transcribe([audio_path], batch_size=1)
        item = out[0] if out else ""
        # NeMo may return plain strings or Hypothesis objects depending on version.
        return (getattr(item, "text", None) or item or "").strip()

    def transcribe(self, audio_path: str, *, language: str | None = None) -> Transcript:
        model = self._ensure_model()
        # `language` overrides the configured language_id for this call (e.g. "hi").
        prev = self.language_id
        if language:
            self.language_id = language
        t0 = time.perf_counter()
        try:
            text = self._decode(model, audio_path)
        finally:
            self.language_id = prev
        compute = time.perf_counter() - t0
        return Transcript(
            text=text,
            language=language or self.language_id,
            seconds_audio=_wav_seconds(audio_path),
            seconds_compute=compute,
        )

    def health_check(self) -> bool:
        try:
            import nemo.collections.asr  # noqa: F401
            return True
        except Exception:
            return False


def build_stt(model: str = "small", *, decoder: str = "ctc"):
    """STT factory used by the CLI/probe. Keeps backend choice in one place:
      'indic'            -> IndicConformer (Marathi/Indic, needs NeMo fork)
      'moonshine[/tiny|/base]' -> Moonshine (fast English, CPU)
      anything else      -> faster-whisper (whisper size or model id)
    """
    if model == "indic":
        return IndicConformerSTT(decoder=decoder)
    if model.startswith("moonshine"):
        from aero.perception.moonshine_stt import MoonshineSTT
        return MoonshineSTT(model if "/" in model else "moonshine/base")
    from aero.perception.stt import FasterWhisperBackend
    return FasterWhisperBackend(model)
