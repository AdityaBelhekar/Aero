"""The gate threshold — how loud an impulse must be to earn a model call.

AERO-PRO-004: the threshold is **context-dependent**. Focused work raises it
sharply; an idle-but-present user lowers it (a good moment to speak); an *absent*
user raises it near-maximum (no audience); an explicit "talk to me" lowers it
strongly. Quiet hours push it past the ceiling — Aero simply cannot speak.

The threshold is what makes proactivity affordable: only impulses whose (decayed)
strength clears it reach the LLM gate, so the model runs on a small minority of
impulses (AERO-PRO-003 budget).

AERO-PRO-005 / AERO-FBK-002: the gate *learns*. Explicit feedback ("don't
interrupt me when I'm coding") produces a durable threshold bump; passive signals
(being ignored, interrupted) move it slowly. That learned movement is carried in
as ``learned_offset`` (persisted in settings by ``loop.py``); this module just
folds it in. Everything here is a pure function — trivially testable.
"""

from __future__ import annotations

from dataclasses import dataclass

#: When Aero must not speak at all (quiet hours), the threshold is set here —
#: above any possible impulse strength (which maxes at 1.0).
SILENCE_CEILING = 2.0

BASE = 0.5


@dataclass
class ThresholdInputs:
    activity_level: str | None = None   # 'active' | 'idle' | 'away' | None
    explicit_request: bool = False      # user asked Aero to engage
    quiet_hours: bool = False           # inside the persona quiet window
    chattiness: float = 0.5             # persona dial 0..1
    familiarity: float = 0.05           # relationship dim 0..1 (cold-start low)
    learned_offset: float = 0.0         # feedback-learned adjustment (±)


def compute_threshold(inp: ThresholdInputs) -> float:
    """Return the strength an impulse must exceed to reach the LLM gate.

    Higher = quieter Aero. Quiet hours short-circuit to a silence ceiling."""
    if inp.quiet_hours:
        return SILENCE_CEILING

    t = BASE

    # Context (AERO-PRO-004). Present-but-idle is the sweet spot for a quiet word;
    # actively-typing means focus → raise; away means no one to talk to → raise hard.
    if inp.activity_level == "active":
        t += 0.20
    elif inp.activity_level == "idle":
        t -= 0.10
    elif inp.activity_level == "away":
        t += 0.35

    # Chattiness dial: talkative lowers the bar, reserved raises it.
    t += (0.5 - inp.chattiness) * 0.4

    # Cold-start conservatism (AERO-COLD-003): an unfamiliar Aero holds back more.
    t += (0.5 - inp.familiarity) * 0.2

    # Learned feedback (AERO-PRO-005): durable + passive adjustments.
    t += inp.learned_offset

    # An explicit invitation lowers the bar strongly, but never to zero — even
    # "talk to me" still lets the gate choose silence if there's nothing to say.
    if inp.explicit_request:
        t = min(t, 0.15)

    # Keep it in a sane band (but below the silence ceiling).
    return max(0.05, min(1.2, t))
