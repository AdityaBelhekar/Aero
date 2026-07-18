"""body.* control ops (AERO-BODY-8xx). Hermetic."""

from __future__ import annotations

from aero import settings as st
from aero.config import Config
from aero.control import ControlService


def test_body_status(tmp_path):
    r = ControlService(Config(home=tmp_path)).dispatch("body.status")
    assert r["ok"]
    res = r["result"]
    assert "host" in res and "robot" in res
    assert res["robot"]["enabled"] is False        # desktop default
    assert res["hardware_available"] is False


def test_body_service_unit(tmp_path):
    r = ControlService(Config(home=tmp_path)).dispatch("body.service")
    unit = r["result"]["unit"]
    assert "[Service]" in unit and "ExecStart=aero daemon" in unit
    assert "AERO_HOME=" in unit                      # defaults to cfg.home


def test_body_pi_preset_persists(tmp_path):
    cfg = Config(home=tmp_path)
    r = ControlService(cfg).dispatch("body.pi_preset")
    assert r["result"]["reflex"] == "local" and r["result"]["primary"] == "litellm"
    # persisted to settings
    s = st.load(cfg)
    assert s.reflex_profile == "local" and s.primary_profile == "litellm"
