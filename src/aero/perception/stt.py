"""Speech-to-text — Aero's ear (PRD Section 22, spike S-3).

Trilingual code-switched STT is the hardest perception problem in the product,
so it gets its own swappable service like cognition. The default backend is
faster-whisper (CTranslate2), which runs Whisper-class multilingual models
locally on CPU and auto-downloads weights from HuggingFace.

Kept behind ``STTService`` so an Indic-specialised model (AI4Bharat
IndicWhisper/IndicConformer class) can be dropped in if the benchmark favours it,
without touching callers. ``faster_whisper`` is an optional dependency; importing
this module never requires it — only constructing the backend does.
"""

from __future__ import annotations

import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class Transcript:
    text: str
    language: str | None = None          # detected language code, if any
    seconds_audio: float = 0.0
    seconds_compute: float = 0.0
    segments: list[dict] = field(default_factory=list)

    @property
    def realtime_factor(self) -> float:
        """compute / audio. < 1.0 means faster than realtime (needed for live)."""
        if self.seconds_audio <= 0:
            return 0.0
        return self.seconds_compute / self.seconds_audio


class STTService(ABC):
    model_name: str

    @abstractmethod
    def transcribe(self, audio_path: str, *, language: str | None = None) -> Transcript:
        ...

    @abstractmethod
    def health_check(self) -> bool:
        ...


class FasterWhisperBackend(STTService):
    """Local Whisper via faster-whisper / CTranslate2.

    ``model_name`` is a whisper size ("tiny", "base", "small", "medium",
    "large-v3") or a HF/CTranslate2 model id. For code-switched Indic audio,
    "small"/"medium" multilingual are the realistic CPU candidates; larger models
    are more accurate but slower than realtime on a laptop CPU.
    """

    def __init__(
        self,
        model_name: str = "small",
        *,
        device: str = "cpu",
        compute_type: str = "int8",   # int8 keeps CPU RAM/latency sane
        download_root: str | None = None,
    ):
        self.model_name = model_name
        self.device = device
        self.compute_type = compute_type
        self.download_root = download_root
        self._model = None

    def _ensure_model(self):
        if self._model is None:
            from faster_whisper import WhisperModel  # lazy: optional dependency

            self._model = WhisperModel(
                self.model_name,
                device=self.device,
                compute_type=self.compute_type,
                download_root=self.download_root,
            )
        return self._model

    def transcribe(self, audio_path: str, *, language: str | None = None) -> Transcript:
        model = self._ensure_model()
        t0 = time.perf_counter()
        # language=None lets Whisper auto-detect; for code-switch we usually pass
        # None and let it ride, or "hi"/"mr"/"en" to bias.
        segments, info = model.transcribe(
            audio_path,
            language=language,
            vad_filter=True,           # drop silence: faster + cleaner
            beam_size=5,
        )
        seg_list = []
        texts = []
        for s in segments:            # generator — realized here
            seg_list.append({"start": s.start, "end": s.end, "text": s.text})
            texts.append(s.text)
        compute = time.perf_counter() - t0
        return Transcript(
            text="".join(texts).strip(),
            language=getattr(info, "language", None),
            seconds_audio=getattr(info, "duration", 0.0),
            seconds_compute=compute,
            segments=seg_list,
        )

    def health_check(self) -> bool:
        try:
            import faster_whisper  # noqa: F401
            return True
        except Exception:
            return False
