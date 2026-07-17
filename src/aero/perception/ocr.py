"""OCR — cheap text off the screen (AERO-VIS-601, Tier-1).

The cheapest way to understand a screen is to read its text, no multimodal model
needed. ``OCREngine`` is the swappable interface; the default backend is
RapidOCR (ONNX, CPU-friendly, no torch) — an optional dependency, import-guarded
so this module always imports. When OCR isn't installed, ``available()`` is False
and callers fall back to a vision brain (ocr -> multimodal is the Tier-1 -> Tier-2
escalation, AERO-VIS-002).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field

from aero.perception.vision import Frame


@dataclass
class OCRResult:
    text: str
    engine: str
    regions: list[dict] = field(default_factory=list)   # optional [{text, bbox, conf}]

    @property
    def has_text(self) -> bool:
        return bool(self.text.strip())


class OCREngine(ABC):
    name: str

    @abstractmethod
    def extract(self, frame: Frame) -> OCRResult:
        ...

    @abstractmethod
    def available(self) -> bool:
        ...


class RapidOCRBackend(OCREngine):
    """Local OCR via rapidocr-onnxruntime (optional). Constructed lazily so the
    ~100MB model only loads when OCR is actually used."""

    name = "rapidocr"

    def __init__(self):
        self._engine = None

    def available(self) -> bool:
        try:
            import rapidocr_onnxruntime  # noqa: F401
            return True
        except Exception:
            return False

    def _ensure(self):
        if self._engine is None:
            from rapidocr_onnxruntime import RapidOCR
            self._engine = RapidOCR()
        return self._engine

    def extract(self, frame: Frame) -> OCRResult:
        if not self.available():
            return OCRResult(text="", engine=self.name)
        import io

        import numpy as np
        from PIL import Image
        img = np.array(Image.open(io.BytesIO(frame.image)).convert("RGB"))
        result, _ = self._ensure()(img)
        regions = [{"text": t, "bbox": box, "conf": conf}
                   for box, t, conf in (result or [])]
        text = "\n".join(r["text"] for r in regions)
        return OCRResult(text=text, engine=self.name, regions=regions)


class NullOCR(OCREngine):
    """Explicit no-OCR backend: always available, returns nothing. Lets the
    pipeline run (and escalate to a vision brain) when OCR isn't installed."""

    name = "null"

    def available(self) -> bool:
        return True

    def extract(self, frame: Frame) -> OCRResult:
        return OCRResult(text="", engine=self.name)


def build_ocr(prefer: str = "rapidocr") -> OCREngine:
    """Return the best available OCR engine, falling back to NullOCR."""
    if prefer == "rapidocr":
        rapid = RapidOCRBackend()
        if rapid.available():
            return rapid
    return NullOCR()
