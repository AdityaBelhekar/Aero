"""Impulse decay + staleness (AERO-PRO-003: source/strength/decay)."""

from __future__ import annotations

from aero.proactive.impulse import Impulse, ImpulseSource


def _imp(strength=1.0, decay=60.0, created=0.0):
    return Impulse(ImpulseSource.NOVELTY, strength, "s", "d",
                   created_at=created, decay_seconds=decay)


def test_full_strength_at_birth():
    assert _imp(0.8).current_strength(0.0) == 0.8


def test_linear_decay_to_zero():
    imp = _imp(1.0, decay=100.0, created=0.0)
    assert imp.current_strength(0.0) == 1.0
    assert abs(imp.current_strength(50.0) - 0.5) < 1e-9
    assert imp.current_strength(100.0) == 0.0
    assert imp.current_strength(200.0) == 0.0  # never negative


def test_staleness_after_decay_window():
    imp = _imp(1.0, decay=30.0, created=10.0)
    assert not imp.is_stale(10.0)
    assert not imp.is_stale(39.0)
    assert imp.is_stale(40.0)      # decayed out — the moment passed


def test_zero_decay_is_immediately_stale():
    assert _imp(1.0, decay=0.0).is_stale(0.0)


def test_serialises_source_and_fields():
    imp = Impulse(ImpulseSource.THOUGHT_THREAD, 0.7, "subj", "detail",
                  created_at=0.0, thread_id="abc")
    d = imp.to_dict()
    assert d["source"] == "thought_thread" and d["thread_id"] == "abc"
