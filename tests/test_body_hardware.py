"""Hardware I/O + avatar->body mapping (AERO-BODY-803/804). Hermetic."""

from __future__ import annotations

from aero.body.hardware import (
    HardwareCaps,
    MockHardware,
    NullHardware,
    apply_avatar_state,
    build_hardware,
    emotion_rgb,
)
from aero.body.host import detect_host
from aero.presence.state import AnimationState, AvatarState, Emotion


# -- null hardware (desktop default) ---------------------------------------
def test_null_hardware_noops():
    hw = NullHardware()
    assert not hw.available()
    assert hw.caps() == HardwareCaps()
    hw.set_led((1, 2, 3))     # must not raise
    hw.set_head(0.5)
    hw.show_face(AvatarState())


def test_build_hardware_desktop_is_null():
    desktop = detect_host(platform="linux", machine="x86_64", env={"DISPLAY": ":0"})
    assert isinstance(build_hardware(desktop), NullHardware)


def test_build_hardware_arm_without_gpio_falls_back(monkeypatch):
    monkeypatch.setattr("aero.body.hardware.GpioHardware._probe", staticmethod(lambda: False))
    pi = detect_host(platform="linux", machine="aarch64", env={"DISPLAY": ":0"})
    assert isinstance(build_hardware(pi), NullHardware)   # no libs -> no-op


# -- mock hardware records commands ----------------------------------------
def test_mock_records_led_and_head():
    hw = MockHardware()
    hw.set_led((10, 20, 30))
    hw.set_head(0.4, -0.2)
    assert hw.led == (10, 20, 30) and hw.head == (0.4, -0.2)


def test_mock_respects_absent_capabilities():
    hw = MockHardware(servos=False)
    hw.set_head(0.9)
    assert hw.head is None            # no servos -> ignored
    hw.set_led((1, 1, 1))
    assert hw.led == (1, 1, 1)        # leds still work


def test_head_clamped():
    hw = MockHardware()
    hw.set_head(5.0, -9.0)
    assert hw.head == (1.0, -1.0)


# -- emotion -> LED --------------------------------------------------------
def test_emotion_colours_distinct():
    assert emotion_rgb(Emotion.ANNOYED) != emotion_rgb(Emotion.HAPPY)
    assert emotion_rgb(Emotion.NEUTRAL) == (40, 40, 50)


# -- apply_avatar_state ----------------------------------------------------
def test_apply_sets_mood_led():
    hw = MockHardware()
    apply_avatar_state(hw, AvatarState(emotion=Emotion.HAPPY))
    assert hw.led == emotion_rgb(Emotion.HAPPY)


def test_listening_faces_user():
    hw = MockHardware()
    apply_avatar_state(hw, AvatarState(animation=AnimationState.LISTENING))
    assert hw.head == (0.0, 0.0)


def test_idle_does_not_force_head():
    hw = MockHardware()
    apply_avatar_state(hw, AvatarState(animation=AnimationState.IDLE))
    assert hw.head is None            # left free for ambient behaviour


def test_display_face_mirrors_state():
    hw = MockHardware()
    s = AvatarState(animation=AnimationState.SPEAKING, emotion=Emotion.EXCITED)
    apply_avatar_state(hw, s)
    assert hw.face is s               # same puppet on the physical face


def test_apply_on_null_hardware_is_safe():
    apply_avatar_state(NullHardware(), AvatarState(emotion=Emotion.TEASING))  # no raise
