"""Personality dials + permissions/kill-switch storage (AERO-APP-205/206). Hermetic."""

from __future__ import annotations

from aero import settings as st
from aero.config import Config


def test_persona_defaults_present(tmp_path):
    s = st.load(Config(home=tmp_path))
    p = st.merged_persona(s)
    assert p["chattiness"] == 0.5
    assert p["roast_level"] == 0.2       # conservative start (relationship earns more)
    assert p["quiet_hours"] == [1, 8]


def test_persona_override_merges_with_defaults(tmp_path):
    s = st.load(Config(home=tmp_path))
    s.persona = {"roast_level": 0.9}     # only one dial set
    merged = st.merged_persona(s)
    assert merged["roast_level"] == 0.9  # override
    assert merged["chattiness"] == 0.5   # default filled in


def test_persona_roundtrip(tmp_path):
    cfg = Config(home=tmp_path)
    s = st.load(cfg)
    s.persona = {**st.DEFAULT_PERSONA_DIALS, "formality": 0.8}
    st.save(s, cfg)
    assert st.load(cfg).persona["formality"] == 0.8


def test_quiet_hours_basic():
    s = st.VoiceSettings(persona={"quiet_hours": [1, 8]})
    assert st.is_quiet_hours(s, 3) is True
    assert st.is_quiet_hours(s, 0) is False
    assert st.is_quiet_hours(s, 8) is False   # end exclusive
    assert st.is_quiet_hours(s, 14) is False


def test_quiet_hours_wraps_midnight():
    s = st.VoiceSettings(persona={"quiet_hours": [23, 6]})
    assert st.is_quiet_hours(s, 23) is True
    assert st.is_quiet_hours(s, 2) is True
    assert st.is_quiet_hours(s, 6) is False
    assert st.is_quiet_hours(s, 12) is False


def test_quiet_hours_disabled_when_equal():
    s = st.VoiceSettings(persona={"quiet_hours": [0, 0]})
    assert st.is_quiet_hours(s, 3) is False


def test_permissions_default_deny(tmp_path):
    s = st.load(Config(home=tmp_path))
    for scope in st.PERMISSION_SCOPES:
        assert st.permission_granted(s, scope) is False


def test_permission_grant_and_revoke(tmp_path):
    cfg = Config(home=tmp_path)
    s = st.load(cfg)
    s.permissions = {"apps": True}
    st.save(s, cfg)
    assert st.permission_granted(st.load(cfg), "apps") is True
    assert st.permission_granted(st.load(cfg), "shell") is False


def test_killswitch_overrides_all_grants():
    s = st.VoiceSettings(permissions={"apps": True, "files": True}, killswitch=True)
    assert st.permission_granted(s, "apps") is False
    assert st.permission_granted(s, "files") is False


def test_unknown_scope_denied():
    s = st.VoiceSettings(permissions={"apps": True})
    assert st.permission_granted(s, "nukes") is False
