"""AmbientScheduler — personality-driven idle behaviour (AERO-PRES-105).

The difference between Aero *feeling alive* and looking like a screensaver. When
nothing is happening he still does things — looks around, stretches, glances at
what you're doing, sighs when it's late — but *weighted by context*, not random
noise (v0.3: "a personality system, not random noise"). "It's 2am and you're in
Valorant" pulls a different set of fidgets than "it's 10am and you're coding".

Inputs: the Tier-0 world state (active window/process/idle — degrades to nothing
on Linux until tier0 is ported, and the scheduler still works), the time of day,
and Aero's current mood. Output: a fidget clip name (from the rig) + context tags
the overlay can use for extra flourish.

Deterministic by construction — the clock and RNG are injected, so tests pin
behaviour without real time or randomness.
"""

from __future__ import annotations

import random
import time
from collections.abc import Callable

from aero.perception.tier0 import Tier0Sample
from aero.presence.rig import RigManifest, default_manifest

# Coarse keyword buckets for the active app -> a context tag. Substring match on
# the lowercased process name + window title. Intentionally small.
_APP_TAGS: dict[str, tuple[str, ...]] = {
    "gaming": ("valorant", "csgo", "cs2", "steam", "minecraft", "game", "riotclient"),
    "coding": ("code", "vscode", "pycharm", "vim", "nvim", "terminal", "cmd",
               "powershell", "sublime", "intellij"),
    "browsing": ("chrome", "firefox", "edge", "brave", "safari"),
    "media": ("youtube", "netflix", "spotify", "vlc", "music"),
}

# Per-tag / per-mood weight boosts for specific fidget clips. A fidget not present
# in the rig is simply skipped. Base weight for every rig fidget is 1.0.
_TAG_BOOSTS: dict[str, dict[str, float]] = {
    "night":   {"bored_sigh": 2.5, "stretch": 1.8, "look_around": 0.6},
    "morning": {"stretch": 2.0, "look_around": 1.3},
    "active":  {"glance_at_screen": 3.0, "look_around": 0.5},  # user working -> watch them
    "away":    {"look_around": 2.5, "bored_sigh": 1.5, "glance_at_screen": 0.2},
    "gaming":  {"glance_at_screen": 3.0},                       # watch the game
    "coding":  {"glance_at_screen": 2.2},
}

_MOOD_BOOSTS: dict[str, dict[str, float]] = {
    "tired":   {"bored_sigh": 2.5, "stretch": 1.6},
    "bored":   {"bored_sigh": 2.0, "look_around": 1.5},
    "playful": {"look_around": 1.5, "stretch": 1.2},
    "neutral": {},
}


class AmbientScheduler:
    def __init__(
        self,
        rig: RigManifest | None = None,
        *,
        clock: Callable[[], float] = time.time,
        rng: random.Random | None = None,
        min_interval: float = 8.0,
        max_interval: float = 25.0,
    ):
        self.rig = rig or default_manifest()
        self._clock = clock
        self._rng = rng or random.Random()
        self.min_interval = min_interval
        self.max_interval = max_interval
        self._last_fire: float | None = None
        self._next_gap = self._rng.uniform(min_interval, max_interval)

    # -- context ----------------------------------------------------------
    def tags_for(self, world: Tier0Sample | None, now: float | None = None) -> list[str]:
        """Context tags from time-of-day + world state. Deterministic."""
        now = self._clock() if now is None else now
        hour = time.localtime(now).tm_hour
        tags: list[str] = []
        if hour >= 23 or hour < 5:
            tags.append("night")
        elif 5 <= hour < 11:
            tags.append("morning")

        if world is not None and world.ok:
            # activity from idle timer
            level = world.activity_level  # active | idle | away
            if level == "active":
                tags.append("active")
            elif level == "away":
                tags.append("away")
            # app bucket
            hay = f"{world.process_name or ''} {world.window_title or ''}".lower()
            for tag, kws in _APP_TAGS.items():
                if any(kw in hay for kw in kws):
                    tags.append(tag)
                    break
        return tags

    # -- selection --------------------------------------------------------
    def weighted_fidgets(
        self, tags: list[str], mood: str = "neutral"
    ) -> dict[str, float]:
        """Weight each rig fidget by the active tags + mood. Base 1.0, multiplied
        by every applicable boost. Only clips the rig actually has are returned."""
        weights = {clip: 1.0 for clip in self.rig.fidgets}
        boosts: list[dict[str, float]] = [_MOOD_BOOSTS.get(mood, {})]
        boosts += [_TAG_BOOSTS[t] for t in tags if t in _TAG_BOOSTS]
        for boost in boosts:
            for clip, mult in boost.items():
                if clip in weights:
                    weights[clip] *= mult
        return weights

    def pick(
        self,
        world: Tier0Sample | None = None,
        *,
        mood: str = "neutral",
        now: float | None = None,
    ) -> tuple[str | None, list[str]]:
        """Choose the next fidget clip (weighted) and return it with the context
        tags. Returns (None, tags) if the rig has no fidgets."""
        tags = self.tags_for(world, now)
        weights = self.weighted_fidgets(tags, mood)
        if not weights:
            return None, tags
        clips = list(weights)
        clip = self._rng.choices(clips, weights=[weights[c] for c in clips], k=1)[0]
        return clip, tags

    # -- cadence ("never looks frozen") -----------------------------------
    def due(self, now: float | None = None) -> bool:
        """True if enough time has passed to play the next fidget. The daemon's
        idle tick calls this; on True it should pick() and reset()."""
        now = self._clock() if now is None else now
        if self._last_fire is None:
            return True
        return (now - self._last_fire) >= self._next_gap

    def reset(self, now: float | None = None) -> None:
        """Record that a fidget just fired and choose the next (jittered) gap."""
        self._last_fire = self._clock() if now is None else now
        self._next_gap = self._rng.uniform(self.min_interval, self.max_interval)
