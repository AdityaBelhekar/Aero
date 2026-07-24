"""ProactiveLoop — one tick of "should I do anything?" (PRD §7, M4).

This is what the daemon calls each tick to give Aero the chance to notice. It
wires the two tiers together and owns the small amount of state that spans ticks
(the previous world state, so deltas can be computed):

  1. generate impulses from the world delta (tier 1, cheap, no model),
  2. take the strongest live impulse — if none fired, return with no fuss,
  3. compute the context-dependent threshold (world + persona + relationship +
     learned feedback + quiet hours),
  4. run the gate, which defaults to silence and only sometimes calls the LLM,
  5. every decision (incl. silence) is logged to self-memory by the gate.

It also owns **feedback learning** (AERO-PRO-005 / AERO-FBK-003): interruption
feedback moves the gate threshold (persisted in settings); relationship feedback
moves the vault's relationship dimensions. Feedback is routed to the correct
store, not dumped in one place.

Time is injected: ``clock`` supplies monotonic seconds for impulse decay, and the
wall-clock ``hour`` (for quiet hours) can be passed in — so the whole loop is
deterministically testable without touching a real clock.
"""

from __future__ import annotations

import time
from datetime import datetime

from aero import settings as st
from aero.config import Config
from aero.memory.store import MemoryStore
from aero.proactive.gate import GateContext, GateDecision, ImpulseGate
from aero.proactive.generator import GenContext, ImpulseGenerator
from aero.proactive.relationship import RelationshipModel
from aero.proactive.selfmem import SelfMemoryLog
from aero.proactive.threads import ThoughtThreadStore
from aero.proactive.threshold import ThresholdInputs, compute_threshold
from aero.working_set import WorldState


def _clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


class ProactiveLoop:
    def __init__(
        self,
        store: MemoryStore,
        llm=None,
        cfg: Config | None = None,
        *,
        settings=None,
        clock=time.monotonic,
        generator: ImpulseGenerator | None = None,
        gate: ImpulseGate | None = None,
    ):
        self.store = store
        self.llm = llm
        self.cfg = cfg or Config.load()
        self._settings = settings          # injected (tests) else loaded live each tick
        self.clock = clock

        self.selfmem = SelfMemoryLog(store)
        self.threads = ThoughtThreadStore(store)
        self.relationship = RelationshipModel(store)
        self.generator = generator or ImpulseGenerator()
        self.gate = gate or ImpulseGate(selfmem=self.selfmem)

        self._prev_world: WorldState | None = None

    def _load(self):
        return self._settings if self._settings is not None else st.load(self.cfg)

    # -- one tick ----------------------------------------------------------
    def tick(
        self,
        world: WorldState,
        *,
        prev: WorldState | None = None,
        recent_failures: int = 0,
        explicit_request: bool = False,
        hour: int | None = None,
        now: float | None = None,
    ) -> GateDecision | None:
        """Consider the current moment. Returns the gate's decision when an
        impulse was actually evaluated, or ``None`` when nothing fired (the quiet
        common case — no impulse means nothing to decide)."""
        s = self._load()
        if not st.proactive_enabled(s):
            return None

        now = self.clock() if now is None else now
        prev = prev if prev is not None else self._prev_world

        ctx = GenContext(world=world, prev=prev, now=now,
                         recent_failures=recent_failures,
                         explicit_request=explicit_request, threads=self.threads)
        # Advance the delta baseline for next tick regardless of outcome.
        self._prev_world = world

        impulse = self.generator.strongest(ctx)
        if impulse is None:
            return None

        # A reactivated thread updates its lifecycle timestamp (AERO-THT-002).
        if impulse.thread_id:
            self.threads.touch(impulse.thread_id)

        inputs = self._threshold_inputs(s, world, explicit_request, hour)
        threshold = compute_threshold(inputs)
        gctx = GateContext(
            world=world.render(),
            relationship=self.relationship.summary(),
            recent=self._recent_context(),
        )
        decision = self.gate.evaluate(
            impulse, threshold=threshold, now=now,
            killswitch=s.killswitch, quiet_hours=inputs.quiet_hours,
            llm=self.llm, context=gctx,
        )
        if decision.speak:
            # A successful, well-judged initiation slowly warms the relationship.
            self.relationship.nudge("familiarity", 0.01)
            self.relationship.nudge("conversation_energy", 0.01)
        return decision

    def _threshold_inputs(self, s, world: WorldState, explicit_request: bool,
                          hour: int | None) -> ThresholdInputs:
        persona = st.merged_persona(s)
        if hour is None:
            hour = datetime.now().hour
        return ThresholdInputs(
            activity_level=world.activity_level,
            explicit_request=explicit_request,
            quiet_hours=st.is_quiet_hours(s, hour),
            chattiness=float(persona.get("chattiness", 0.5)),
            familiarity=self.relationship.get("familiarity"),
            learned_offset=st.proactive_threshold_offset(s, world.active_app),
        )

    def _recent_context(self) -> str:
        """A short note on what Aero did recently, for the gate prompt — so it
        doesn't nag or repeat itself."""
        last = self.selfmem.recent(limit=1)
        if not last:
            return "nothing recently"
        e = last[0]
        return f"last thing Aero did: {e.action} ({e.context or ''})".strip()

    # -- feedback learning (AERO-PRO-005 / AERO-FBK-003) -------------------
    def record_feedback(self, kind: str, *, app: str | None = None) -> dict:
        """Route social feedback to the right store.

        Interruption tolerance moves the **gate threshold** (persisted in
        settings); joke/quality reactions move **relationship** dimensions. Kinds:

          * ``dont_interrupt`` — explicit, durable, larger bump (AERO-FBK-001).
          * ``talk_more``      — explicit invitation; lowers the bar durably.
          * ``good_call``      — the proactive message landed; lower bar a touch, build trust.
          * ``ignored`` / ``interrupted`` — passive, *slow* movement (AERO-FBK-002).
        """
        s = self._load()
        prox = dict(s.proactive or {})
        off = float(prox.get("threshold_offset", 0.0) or 0.0)
        by_app = dict(prox.get("threshold_offset_by_app") or {})

        def bump_app(delta: float) -> None:
            if app:
                by_app[app] = _clamp(float(by_app.get(app, 0.0)) + delta, -0.4, 0.6)

        if kind == "dont_interrupt":          # explicit, durable
            if app:
                bump_app(0.25)
            else:
                off = _clamp(off + 0.25, -0.4, 0.6)
            self.relationship.nudge("desire_for_interaction", -0.05)
        elif kind == "talk_more":             # explicit invitation
            off = _clamp(off - 0.15, -0.4, 0.6)
            self.relationship.nudge("desire_for_interaction", 0.05)
        elif kind == "good_call":             # it landed
            off = _clamp(off - 0.05, -0.4, 0.6)
            self.relationship.nudge("trust", 0.02)
            self.relationship.nudge("interaction_quality", 0.03)
        elif kind in ("ignored", "interrupted"):  # passive, slow
            off = _clamp(off + 0.03, -0.4, 0.6)
            self.relationship.nudge("interaction_quality", -0.02)
        else:
            raise ValueError(f"unknown feedback kind: {kind!r}")

        prox["threshold_offset"] = off
        prox["threshold_offset_by_app"] = by_app
        s.proactive = prox
        if self._settings is None:
            st.save(s, self.cfg)
        self.selfmem.record("feedback", context=f"{kind} (app={app})")
        return {"threshold_offset": off, "by_app": by_app}
