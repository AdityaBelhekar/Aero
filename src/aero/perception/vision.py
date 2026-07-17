"""Eyes — consent-gated, ephemeral visual perception (v0.3 Pillar 6, AERO-VIS-601/604).

Vision exists so Aero can *react like a friend in the room* — see the game, the
meme, the error, and comment. It is off by default, per-source consented, and
frames are **ephemeral**: a captured frame is held only long enough to be used
(OCR'd, sent to a vision brain) and is never persisted unless the user explicitly
asks Aero to remember it (AERO-VIS-604).

Two sources, one interface (``VisionSource``): the **screen** (Tier-1, driven by
what Tier-0 says is the active window) and the **camera** (local-only). Real
capture backends (mss/Pillow for screen, OpenCV for camera) need a display/device
and are injected as ``grabber`` callables — so this module is dependency-free and
fully testable, and wiring a real grabber later is one function.

Consent reuses the M10/M12 permission scopes (``screen``/``camera``): capture goes
through ``settings.permission_granted``, which is default-deny and forced off by
the kill switch. No grant -> no frame is ever taken.
"""

from __future__ import annotations

import hashlib
from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum

from aero import settings as st
from aero.config import Config


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class Frame:
    """One captured image. ``thumb`` is a small grayscale buffer (row-major bytes)
    used for cheap scene-change detection without decoding the full image."""

    image: bytes                       # encoded image (png/jpeg) or raw pixels
    source: str                        # "screen" | "camera" | a window title
    width: int = 0
    height: int = 0
    fmt: str = "png"
    ts: str = field(default_factory=_now)
    ephemeral: bool = True             # not persisted unless explicitly kept
    thumb: bytes | None = None         # small grayscale thumbnail for scene hashing

    def content_hash(self) -> str:
        return hashlib.sha256(self.image).hexdigest()[:16]

    def keep(self) -> "Frame":
        """Mark this frame non-ephemeral (the user asked Aero to remember it)."""
        self.ephemeral = False
        return self


class LookVerdict(str, Enum):
    CAPTURED = "captured"
    REFUSED = "refused"       # scope not granted / kill switch
    UNAVAILABLE = "unavailable"  # no display / device / backend


@dataclass
class LookResult:
    verdict: LookVerdict
    source: str
    frame: Frame | None = None
    reason: str = ""

    @property
    def ok(self) -> bool:
        return self.verdict is LookVerdict.CAPTURED

    def to_dict(self) -> dict:
        return {"verdict": self.verdict.value, "source": self.source,
                "reason": self.reason,
                "frame": None if self.frame is None else {
                    "source": self.frame.source, "fmt": self.frame.fmt,
                    "width": self.frame.width, "height": self.frame.height,
                    "ts": self.frame.ts, "ephemeral": self.frame.ephemeral,
                    "bytes": len(self.frame.image)}}


class VisionSource(ABC):
    """A place Aero can look. ``scope`` is the permission scope it needs."""

    scope: str
    name: str

    @abstractmethod
    def capture(self) -> Frame | None:
        """Grab one frame, or None if capture is currently impossible."""

    @abstractmethod
    def available(self) -> bool:
        """True if this source can actually capture (display/device present)."""


# grabber() -> (image_bytes, width, height, thumb_bytes|None), or None if it can't.
Grabber = Callable[[], "tuple[bytes, int, int, bytes | None] | None"]


class ScreenSource(VisionSource):
    scope = "screen"
    name = "screen"

    def __init__(self, grabber: Grabber | None = None, *, fmt: str = "png"):
        # Real grabber (mss/Pillow) captures the active window/desktop. Injected so
        # this is testable and dependency-free; None -> unavailable (headless).
        self._grabber = grabber
        self.fmt = fmt

    def available(self) -> bool:
        return self._grabber is not None

    def capture(self) -> Frame | None:
        if self._grabber is None:
            return None
        got = self._grabber()
        if got is None:
            return None
        image, w, h, thumb = got
        return Frame(image=image, source="screen", width=w, height=h,
                     fmt=self.fmt, thumb=thumb)


class CameraSource(VisionSource):
    scope = "camera"
    name = "camera"

    def __init__(self, grabber: Grabber | None = None, *, fmt: str = "jpeg"):
        self._grabber = grabber
        self.fmt = fmt

    def available(self) -> bool:
        return self._grabber is not None

    def capture(self) -> Frame | None:
        if self._grabber is None:
            return None
        got = self._grabber()
        if got is None:
            return None
        image, w, h, thumb = got
        return Frame(image=image, source="camera", width=w, height=h,
                     fmt=self.fmt, thumb=thumb)


class Eyes:
    """Consent-gated capture across the registered sources. The ONLY way a frame
    is taken — so the per-source grant + kill switch always apply."""

    def __init__(self, cfg: Config | None = None, *,
                 sources: dict[str, VisionSource] | None = None, settings=None):
        self.cfg = cfg or Config.load()
        self.sources = sources or {}
        self._settings = settings   # injectable for tests; else loaded live

    def _load(self):
        return self._settings if self._settings is not None else st.load(self.cfg)

    def add_source(self, source: VisionSource) -> None:
        self.sources[source.name] = source

    def look(self, source: str = "screen") -> LookResult:
        src = self.sources.get(source)
        if src is None:
            return LookResult(LookVerdict.UNAVAILABLE, source,
                              reason=f"no '{source}' source registered")

        # per-source consent (default-deny; kill switch forces off)
        s = self._load()
        if not st.permission_granted(s, src.scope):
            return LookResult(LookVerdict.REFUSED, source,
                              reason=f"permission '{src.scope}' not granted "
                                     "(vision is off by default)")
        if not src.available():
            return LookResult(LookVerdict.UNAVAILABLE, source,
                              reason="no display/device or capture backend")

        frame = src.capture()
        if frame is None:
            return LookResult(LookVerdict.UNAVAILABLE, source,
                              reason="capture returned nothing")
        return LookResult(LookVerdict.CAPTURED, source, frame=frame)
