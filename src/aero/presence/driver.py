"""PresenceDriver — the one object the daemon ticks to drive the avatar.

Ties the state machine (M9.2) and the ambient scheduler (M9.3) together: feed it
Aero's live signals each tick and it returns the current ``AvatarState`` to stream
to the overlay. When Aero is idle it consults the ambient scheduler on its own
cadence so he keeps fidgeting; when he's listening/thinking/speaking those win.

This is the whole producer side of the state→avatar contract. The daemon owns the
transport (serialise ``AvatarState.to_json()`` over the existing local IPC); the
overlay owns rendering. Neither needs to know how the state was decided.
"""

from __future__ import annotations

import random
import time
from collections.abc import Callable

from aero.perception.tier0 import Tier0Sample
from aero.presence.ambient import AmbientScheduler
from aero.presence.rig import RigManifest, default_manifest
from aero.presence.state import AvatarState
from aero.presence.state_machine import AvatarStateMachine
from aero.voice.speech_intent import SpeechIntent


class PresenceDriver:
    def __init__(
        self,
        rig: RigManifest | None = None,
        *,
        clock: Callable[[], float] = time.time,
        rng: random.Random | None = None,
        mood: str = "neutral",
    ):
        self.rig = rig or default_manifest()
        self.machine = AvatarStateMachine(self.rig)
        self.ambient = AmbientScheduler(self.rig, clock=clock, rng=rng)
        self.mood = mood
        self._idle_clip: str | None = None

    def tick(
        self,
        *,
        mic_hot: bool = False,
        thinking: bool = False,
        speaking: bool = False,
        intent: SpeechIntent | None = None,
        mouth_open: float = 0.0,
        action: str | None = None,
        world: Tier0Sample | None = None,
        now: float | None = None,
    ) -> AvatarState:
        """Compute the AvatarState for this tick. Only IDLE consults the ambient
        scheduler; active states (listen/think/speak) always take priority."""
        idle = not (mic_hot or thinking or speaking)
        tags: list[str] = []

        if idle:
            tags = self.ambient.tags_for(world, now)
            if self.ambient.due(now) or self._idle_clip is None:
                clip, tags = self.ambient.pick(world, mood=self.mood, now=now)
                self._idle_clip = clip
                self.ambient.reset(now)
        else:
            # leaving idle -> forget the held fidget so re-entering idle picks fresh
            self._idle_clip = None

        return self.machine.update(
            mic_hot=mic_hot,
            thinking=thinking,
            speaking=speaking,
            intent=intent,
            mouth_open=mouth_open,
            action=action,
            idle_clip=self._idle_clip if idle else None,
            tags=tags,
        )

    def set_mood(self, mood: str) -> None:
        self.mood = mood
