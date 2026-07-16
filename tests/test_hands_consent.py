"""ConsentGate — default-deny, tiered confirm, kill switch (AERO-ACT-502/503/507)."""

from __future__ import annotations

from aero import settings as st
from aero.hands.consent import ConsentGate, Verdict
from aero.hands.tool import Tool, ToolResult

_ok = lambda p: ToolResult(ok=True)  # noqa: E731


def _tool(scope="apps", *, reversible=True, hard_gate=False, name="t"):
    return Tool(name, scope, "desc", _ok, reversible=reversible, hard_gate=hard_gate)


def _gate(**settings_kw):
    s = st.VoiceSettings(**settings_kw)
    return ConsentGate(settings=s)


# -- default-deny ----------------------------------------------------------
def test_ungranted_scope_refused():
    d = _gate().evaluate(_tool("apps"))
    assert d.verdict is Verdict.REFUSE
    assert "not granted" in d.reason


def test_granted_reversible_allowed():
    d = _gate(permissions={"apps": True}).evaluate(_tool("apps"))
    assert d.verdict is Verdict.ALLOW


# -- kill switch overrides everything --------------------------------------
def test_killswitch_refuses_even_granted():
    d = _gate(permissions={"apps": True}, killswitch=True).evaluate(_tool("apps"))
    assert d.verdict is Verdict.REFUSE
    assert "kill switch" in d.reason


def test_killswitch_refuses_hard_gate_even_confirmed():
    g = _gate(permissions={"files": True}, killswitch=True)
    d = g.evaluate(_tool("files", hard_gate=True), confirmed=True)
    assert d.verdict is Verdict.REFUSE


# -- tiered confirmation ---------------------------------------------------
def test_hard_gate_requires_confirmation():
    g = _gate(permissions={"files": True})
    d = g.evaluate(_tool("files", reversible=False, hard_gate=True))
    assert d.verdict is Verdict.CONFIRM
    assert d.requires_confirmation is True


def test_hard_gate_allowed_once_confirmed():
    g = _gate(permissions={"files": True})
    d = g.evaluate(_tool("files", reversible=False, hard_gate=True), confirmed=True)
    assert d.verdict is Verdict.ALLOW


def test_irreversible_requires_confirmation_even_without_hard_gate():
    g = _gate(permissions={"files": True})
    d = g.evaluate(_tool("files", reversible=False, hard_gate=False))
    assert d.verdict is Verdict.CONFIRM


def test_hard_gate_still_refused_if_scope_ungranted():
    # confirmation cannot bypass a missing grant
    g = _gate(permissions={})
    d = g.evaluate(_tool("files", reversible=False, hard_gate=True), confirmed=True)
    assert d.verdict is Verdict.REFUSE
    assert "not granted" in d.reason


# -- live settings ---------------------------------------------------------
def test_gate_reads_settings_live(tmp_path):
    from aero.config import Config
    cfg = Config(home=tmp_path)
    gate = ConsentGate(cfg)                      # loads live each evaluate
    assert gate.evaluate(_tool("apps")).verdict is Verdict.REFUSE
    s = st.load(cfg); s.permissions = {"apps": True}; st.save(s, cfg)
    assert gate.evaluate(_tool("apps")).verdict is Verdict.ALLOW
    s.killswitch = True; st.save(s, cfg)
    assert gate.evaluate(_tool("apps")).verdict is Verdict.REFUSE


def test_decision_serialises():
    d = _gate().evaluate(_tool("apps"))
    j = d.to_dict()
    assert j["verdict"] == "refuse" and j["tool"] == "t" and j["scope"] == "apps"
