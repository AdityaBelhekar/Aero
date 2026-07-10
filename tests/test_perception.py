"""Tier-0 perception tests — hermetic (fabricated samples, no real Win32).

Live sensing is environment-dependent, so we test the pure logic: sample
semantics, world-state mapping, and app-switch detection.
"""

from __future__ import annotations

from aero.perception.tier0 import Tier0Sample, WorldStateProvider
from aero.working_set import WorldState


def test_sample_activity_levels():
    assert Tier0Sample(idle_seconds=10).activity_level == "active"
    assert Tier0Sample(idle_seconds=10).active is True
    assert Tier0Sample(idle_seconds=120).activity_level == "idle"
    assert Tier0Sample(idle_seconds=600).activity_level == "away"
    assert Tier0Sample(idle_seconds=120).active is False


def test_worldstate_from_ok_sample():
    s = Tier0Sample(window_title="foo - Chrome", process_name="chrome.exe",
                    idle_seconds=5, ok=True)
    ws = WorldState.from_tier0(s, time_str="Mon 10:00")
    assert ws.active_app == "chrome.exe"
    assert ws.window_title == "foo - Chrome"
    assert ws.activity_level == "active"
    rendered = ws.render()
    assert "chrome.exe" in rendered and "active" in rendered


def test_worldstate_from_unavailable_sample():
    ws = WorldState.from_tier0(Tier0Sample(ok=False), time_str="Mon 10:00")
    assert ws.active_app is None
    assert ws.time_str == "Mon 10:00"


def test_provider_detects_app_switch(monkeypatch):
    samples = iter([
        Tier0Sample(process_name="code.exe", window_title="a", ok=True),
        Tier0Sample(process_name="code.exe", window_title="a", ok=True),
        Tier0Sample(process_name="chrome.exe", window_title="b", ok=True),
    ])
    import aero.perception.tier0 as t0
    monkeypatch.setattr(t0, "sample_tier0", lambda: next(samples))

    prov = WorldStateProvider()
    _, sw1 = prov.poll()   # first sample, no prior -> no switch
    _, sw2 = prov.poll()   # same app -> no switch
    _, sw3 = prov.poll()   # code -> chrome -> switch
    assert sw1 is False
    assert sw2 is False
    assert sw3 is True


def test_provider_no_switch_when_unavailable(monkeypatch):
    import aero.perception.tier0 as t0
    monkeypatch.setattr(t0, "sample_tier0", lambda: Tier0Sample(ok=False))
    prov = WorldStateProvider()
    _, switched = prov.poll()
    assert switched is False
