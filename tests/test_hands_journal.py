"""Actuator audit journal (AERO-ACT-504). Hermetic — real tmp vault."""

from __future__ import annotations

from aero.hands.consent import ConsentDecision, Verdict
from aero.hands.journal import ActuatorJournal
from aero.hands.tool import ToolResult


def _decision(verdict=Verdict.ALLOW, tool="open_url", scope="browser"):
    return ConsentDecision(verdict, "reason", tool, scope)


def test_records_allowed_execution(vault):
    j = ActuatorJournal(vault)
    j.record(_decision(), {"url": "http://x"}, executed=True,
             result=ToolResult(ok=True, output="done"))
    rows = j.recent()
    assert len(rows) == 1
    r = rows[0]
    assert r["tool"] == "open_url" and r["verdict"] == "allow"
    assert r["executed"] == 1 and r["outcome"] == "ok"


def test_records_refusal_not_executed(vault):
    j = ActuatorJournal(vault)
    j.record(_decision(Verdict.REFUSE), {"x": 1}, executed=False)
    r = j.recent()[0]
    assert r["verdict"] == "refuse" and r["executed"] == 0
    assert r["outcome"] is None


def test_records_dry_run(vault):
    j = ActuatorJournal(vault)
    j.record(_decision(), {}, executed=False, dry_run=True)
    assert j.recent()[0]["dry_run"] == 1


def test_records_error_outcome(vault):
    j = ActuatorJournal(vault)
    j.record(_decision(), {}, executed=True,
             result=ToolResult(ok=False, error="boom"))
    r = j.recent()[0]
    assert r["outcome"] == "error" and r["error"] == "boom"


def test_recent_filters_by_tool(vault):
    j = ActuatorJournal(vault)
    j.record(_decision(tool="open_url"), {})
    j.record(_decision(tool="empty_trash"), {})
    assert len(j.recent(tool="empty_trash")) == 1
    assert j.recent()[0]["tool"] == "empty_trash"     # newest first


def test_count_by_verdict(vault):
    j = ActuatorJournal(vault)
    j.record(_decision(Verdict.ALLOW), {})
    j.record(_decision(Verdict.REFUSE), {})
    j.record(_decision(Verdict.REFUSE), {})
    assert j.count() == 3
    assert j.count(verdict=Verdict.REFUSE) == 2


def test_params_json_roundtrips_unicode(vault):
    j = ActuatorJournal(vault)
    j.record(_decision(), {"msg": "नको यार"})
    import json
    assert json.loads(j.recent()[0]["params_json"])["msg"] == "नको यार"
