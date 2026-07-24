"""Impulse generator — tier 1, cheap and continuous (AERO-PRO-003).

Every daemon tick this watches world-state **deltas** and emits impulses. It never
calls a model: producers are plain functions over the current + previous world
state, recent-failure counts, and active thought threads. The strongest surviving
impulse (if any) is what the gate later considers — but the vast majority never
get that far, because the gate's threshold is high and impulses decay fast.

Hard rule — **AERO-PRO-001: proactive speech must never be timer-based.** So no
producer here keys on elapsed idle time alone. "User came back after being away"
is a *state transition* (away → active), which is a legitimate delta; "it's been
10 minutes, say something" is forbidden and deliberately absent.

Producers, and the signal each reads:

  * ``app_switch_novelty`` — the foreground app changed to something new.
  * ``return_from_away``   — activity transitioned away → active (a social opening).
  * ``repeated_failure``   — the user keeps hitting the same wall (concern).
  * ``thread_reactivation``— an active thought thread's trigger matches the world.

Adding a producer is the extension point; nothing else changes (the codebase's
interface → producers → generate pattern).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

from aero.proactive.impulse import Impulse, ImpulseSource
from aero.proactive.threads import ThoughtThreadStore
from aero.working_set import WorldState


@dataclass
class GenContext:
    """Everything a producer may read for one tick. All cheap, all local."""

    world: WorldState
    prev: WorldState | None
    now: float
    recent_failures: int = 0        # count of recent failure-ish events
    explicit_request: bool = False  # user asked Aero to talk (lowers the bar)
    threads: ThoughtThreadStore | None = None


Producer = Callable[[GenContext], "list[Impulse]"]


def _seen(world: WorldState | None, app: str | None) -> bool:
    return bool(world and app and world.active_app == app)


def app_switch_novelty(ctx: GenContext) -> list[Impulse]:
    """A newly-foregrounded app is a mild novelty signal. Deliberately weak —
    switching apps is normal; it should rarely clear the gate on its own."""
    app = ctx.world.active_app
    if not app:
        return []
    if ctx.prev is None or _seen(ctx.prev, app):
        return []  # no switch, or same app as before
    return [Impulse(
        source=ImpulseSource.NOVELTY,
        strength=0.25,
        subject=f"switched to {app}",
        detail=f"Aditya just switched to {app}"
               + (f" ({ctx.world.window_title})" if ctx.world.window_title else ""),
        created_at=ctx.now,
        decay_seconds=45.0,
    )]


def return_from_away(ctx: GenContext) -> list[Impulse]:
    """away → active transition: a social opening, not a timer. Aditya walking
    back to the machine is a real-world delta worth (maybe) acknowledging."""
    if ctx.prev is None:
        return []
    was_away = ctx.prev.activity_level in ("away", "idle")
    now_active = ctx.world.activity_level == "active"
    if not (was_away and now_active):
        return []
    return [Impulse(
        source=ImpulseSource.SOCIAL_URGE,
        strength=0.35,
        subject="user returned",
        detail="Aditya just came back to the keyboard after being away.",
        created_at=ctx.now,
        decay_seconds=30.0,
    )]


def repeated_failure(ctx: GenContext) -> list[Impulse]:
    """Repeated failure signals concern — strength scales with how many times the
    user has hit the wall (AERO-PRO-003: repeated_failure)."""
    n = ctx.recent_failures
    if n < 2:
        return []
    strength = min(0.9, 0.4 + 0.15 * (n - 2))  # 2→0.4, ramps toward 0.9
    return [Impulse(
        source=ImpulseSource.REPEATED_FAILURE,
        strength=strength,
        subject="repeated failure",
        detail=f"Aditya has hit the same problem about {n} times in a row.",
        created_at=ctx.now,
        decay_seconds=120.0,
    )]


def thread_reactivation(ctx: GenContext) -> list[Impulse]:
    """An unresolved thought thread whose trigger matches the current world
    reactivates (AERO-THT-001) — a strong reason to speak: Aero has been sitting
    on this. Matched against the active app, window title, project, and file."""
    if ctx.threads is None:
        return []
    signals = [ctx.world.active_app, ctx.world.window_title,
               str(ctx.world.extra.get("project") or ""),
               str(ctx.world.extra.get("file") or "")]
    out: list[Impulse] = []
    for thread in ctx.threads.matching(*signals):
        out.append(Impulse(
            source=ImpulseSource.THOUGHT_THREAD,
            strength=0.7,
            subject=f"thread: {thread.statement[:40]}",
            detail=f"Reactivated thought: \"{thread.statement}\"",
            created_at=ctx.now,
            decay_seconds=90.0,
            thread_id=thread.id,
        ))
    return out


#: The default producer set. Order doesn't matter — generate() collects all.
DEFAULT_PRODUCERS: tuple[Producer, ...] = (
    app_switch_novelty,
    return_from_away,
    repeated_failure,
    thread_reactivation,
)


@dataclass
class ImpulseGenerator:
    """Runs every producer for a tick and returns the impulses they emit."""

    producers: tuple[Producer, ...] = field(default=DEFAULT_PRODUCERS)

    def generate(self, ctx: GenContext) -> list[Impulse]:
        out: list[Impulse] = []
        for producer in self.producers:
            try:
                out.extend(producer(ctx))
            except Exception:
                # A misbehaving producer must never break the tick — the loop
                # around this catches too, but be defensive per-producer.
                continue
        return out

    def strongest(self, ctx: GenContext) -> Impulse | None:
        """The loudest live impulse this tick, or None if nothing fired."""
        impulses = [i for i in self.generate(ctx) if not i.is_stale(ctx.now)]
        if not impulses:
            return None
        return max(impulses, key=lambda i: i.current_strength(ctx.now))
