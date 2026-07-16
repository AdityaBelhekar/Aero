"""hands.* control ops (AERO-ACT via Control App). Hermetic, real tmp vault."""

from __future__ import annotations

import pytest

from aero.config import Config
from aero.control import ControlService


@pytest.fixture()
def svc(tmp_path, vault):
    from aero.memory.store import MemoryStore
    cfg = Config(home=tmp_path)
    s = ControlService(cfg, store=MemoryStore(vault, actor="test"))
    return s


def test_hands_tools_lists_registry(svc):
    r = svc.dispatch("hands.tools")
    assert r["ok"]
    names = {t["name"] for t in r["result"]["tools"]}
    assert {"open_url", "empty_trash"} <= names


def test_hands_run_refused_without_grant(svc):
    r = svc.dispatch("hands.run", {"tool": "open_url", "params": {"url": "http://x"}})
    assert r["ok"]
    assert r["result"]["executed"] is False
    assert r["result"]["decision"]["verdict"] == "refuse"


def test_hands_run_allowed_after_grant(svc):
    svc.dispatch("perms.grant", {"scope": "browser", "on": True})
    r = svc.dispatch("hands.run", {"tool": "open_url", "params": {"url": "http://x"}})
    assert r["result"]["executed"] is True
    assert r["result"]["decision"]["verdict"] == "allow"


def test_hands_run_hard_gate_needs_confirm(svc):
    svc.dispatch("perms.grant", {"scope": "files", "on": True})
    r = svc.dispatch("hands.run", {"tool": "empty_trash"})
    assert r["result"]["executed"] is False
    assert r["result"]["decision"]["verdict"] == "confirm"
    r2 = svc.dispatch("hands.run", {"tool": "empty_trash", "confirmed": True})
    assert r2["result"]["executed"] is True


def test_hands_log_records_attempts(svc):
    svc.dispatch("hands.run", {"tool": "open_url", "params": {}})  # refused
    entries = svc.dispatch("hands.log")["result"]["entries"]
    assert entries and entries[0]["tool"] == "open_url"
    assert entries[0]["verdict"] == "refuse"


def test_hands_run_unknown_tool(svc):
    r = svc.dispatch("hands.run", {"tool": "nope"})
    assert r["result"]["error"] and not r["result"]["executed"]
