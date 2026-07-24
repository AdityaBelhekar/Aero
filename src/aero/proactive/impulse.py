"""Impulses — candidate reasons to engage (AERO-PRO-003 tier 1).

An impulse is *not* a decision to speak. It's a cheap signal the generator emits
when world state shifts in a way that might warrant engagement. Most impulses die
unread: they decay, or the gate suppresses them into silence.

Each impulse carries the three things AERO-PRO-003 requires — a **source** (why
it fired), a **strength** (how loud, 0..1 at birth), and a **decay time** (how
long before the moment has passed). Strength decays linearly to zero over the
decay window; a stale impulse (strength ≤ 0) is discarded rather than spoken,
because "if the moment passed, don't say it" (AERO-LAT, staleness rule).

Time is passed in explicitly as a monotonic-seconds ``now`` so the whole tier is
deterministically testable — nothing here reads the clock itself.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class ImpulseSource(str, Enum):
    """Why an impulse fired (AERO-PRO-003 enumerates these candidate reasons)."""

    NOVELTY = "novelty"                    # something new appeared in the world
    CONCERN = "concern"                    # something looks like it's going wrong
    HUMOUR = "humour"                      # an opening for a joke (needs earned roast)
    MEMORY_ACTIVATION = "memory_activation"  # a stored memory got triggered
    REPEATED_FAILURE = "repeated_failure"  # the user keeps hitting the same wall
    CONTRADICTION = "contradiction"        # world contradicts a known habit
    THOUGHT_THREAD = "thought_thread"      # an unresolved thought reactivated
    SOCIAL_URGE = "social_urge"            # a social opening (e.g. user came back)


@dataclass
class Impulse:
    """One candidate reason to engage, with source / strength / decay."""

    source: ImpulseSource
    strength: float          # 0..1 at creation (birth strength)
    subject: str             # short label of what it's about (for logs)
    detail: str              # a sentence the gate/LLM can read
    created_at: float        # monotonic seconds when it fired
    decay_seconds: float = 60.0  # strength reaches 0 this long after birth
    thread_id: str | None = None   # set for THOUGHT_THREAD impulses
    memory_id: str | None = None   # set for MEMORY_ACTIVATION impulses

    def current_strength(self, now: float) -> float:
        """Strength after linear decay from birth to ``now`` (clamped ≥ 0)."""
        if self.decay_seconds <= 0:
            return 0.0
        elapsed = max(0.0, now - self.created_at)
        remaining = 1.0 - (elapsed / self.decay_seconds)
        return max(0.0, self.strength * remaining)

    def is_stale(self, now: float) -> bool:
        """True once the moment has passed — nothing left to say (staleness rule)."""
        return self.current_strength(now) <= 0.0

    def to_dict(self) -> dict:
        return {
            "source": self.source.value,
            "strength": round(self.strength, 3),
            "subject": self.subject,
            "detail": self.detail,
            "decay_seconds": self.decay_seconds,
            "thread_id": self.thread_id,
            "memory_id": self.memory_id,
        }
