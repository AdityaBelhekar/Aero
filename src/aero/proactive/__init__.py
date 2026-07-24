"""Proactive cognition — Aero notices, and mostly stays silent (PRD §7, M4).

The one feature that makes Aero not-a-chatbot: it can initiate. But "initiate"
here means the *decision to engage at all*, whose overwhelming default is
silence (AERO-PRO-002). The machinery is two-tier by cost (AERO-PRO-003):

  * **tier 1 — impulse generation** (``generator.py``): cheap, continuous,
    non-LLM heuristics over world-state *deltas* produce candidate reasons to
    engage — *impulses* carrying a source, a strength, and a decay time. This
    runs every daemon tick and never calls a model.
  * **tier 2 — impulse gate** (``gate.py``): only when an impulse clears a
    *context-dependent threshold* (``threshold.py``) does the LLM run a full
    social evaluation. Its default output is still silence. This is the < 10%
    of impulses that earn a model call (AERO-PRO-003 budget).

Supporting state: ``threads.py`` (unresolved thought threads that reactivate on
triggers), ``relationship.py`` (slow-moving familiarity/trust that gate
behaviour), ``selfmem.py`` (every decision — including silences — logged with its
reasoning, AERO-PRO-006). ``loop.py`` ties it together for one daemon tick.

Design guarantee (mirrors the consent gate): the default-silence rules are
*code*, not prompt guidance a clever context could talk around. Timer-based
proactive speech is structurally impossible — no producer keys on elapsed idle
time alone (AERO-PRO-001).
"""

from aero.proactive.impulse import Impulse, ImpulseSource
from aero.proactive.gate import GateDecision, GateVerdict, ImpulseGate
from aero.proactive.generator import GenContext, ImpulseGenerator
from aero.proactive.loop import ProactiveLoop
from aero.proactive.relationship import RelationshipModel
from aero.proactive.selfmem import SelfMemoryLog
from aero.proactive.threads import ThoughtThread, ThoughtThreadStore
from aero.proactive.threshold import ThresholdInputs, compute_threshold

__all__ = [
    "Impulse",
    "ImpulseSource",
    "ImpulseGenerator",
    "GenContext",
    "ImpulseGate",
    "GateDecision",
    "GateVerdict",
    "compute_threshold",
    "ThresholdInputs",
    "ThoughtThread",
    "ThoughtThreadStore",
    "RelationshipModel",
    "SelfMemoryLog",
    "ProactiveLoop",
]
