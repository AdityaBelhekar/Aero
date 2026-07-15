"""Personality ambient scheduler (AERO-PRES-105). Deterministic (clock+rng injected)."""

from __future__ import annotations

import random
import time

from aero.perception.tier0 import Tier0Sample
from aero.presence.ambient import AmbientScheduler


def _at(hour: int) -> float:
    """Epoch for today at a given local hour (deterministic tags_for input)."""
    lt = time.localtime()
    return time.mktime((lt.tm_year, lt.tm_mon, lt.tm_mday, hour, 0, 0, 0, 0, -1))


def test_night_tag():
    s = AmbientScheduler()
    assert "night" in s.tags_for(None, now=_at(2))
    assert "night" in s.tags_for(None, now=_at(23))
    assert "morning" in s.tags_for(None, now=_at(8))
    assert "night" not in s.tags_for(None, now=_at(14))


def test_world_activity_tags():
    s = AmbientScheduler()
    active = Tier0Sample(window_title="main.py", process_name="code.exe", idle_seconds=2)
    tags = s.tags_for(active, now=_at(10))
    assert "active" in tags and "coding" in tags

    away = Tier0Sample(process_name="chrome.exe", idle_seconds=600)
    assert "away" in s.tags_for(away, now=_at(10))


def test_gaming_tag_from_window():
    s = AmbientScheduler()
    w = Tier0Sample(window_title="VALORANT", process_name="valorant.exe", idle_seconds=1)
    assert "gaming" in s.tags_for(w, now=_at(1))


def test_non_windows_sample_yields_only_time_tags():
    s = AmbientScheduler()
    # tier0 on Linux returns ok=False -> no world tags, just time
    tags = s.tags_for(Tier0Sample(ok=False), now=_at(2))
    assert tags == ["night"]


def test_weighting_boosts_context_clip():
    s = AmbientScheduler()
    # "active" should heavily boost glance_at_screen
    w = s.weighted_fidgets(["active"], mood="neutral")
    assert w["glance_at_screen"] > w["look_around"]
    # night boosts the sigh
    w2 = s.weighted_fidgets(["night"], mood="neutral")
    assert w2["bored_sigh"] > w2["glance_at_screen"]


def test_mood_boost_applies():
    s = AmbientScheduler()
    w = s.weighted_fidgets([], mood="tired")
    assert w["bored_sigh"] > w["look_around"]


def test_pick_is_deterministic_with_seeded_rng():
    s1 = AmbientScheduler(rng=random.Random(42))
    s2 = AmbientScheduler(rng=random.Random(42))
    w = Tier0Sample(process_name="valorant.exe", idle_seconds=1)
    p1 = [s1.pick(w, now=_at(1))[0] for _ in range(5)]
    p2 = [s2.pick(w, now=_at(1))[0] for _ in range(5)]
    assert p1 == p2
    assert all(c in s1.rig.fidgets for c in p1)


def test_pick_returns_tags():
    s = AmbientScheduler(rng=random.Random(1))
    w = Tier0Sample(process_name="valorant.exe", idle_seconds=1)
    clip, tags = s.pick(w, now=_at(1))
    assert clip is not None
    assert "gaming" in tags and "night" in tags


def test_pick_none_when_no_fidgets():
    from aero.presence.rig import RigManifest
    rig = RigManifest.from_dict({"states": {"idle": ["i"]}, "fidgets": []})
    s = AmbientScheduler(rig)
    clip, _ = s.pick(None, now=_at(12))
    assert clip is None


def test_cadence_due_and_reset():
    clock = {"t": 100.0}
    s = AmbientScheduler(clock=lambda: clock["t"], rng=random.Random(0),
                         min_interval=10, max_interval=10)
    assert s.due() is True             # never fired -> due
    s.reset()                          # gap fixed at 10 (min==max)
    clock["t"] = 105.0
    assert s.due() is False            # only 5s passed
    clock["t"] = 111.0
    assert s.due() is True             # 11s passed >= 10
