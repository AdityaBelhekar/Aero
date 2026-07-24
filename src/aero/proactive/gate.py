"""The impulse gate — tier 2, default silence, structurally (AERO-PRO-002/003).

This is the counterpart to the consent gate: the rules that keep Aero quiet are
*code*, not prompt guidance. The gate decides between **speak** and **silent**,
and silence wins by construction. The expensive LLM social evaluation runs only
after the cheap structural checks have already let an impulse through — so the
model is consulted on a small minority of impulses (AERO-PRO-003 budget).

Decision order (cheapest / most-restrictive first — each can only say *silent*):

  1. **kill switch on** → silent. Aero takes no initiative at all.
  2. **quiet hours** → silent (threshold at the silence ceiling).
  3. **impulse stale** → silent — the moment passed; late proactive speech is
     discarded, never delivered (staleness rule).
  4. **strength below threshold** → silent, *without a model call*. This is the
     ~90% path (AERO-PRO-004 threshold does the filtering cheaply).
  5. **LLM social evaluation** → still defaults to silence; only a confident
     "speak" with a real utterance produces speech.

AERO-PRO-006: **every** decision — including all the silences above — is logged
to self-memory with its reasoning, so a suppressed impulse can inform a later
moment ("I noticed this earlier but you were busy").
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from aero.proactive.impulse import Impulse
from aero.proactive.selfmem import SelfMemoryLog
from aero.proactive.threshold import SILENCE_CEILING
from aero.prompts.proactive import gate_messages


class GateVerdict(str, Enum):
    SPEAK = "speak"
    SILENT = "silent"


@dataclass
class GateContext:
    """Pre-rendered short strings the LLM social eval reads. The loop assembles
    these from world state, the relationship model, and recent interaction."""

    world: str = ""
    relationship: str = ""
    recent: str = ""


@dataclass
class GateDecision:
    verdict: GateVerdict
    reason: str
    impulse: Impulse | None
    threshold: float
    strength: float
    utterance: str | None = None
    llm_ran: bool = False

    @property
    def speak(self) -> bool:
        return self.verdict is GateVerdict.SPEAK

    def to_dict(self) -> dict:
        return {
            "verdict": self.verdict.value,
            "reason": self.reason,
            "utterance": self.utterance,
            "llm_ran": self.llm_ran,
            "threshold": round(self.threshold, 3),
            "strength": round(self.strength, 3),
            "impulse": self.impulse.to_dict() if self.impulse else None,
        }


class ImpulseGate:
    """Speak-or-silence, with silence as the structural default."""

    def __init__(self, *, selfmem: SelfMemoryLog | None = None):
        #: When set, every decision is logged to self-memory (AERO-PRO-006).
        self.selfmem = selfmem

    def evaluate(
        self,
        impulse: Impulse,
        *,
        threshold: float,
        now: float,
        killswitch: bool = False,
        quiet_hours: bool = False,
        llm=None,
        context: GateContext | None = None,
    ) -> GateDecision:
        strength = impulse.current_strength(now)

        def decide(verdict: GateVerdict, reason: str, *,
                   utterance: str | None = None, llm_ran: bool = False) -> GateDecision:
            d = GateDecision(verdict, reason, impulse, threshold, strength,
                             utterance=utterance, llm_ran=llm_ran)
            self._log(d)
            return d

        # 1. kill switch — no initiative whatsoever (mirrors the consent gate).
        if killswitch:
            return decide(GateVerdict.SILENT, "kill switch on — no proactive speech")

        # 2. quiet hours — Aero cannot speak now.
        if quiet_hours or threshold >= SILENCE_CEILING:
            return decide(GateVerdict.SILENT, "quiet hours")

        # 3. staleness — the moment passed before we got here.
        if impulse.is_stale(now):
            return decide(GateVerdict.SILENT, "moment passed (impulse decayed)")

        # 4. below threshold — the cheap majority; NO model call.
        if strength < threshold:
            return decide(GateVerdict.SILENT,
                          f"below threshold ({strength:.2f} < {threshold:.2f})")

        # 5. the impulse earned an LLM social evaluation — default still silence.
        if llm is None:
            return decide(GateVerdict.SILENT, "no brain available for gate eval")
        parsed = self._eval_llm(llm, impulse, context or GateContext())
        if not parsed or not parsed.get("speak"):
            why = (parsed or {}).get("reason") or "gate chose silence"
            return decide(GateVerdict.SILENT, f"gate: {why}", llm_ran=True)
        utterance = str(parsed.get("utterance") or "").strip()
        if not utterance:
            return decide(GateVerdict.SILENT,
                          "gate said speak but produced no utterance", llm_ran=True)
        return decide(GateVerdict.SPEAK,
                      f"gate: {parsed.get('reason') or 'worth it'}",
                      utterance=utterance, llm_ran=True)

    # -- internals ---------------------------------------------------------
    def _eval_llm(self, llm, impulse: Impulse, ctx: GateContext) -> dict | None:
        """Run the social evaluation. Any failure degrades to None → silence."""
        try:
            messages = gate_messages(world=ctx.world, relationship=ctx.relationship,
                                     impulse=impulse.detail, recent=ctx.recent)
            parsed, _ = llm.complete_json(messages, temperature=0.4, max_tokens=200)
            return parsed if isinstance(parsed, dict) else None
        except Exception:
            return None

    def _log(self, d: GateDecision) -> None:
        if self.selfmem is None:
            return
        action = "spoke" if d.speak else "stayed_silent"
        src = d.impulse.source.value if d.impulse else "?"
        context = f"[{src}] {d.reason}"
        if d.impulse:
            context += f" | impulse: {d.impulse.subject}"
        self.selfmem.record(action, context=context, outcome=d.utterance)
