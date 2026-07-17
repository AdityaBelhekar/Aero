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


# -- scene change + sparse sampling (cost control, AERO-VIS-002/003) --------
def average_hash(thumb: bytes) -> int:
    """64-ish-bit average hash of a small grayscale buffer: each byte becomes a
    bit (1 if brighter than the mean). Robust to tiny changes, so a static screen
    hashes the same frame to frame — the basis of scene-change detection."""
    if not thumb:
        return 0
    mean = sum(thumb) / len(thumb)
    bits = 0
    for i, b in enumerate(thumb):
        if b > mean:
            bits |= (1 << i)
    return bits


def hamming(a: int, b: int) -> int:
    return bin(a ^ b).count("1")


class SceneChange:
    """Tracks the last analysed thumbnail and reports meaningful changes. Below
    ``threshold`` Hamming bits of difference is 'the same scene'."""

    def __init__(self, threshold: int = 5):
        self.threshold = threshold
        self._last: int | None = None

    def changed(self, thumb: bytes) -> bool:
        h = average_hash(thumb)
        if self._last is None or hamming(h, self._last) > self.threshold:
            self._last = h
            return True
        return False

    def reset(self) -> None:
        self._last = None


class VisionSampler:
    """Decides when the *expensive* analysis (OCR / multimodal) should run, given
    a cheaply-grabbed thumbnail — so Aero looks properly only when something
    actually changed and not too often (AERO-VIS-002 event-driven budget).

    A ``trigger`` (the user said "look at this", or a high-salience event) always
    passes. Otherwise: rate-limited AND scene must have changed.
    """

    def __init__(self, *, min_interval: float = 2.0, threshold: int = 5,
                 clock: Callable[[], float] | None = None):
        import time
        self.min_interval = min_interval
        self._scene = SceneChange(threshold)
        self._clock = clock or time.monotonic
        self._last_analyze: float | None = None

    def should_analyze(self, thumb: bytes | None = None, *,
                       trigger: bool = False, now: float | None = None) -> bool:
        now = self._clock() if now is None else now
        if trigger:
            self._commit(now, thumb)
            return True
        if self._last_analyze is not None and (now - self._last_analyze) < self.min_interval:
            return False
        if thumb is not None and not self._scene.changed(thumb):
            return False
        self._commit(now, thumb)
        return True

    def _commit(self, now: float, thumb: bytes | None) -> None:
        self._last_analyze = now
        if thumb is not None:
            # keep the scene detector in sync so the next change is relative to now
            self._scene._last = average_hash(thumb)


# -- real capture backends (optional; return None when unavailable) --------
def _thumb_from_pixels(rgb, size: int = 8) -> bytes:
    """8x8 grayscale thumbnail from a PIL image, for scene-hashing."""
    small = rgb.convert("L").resize((size, size))
    return bytes(small.getdata())


def mss_screen_grabber() -> Grabber | None:
    """A screen grabber using mss + Pillow, or None if either the deps or a
    display are missing. Captures the primary monitor as PNG + a scene thumbnail.
    (Needs a display; unavailable on a headless box — falls back to None.)"""
    try:
        import io

        import mss
        from PIL import Image
    except Exception:
        return None

    def grab():
        try:
            with mss.mss() as sct:
                mon = sct.monitors[1]
                shot = sct.grab(mon)
                img = Image.frombytes("RGB", shot.size, shot.bgra, "raw", "BGRX")
                buf = io.BytesIO()
                img.save(buf, format="PNG")
                return buf.getvalue(), img.width, img.height, _thumb_from_pixels(img)
        except Exception:
            return None
    return grab


def opencv_camera_grabber(device: int = 0) -> Grabber | None:
    """A camera grabber via OpenCV, or None if unavailable. Local-only; a frame
    is read on demand and released. (Needs a camera device.)"""
    try:
        import io

        import cv2
        from PIL import Image
    except Exception:
        return None

    def grab():
        cap = None
        try:
            cap = cv2.VideoCapture(device)
            ok, frame = cap.read()
            if not ok:
                return None
            rgb = Image.fromarray(frame[:, :, ::-1])  # BGR -> RGB
            buf = io.BytesIO()
            rgb.save(buf, format="JPEG")
            return buf.getvalue(), rgb.width, rgb.height, _thumb_from_pixels(rgb)
        except Exception:
            return None
        finally:
            if cap is not None:
                cap.release()
    return grab


def build_eyes(cfg: Config | None = None) -> "Eyes":
    """Assemble Eyes with the best available real capture backends. On a headless
    box both sources exist but report unavailable() — consent + routing still work,
    they just can't grab a frame until there's a display/camera."""
    return Eyes(cfg, sources={
        "screen": ScreenSource(mss_screen_grabber()),
        "camera": CameraSource(opencv_camera_grabber()),
    })
