"""eyes.* control ops (AERO-VIS-6xx). Hermetic — headless (no real capture)."""

from __future__ import annotations

from aero import settings as st
from aero.config import Config
from aero.control import ControlService
from aero.perception.vision import Eyes, ScreenSource


def _svc_with_fake_eyes(cfg, grabber):
    """A ControlService whose Eyes uses an injected grabber (so capture works
    without a display)."""
    svc = ControlService(cfg)
    svc._eyes = Eyes(cfg, sources={"screen": ScreenSource(grabber)})
    return svc


def test_eyes_status_headless(tmp_path):
    r = ControlService(Config(home=tmp_path)).dispatch("eyes.status")
    assert r["ok"]
    src = r["result"]["sources"]
    assert "screen" in src and "camera" in src
    assert src["screen"]["granted"] is False       # default-deny
    assert src["screen"]["available"] is False     # headless


def test_eyes_look_refused_without_grant(tmp_path):
    cfg = Config(home=tmp_path)
    svc = _svc_with_fake_eyes(cfg, lambda: (b"IMG", 100, 100, b"\x00" * 64))
    r = svc.dispatch("eyes.look", {"source": "screen"})
    assert r["result"]["verdict"] == "refused"     # grant gate before capture


def test_eyes_look_captures_after_grant(tmp_path):
    cfg = Config(home=tmp_path)
    s = st.load(cfg); s.permissions = {"screen": True}; st.save(s, cfg)
    svc = _svc_with_fake_eyes(cfg, lambda: (b"IMG", 100, 100, b"\x00" * 64))
    r = svc.dispatch("eyes.look", {"source": "screen"})
    assert r["result"]["verdict"] == "captured"
    assert r["result"]["frame"]["bytes"] == 3
    assert r["result"]["frame"]["ephemeral"] is True   # never persisted by default


def test_eyes_describe_blocked_without_grant(tmp_path):
    cfg = Config(home=tmp_path)
    svc = _svc_with_fake_eyes(cfg, lambda: (b"IMG", 10, 10, None))
    r = svc.dispatch("eyes.describe", {"source": "screen"})
    assert r["result"]["look"]["verdict"] == "refused"
    assert r["result"]["vision"] is None           # never reached the brain
