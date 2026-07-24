"""Impulse generator — tier-1 producers over world deltas (AERO-PRO-001/003).

The load-bearing guarantee tested here: proactive speech is **never timer-based**
(AERO-PRO-001). A world that simply sits still — however long — produces no
impulses. Only *deltas* and content triggers do.
"""

from __future__ import annotations

from aero.memory.store import MemoryStore
from aero.proactive.generator import GenContext, ImpulseGenerator
from aero.proactive.impulse import ImpulseSource
from aero.proactive.threads import ThoughtThreadStore
from aero.working_set import WorldState


def _w(app=None, title=None, activity="idle", **extra):
    return WorldState(active_app=app, window_title=title,
                      activity_level=activity, extra=extra)


def _gen(**ctx_kw):
    ctx = GenContext(now=100.0, **ctx_kw)
    return ImpulseGenerator().generate(ctx)


def test_still_world_produces_nothing_no_timer():
    # Same app, present but idle, no threads, no failures — a long quiet stretch.
    w = _w("code.exe", activity="idle")
    assert _gen(world=w, prev=w) == []            # NOT timer-based (AERO-PRO-001)


def test_first_tick_has_no_prior_no_switch():
    assert _gen(world=_w("code.exe"), prev=None) == []


def test_app_switch_emits_weak_novelty():
    out = _gen(world=_w("chrome.exe"), prev=_w("code.exe"))
    assert len(out) == 1
    assert out[0].source is ImpulseSource.NOVELTY
    assert out[0].strength < 0.4     # switching apps is normal; kept quiet


def test_return_from_away_emits_social_urge():
    out = _gen(world=_w("code.exe", activity="active"),
               prev=_w("code.exe", activity="away"))
    assert any(i.source is ImpulseSource.SOCIAL_URGE for i in out)


def test_repeated_failure_scales_with_count():
    two = _gen(world=_w("code.exe"), prev=_w("code.exe"), recent_failures=2)
    many = _gen(world=_w("code.exe"), prev=_w("code.exe"), recent_failures=6)
    assert two and many
    f2 = next(i for i in two if i.source is ImpulseSource.REPEATED_FAILURE)
    f6 = next(i for i in many if i.source is ImpulseSource.REPEATED_FAILURE)
    assert f6.strength > f2.strength


def test_single_failure_is_not_yet_concern():
    out = _gen(world=_w("code.exe"), prev=_w("code.exe"), recent_failures=1)
    assert not any(i.source is ImpulseSource.REPEATED_FAILURE for i in out)


def test_thread_reactivation_fires_on_trigger_match(vault):
    ts = ThoughtThreadStore(MemoryStore(vault, actor="proactive"))
    ts.open("we approached this backwards", ["impulse"])
    out = _gen(world=_w("editor", title="impulse.py — Aero"), prev=_w("editor"),
               threads=ts)
    thread_imps = [i for i in out if i.source is ImpulseSource.THOUGHT_THREAD]
    assert len(thread_imps) == 1
    assert thread_imps[0].thread_id is not None
    assert thread_imps[0].strength >= 0.6     # a strong reason: Aero sat on this


def test_strongest_picks_loudest_live_impulse(vault):
    ts = ThoughtThreadStore(MemoryStore(vault, actor="proactive"))
    ts.open("idea", ["impulse"])
    ctx = GenContext(world=_w("chrome.exe", title="impulse notes"),
                     prev=_w("code.exe"), now=100.0, threads=ts)
    strongest = ImpulseGenerator().strongest(ctx)
    # thread (0.7) beats the app-switch novelty (0.25)
    assert strongest.source is ImpulseSource.THOUGHT_THREAD
