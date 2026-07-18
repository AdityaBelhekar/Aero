"""Shared face rig + robot profile + autostart (AERO-BODY-802/805). Hermetic."""

from __future__ import annotations

from aero import settings as st
from aero.body.face import DisplayFace, OverlayFace, build_face
from aero.body.hardware import MockHardware, NullHardware
from aero.body.robot import (
    RobotProfile,
    apply_pi_brain_preset,
    systemd_unit,
)
from aero.config import Config
from aero.presence.state import AnimationState, AvatarState, Emotion


# -- face: one rig, two outputs --------------------------------------------
def test_overlay_face_forwards_json():
    sent = []
    face = OverlayFace(sink=sent.append)
    face.render(AvatarState(animation=AnimationState.SPEAKING))
    assert len(sent) == 1 and '"animation":"speaking"' in sent[0]


def test_display_face_expresses_on_hardware():
    hw = MockHardware()
    face = DisplayFace(hw)
    s = AvatarState(emotion=Emotion.HAPPY, animation=AnimationState.LISTENING)
    face.render(s)
    assert hw.face is s and hw.led is not None
    assert hw.head == (0.0, 0.0)          # listening -> faces user


def test_build_face_desktop_is_overlay():
    assert isinstance(build_face(hardware=NullHardware()), OverlayFace)


def test_build_face_with_display_hw_is_display_face():
    hw = MockHardware(display_face=True)
    assert isinstance(build_face(hardware=hw), DisplayFace)


def test_same_state_drives_either_face():
    # the point of AERO-BODY-805: identical AvatarState, different output
    s = AvatarState(emotion=Emotion.EXCITED)
    overlay = OverlayFace(sink=lambda _j: None)
    hw = MockHardware()
    display = DisplayFace(hw)
    overlay.render(s)
    display.render(s)
    assert overlay.last is s and display.last is s


# -- robot profile ---------------------------------------------------------
def test_robot_profile_default_disabled():
    p = RobotProfile.from_settings(st.VoiceSettings())
    assert not p.enabled and p.platform == "auto"
    assert not p.hardware.servos


def test_robot_profile_from_settings():
    s = st.VoiceSettings(robot={"enabled": True, "platform": "pi",
                                "hardware": {"leds": True, "servos": True}})
    p = RobotProfile.from_settings(s)
    assert p.enabled and p.platform == "pi"
    assert p.hardware.leds and p.hardware.servos and not p.hardware.display_face


def test_robot_profile_roundtrips(tmp_path):
    cfg = Config(home=tmp_path)
    s = st.load(cfg)
    s.robot = {"enabled": True, "platform": "pi", "hardware": {"display_face": True}}
    st.save(s, cfg)
    p = RobotProfile.from_settings(st.load(cfg))
    assert p.enabled and p.hardware.display_face


# -- pi brain preset -------------------------------------------------------
def test_pi_brain_preset_sets_two_speed_router():
    s = apply_pi_brain_preset(st.VoiceSettings())
    assert s.reflex_profile == "local"      # tagging/reflex stays on-device
    assert s.primary_profile == "litellm"   # hard stuff routes to a LAN/cloud brain


# -- systemd autostart -----------------------------------------------------
def test_systemd_unit_wellformed():
    unit = systemd_unit(exec_start="/usr/bin/aero daemon", aero_home="/home/pi/.aero")
    assert "[Unit]" in unit and "[Service]" in unit and "[Install]" in unit
    assert "ExecStart=/usr/bin/aero daemon" in unit
    assert "AERO_HOME=/home/pi/.aero" in unit
    assert "Restart=on-failure" in unit
    assert "WantedBy=default.target" in unit


def test_systemd_unit_without_home_omits_env():
    unit = systemd_unit()
    assert "Environment=AERO_HOME" not in unit
    assert "ExecStart=aero daemon" in unit
