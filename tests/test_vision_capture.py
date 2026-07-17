"""Vision capture + consent + ephemerality (AERO-VIS-601/604). Hermetic, fake sources."""

from __future__ import annotations

from aero import settings as st
from aero.config import Config
from aero.perception.vision import (
    CameraSource,
    Eyes,
    Frame,
    LookVerdict,
    ScreenSource,
)


def _grabber(tag=b"IMG", w=1920, h=1080, thumb=b"\x00" * 64):
    return lambda: (tag, w, h, thumb)


def _eyes(settings, *, screen=True, camera=False):
    sources = {}
    if screen:
        sources["screen"] = ScreenSource(_grabber(b"SCREEN"))
    if camera:
        sources["camera"] = CameraSource(_grabber(b"CAM"))
    return Eyes(settings=settings, sources=sources)


# -- consent: off by default -----------------------------------------------
def test_look_refused_without_grant():
    r = _eyes(st.VoiceSettings()).look("screen")
    assert r.verdict is LookVerdict.REFUSED
    assert r.frame is None                    # nothing captured
    assert "not granted" in r.reason


def test_look_captures_when_granted():
    r = _eyes(st.VoiceSettings(permissions={"screen": True})).look("screen")
    assert r.verdict is LookVerdict.CAPTURED
    assert r.frame.image == b"SCREEN" and r.frame.width == 1920


def test_killswitch_blocks_capture():
    r = _eyes(st.VoiceSettings(permissions={"screen": True}, killswitch=True)).look()
    assert r.verdict is LookVerdict.REFUSED


def test_camera_needs_its_own_scope():
    s = st.VoiceSettings(permissions={"screen": True})   # screen only
    eyes = _eyes(s, camera=True)
    assert eyes.look("camera").verdict is LookVerdict.REFUSED
    s.permissions["camera"] = True
    assert eyes.look("camera").verdict is LookVerdict.CAPTURED


# -- availability ----------------------------------------------------------
def test_unavailable_source_when_no_grabber():
    eyes = Eyes(settings=st.VoiceSettings(permissions={"screen": True}),
                sources={"screen": ScreenSource(None)})   # headless
    r = eyes.look("screen")
    assert r.verdict is LookVerdict.UNAVAILABLE


def test_unknown_source():
    r = _eyes(st.VoiceSettings(permissions={"screen": True})).look("hologram")
    assert r.verdict is LookVerdict.UNAVAILABLE
    assert "registered" in r.reason


# -- ephemerality ----------------------------------------------------------
def test_frames_are_ephemeral_by_default():
    r = _eyes(st.VoiceSettings(permissions={"screen": True})).look()
    assert r.frame.ephemeral is True


def test_keep_makes_frame_non_ephemeral():
    f = Frame(image=b"x", source="screen").keep()
    assert f.ephemeral is False


def test_content_hash_stable():
    f1 = Frame(image=b"abc", source="screen")
    f2 = Frame(image=b"abc", source="screen")
    assert f1.content_hash() == f2.content_hash()
    assert Frame(image=b"xyz", source="screen").content_hash() != f1.content_hash()


# -- live settings ---------------------------------------------------------
def test_grant_read_live(tmp_path):
    cfg = Config(home=tmp_path)
    eyes = Eyes(cfg, sources={"screen": ScreenSource(_grabber())})
    assert eyes.look().verdict is LookVerdict.REFUSED
    s = st.load(cfg); s.permissions = {"screen": True}; st.save(s, cfg)
    assert eyes.look().verdict is LookVerdict.CAPTURED


def test_result_serialises():
    r = _eyes(st.VoiceSettings(permissions={"screen": True})).look()
    d = r.to_dict()
    assert d["verdict"] == "captured" and d["frame"]["ephemeral"] is True
    assert d["frame"]["bytes"] == len(b"SCREEN")
