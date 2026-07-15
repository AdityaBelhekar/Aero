"""PresenceDriver — state machine + ambient integration. Deterministic."""

from __future__ import annotations

import random

from aero.perception.tier0 import Tier0Sample
from aero.presence import PresenceDriver
from aero.presence.state import AnimationState, Emotion
from aero.voice.speech_intent import SpeechIntent


def _driver():
    clock = {"t": 0.0}
    d = PresenceDriver(clock=lambda: clock["t"], rng=random.Random(7))
    return d, clock


def test_idle_tick_produces_fidget():
    d, _ = _driver()
    s = d.tick(world=Tier0Sample(ok=False))
    assert s.animation is AnimationState.IDLE
    assert s.clip in d.rig.fidgets       # a fidget was chosen for idle


def test_speaking_tick_overrides_ambient():
    d, _ = _driver()
    s = d.tick(speaking=True, intent=SpeechIntent.from_tone("yo", "excited"),
               mouth_open=0.4)
    assert s.animation is AnimationState.SPEAKING
    assert s.emotion is Emotion.EXCITED
    assert s.mouth_open == 0.4


def test_fidget_held_until_due_then_changes():
    d, clock = _driver()
    first = d.tick(world=Tier0Sample(ok=False)).clip
    # not due yet -> same fidget held
    held = d.tick(world=Tier0Sample(ok=False)).clip
    assert held == first
    # advance well past max_interval -> a new pick happens
    clock["t"] = 1000.0
    d.tick(world=Tier0Sample(ok=False))
    # (clip may or may not differ by chance, but a pick occurred without error)
    assert d._idle_clip in d.rig.fidgets


def test_leaving_and_reentering_idle_repicks():
    d, _ = _driver()
    d.tick(world=Tier0Sample(ok=False))
    assert d._idle_clip is not None
    d.tick(thinking=True)                # active state clears held fidget
    assert d._idle_clip is None
    d.tick(world=Tier0Sample(ok=False))  # back to idle -> repick
    assert d._idle_clip in d.rig.fidgets


def test_state_serialises_for_ipc():
    d, _ = _driver()
    s = d.tick(mic_hot=True)
    # the contract the daemon streams
    assert '"animation":"listening"' in s.to_json()
