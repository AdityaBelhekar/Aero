"""OCR interface + scene-change + sparse sampler (AERO-VIS-601, VIS-002/003)."""

from __future__ import annotations

from aero.perception.ocr import NullOCR, OCRResult, build_ocr
from aero.perception.vision import (
    Frame,
    SceneChange,
    VisionSampler,
    average_hash,
    hamming,
)


# -- OCR interface ---------------------------------------------------------
def test_null_ocr_available_and_empty():
    ocr = NullOCR()
    assert ocr.available()
    r = ocr.extract(Frame(image=b"x", source="screen"))
    assert isinstance(r, OCRResult) and not r.has_text


def test_build_ocr_falls_back_to_null_without_rapid():
    # rapidocr almost certainly not installed in CI -> NullOCR
    ocr = build_ocr()
    assert ocr.available()


def test_ocr_result_has_text():
    assert OCRResult("hello", "x").has_text
    assert not OCRResult("   ", "x").has_text


# -- average hash + scene change -------------------------------------------
def test_average_hash_deterministic():
    thumb = bytes(range(64))
    assert average_hash(thumb) == average_hash(bytes(range(64)))


def test_identical_thumbs_no_change():
    sc = SceneChange(threshold=5)
    t = bytes([i % 256 for i in range(64)])
    assert sc.changed(t) is True          # first ever -> change
    assert sc.changed(t) is False         # same scene


def test_big_change_detected():
    sc = SceneChange(threshold=5)
    dark = bytes([10] * 64)
    bright_half = bytes([10] * 32 + [250] * 32)
    sc.changed(dark)
    assert sc.changed(bright_half) is True


def test_tiny_change_ignored():
    sc = SceneChange(threshold=5)
    a = bytes([i for i in range(64)])
    b = bytearray(a); b[0] = (b[0] + 1) % 256   # 1-pixel nudge
    sc.changed(a)
    assert sc.changed(bytes(b)) is False


def test_hamming():
    assert hamming(0b1010, 0b1000) == 1
    assert hamming(0, 0) == 0


# -- sparse sampler --------------------------------------------------------
def _thumb(v):
    return bytes([v] * 64)


def test_trigger_always_analyzes():
    s = VisionSampler(min_interval=100)
    assert s.should_analyze(_thumb(10), trigger=True, now=0) is True
    assert s.should_analyze(_thumb(10), trigger=True, now=0.1) is True  # even rapid


def test_rate_limited_without_trigger():
    s = VisionSampler(min_interval=2.0)
    assert s.should_analyze(_thumb(10), now=0) is True
    # same scene, too soon -> no
    assert s.should_analyze(_thumb(250), now=0.5) is False


def test_scene_change_gates_analysis():
    s = VisionSampler(min_interval=1.0)
    assert s.should_analyze(_thumb(10), now=0) is True
    # enough time passed but scene unchanged -> no
    assert s.should_analyze(_thumb(10), now=5) is False
    # time passed AND scene changed -> yes
    bright = bytes([10] * 32 + [250] * 32)
    assert s.should_analyze(bright, now=10) is True


def test_no_thumb_only_rate_limited():
    s = VisionSampler(min_interval=2.0)
    assert s.should_analyze(now=0) is True
    assert s.should_analyze(now=1) is False
    assert s.should_analyze(now=3) is True
