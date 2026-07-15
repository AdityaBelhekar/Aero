"""Presence — Aero on your screen (v0.3 Pillar 1, the soul of the release).

This package is the **puppeteer, not the puppet** (v0.3 Rule 11: "you make the
body, we make it live"). Aditya authors the 3D robot model + animation clips; the
code here decides *which* clip plays *when* — idling with personality, reacting to
what's happening, lip-syncing to speech, expressing mood.

It is deliberately render-agnostic and asset-free: it emits a small, serialisable
``AvatarState`` (which animation, which emotion, a one-shot action, a lip-sync
amplitude) that the daemon streams over the existing local IPC to a thin overlay
client. The overlay — a transparent always-on-top window rendering the glTF, in a
web stack or Godot (spike S-11) — turns that state into pixels. Swapping the
renderer never touches this package.

Nothing here needs a display or the user's real model to run and be tested: the
state machine, emotion map, and ambient scheduler are pure logic over a
``RigManifest`` that ships with a placeholder default.
"""

from aero.presence.ambient import AmbientScheduler
from aero.presence.driver import PresenceDriver
from aero.presence.emotion import emotion_from_intent
from aero.presence.rig import RigManifest, default_manifest
from aero.presence.state import AnimationState, AvatarState, Emotion
from aero.presence.state_machine import AvatarStateMachine

__all__ = [
    "AmbientScheduler",
    "AnimationState",
    "AvatarState",
    "AvatarStateMachine",
    "Emotion",
    "PresenceDriver",
    "RigManifest",
    "default_manifest",
    "emotion_from_intent",
]
