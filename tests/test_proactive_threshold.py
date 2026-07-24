"""Context-dependent gate threshold (AERO-PRO-004)."""

from __future__ import annotations

from aero.proactive.threshold import SILENCE_CEILING, ThresholdInputs, compute_threshold


def test_quiet_hours_hits_silence_ceiling():
    # Above any possible impulse strength -> Aero cannot speak.
    assert compute_threshold(ThresholdInputs(quiet_hours=True)) == SILENCE_CEILING


def test_focused_active_raises_vs_idle():
    active = compute_threshold(ThresholdInputs(activity_level="active"))
    idle = compute_threshold(ThresholdInputs(activity_level="idle"))
    assert active > idle  # never interrupt focused work as readily


def test_away_raises_hard():
    away = compute_threshold(ThresholdInputs(activity_level="away"))
    idle = compute_threshold(ThresholdInputs(activity_level="idle"))
    assert away > idle  # no audience -> hold back


def test_explicit_request_lowers_strongly():
    # Even from a focused state, "talk to me" pulls the bar right down...
    t = compute_threshold(ThresholdInputs(activity_level="active", explicit_request=True))
    assert t <= 0.15
    # ...but never to zero: the gate can still choose silence.
    assert t > 0.0


def test_chattiness_lowers_talkative_raises_reserved():
    talkative = compute_threshold(ThresholdInputs(chattiness=1.0))
    reserved = compute_threshold(ThresholdInputs(chattiness=0.0))
    assert talkative < reserved


def test_cold_start_familiarity_raises_bar():
    # A new Aero (low familiarity) is more conservative than a mature one.
    cold = compute_threshold(ThresholdInputs(familiarity=0.0))
    warm = compute_threshold(ThresholdInputs(familiarity=1.0))
    assert cold > warm


def test_learned_offset_folds_in():
    base = compute_threshold(ThresholdInputs())
    quieter = compute_threshold(ThresholdInputs(learned_offset=0.3))
    assert quieter > base  # "don't interrupt me" durably raises the bar


def test_result_stays_in_band():
    # Piling on positive offsets can't exceed the sane ceiling (below silence).
    t = compute_threshold(ThresholdInputs(activity_level="away", chattiness=0.0,
                                          familiarity=0.0, learned_offset=1.0))
    assert t <= 1.2
