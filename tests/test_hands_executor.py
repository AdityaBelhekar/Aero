"""HandsExecutor + skills + MCP bridge (AERO-ACT-505/506, gate enforcement)."""

from __future__ import annotations

from aero import settings as st
from aero.hands.consent import ConsentGate, Verdict
from aero.hands.executor import HandsExecutor
from aero.hands.journal import ActuatorJournal
from aero.hands.mcp_bridge import MCPToolSpec, bridge_tool
from aero.hands.registry import ToolRegistry
from aero.hands.skills import Skill, SkillRunner, load_skills
from aero.hands.tool import Tool, ToolResult


def _tool(name, scope, *, reversible=True, hard_gate=False):
    ran = {"n": 0}
    def run(p):
        ran["n"] += 1
        return ToolResult(ok=True, output=f"{name}:{p}")
    t = Tool(name, scope, "d", run, reversible=reversible, hard_gate=hard_gate)
    return t, ran


def _executor(settings, journal=None, tools=()):
    reg = ToolRegistry()
    rans = {}
    for name, scope, kw in tools:
        t, ran = _tool(name, scope, **kw)
        reg.register(t)
        rans[name] = ran
    gate = ConsentGate(settings=settings)
    return HandsExecutor(reg, gate, journal), rans


# -- executor gate enforcement ---------------------------------------------
def test_allowed_tool_executes():
    ex, rans = _executor(st.VoiceSettings(permissions={"apps": True}),
                         tools=[("open_app", "apps", {})])
    out = ex.run("open_app", {"name": "spotify"})
    assert out.executed and out.result.ok
    assert rans["open_app"]["n"] == 1


def test_refused_tool_does_not_execute():
    ex, rans = _executor(st.VoiceSettings(permissions={}),
                         tools=[("open_app", "apps", {})])
    out = ex.run("open_app", {"name": "x"})
    assert not out.executed and out.decision.verdict is Verdict.REFUSE
    assert rans["open_app"]["n"] == 0        # side-effect never ran


def test_hard_gate_needs_confirmation_then_runs():
    ex, rans = _executor(st.VoiceSettings(permissions={"files": True}),
                         tools=[("empty_trash", "files",
                                 {"reversible": False, "hard_gate": True})])
    out = ex.run("empty_trash", {})
    assert not out.executed and out.decision.verdict is Verdict.CONFIRM
    assert rans["empty_trash"]["n"] == 0     # NOT executed without confirm
    out2 = ex.run("empty_trash", {}, confirmed=True)
    assert out2.executed and rans["empty_trash"]["n"] == 1


def test_dry_run_never_executes_even_when_allowed():
    ex, rans = _executor(st.VoiceSettings(permissions={"apps": True}),
                         tools=[("open_app", "apps", {})])
    out = ex.run("open_app", {"name": "x"}, dry_run=True)
    assert out.dry_run and not out.executed
    assert out.decision.verdict is Verdict.ALLOW   # would have been allowed
    assert rans["open_app"]["n"] == 0              # but did not run


def test_unknown_tool():
    ex, _ = _executor(st.VoiceSettings())
    out = ex.run("nope")
    assert out.error and not out.executed


# -- journalling -----------------------------------------------------------
def test_executor_journals_allow_and_refuse(vault):
    j = ActuatorJournal(vault)
    ex, _ = _executor(st.VoiceSettings(permissions={"apps": True}), j,
                      tools=[("open_app", "apps", {}), ("secret", "shell", {})])
    ex.run("open_app", {"name": "x"})
    ex.run("secret", {})                     # shell ungranted -> refuse
    rows = j.recent()
    assert {r["verdict"] for r in rows} == {"allow", "refuse"}
    assert j.count(verdict=Verdict.REFUSE) == 1


# -- skills ----------------------------------------------------------------
def test_skill_runs_all_steps_when_granted():
    ex, rans = _executor(st.VoiceSettings(permissions={"apps": True, "media": True}),
                         tools=[("open_app", "apps", {}), ("media_control", "media", {})])
    skill = Skill.from_dict({"name": "s", "steps": [
        {"tool": "media_control", "params": {"action": "pause"}},
        {"tool": "open_app", "params": {"name": "journal"}}]})
    run = SkillRunner(ex).run(skill)
    assert run.completed and len(run.steps) == 2
    assert rans["open_app"]["n"] == 1 and rans["media_control"]["n"] == 1


def test_skill_stops_at_first_blocked_step():
    # media granted, apps NOT -> second step blocks
    ex, rans = _executor(st.VoiceSettings(permissions={"media": True}),
                         tools=[("media_control", "media", {}), ("open_app", "apps", {})])
    skill = Skill.from_dict({"name": "s", "steps": [
        {"tool": "media_control", "params": {}},
        {"tool": "open_app", "params": {}}]})
    run = SkillRunner(ex).run(skill)
    assert not run.completed and run.stopped_at == 1
    assert rans["open_app"]["n"] == 0        # blocked step never ran


def test_skill_dry_run_previews_without_executing():
    ex, rans = _executor(st.VoiceSettings(permissions={"apps": True}),
                         tools=[("open_app", "apps", {})])
    skill = Skill.from_dict({"name": "s", "steps": [{"tool": "open_app", "params": {}}]})
    run = SkillRunner(ex).run(skill, dry_run=True)
    assert len(run.steps) == 1 and rans["open_app"]["n"] == 0


def test_load_skills_from_file(tmp_path):
    p = tmp_path / "wind_down.json"
    p.write_text('{"name": "wind_down", "description": "chill", '
                 '"steps": [{"tool": "media_control", "params": {"action": "pause"}}]}')
    skills = load_skills(p)
    assert "wind_down" in skills
    assert skills["wind_down"].tools_used() == {"media_control"}


# -- MCP bridge ------------------------------------------------------------
def test_mcp_tool_is_gated_and_conservative():
    calls = []
    def invoker(name, params):
        calls.append((name, params))
        return {"echo": params}
    spec = MCPToolSpec(name="search", description="web search", params=("q",))
    tool = bridge_tool(spec, invoker)
    assert tool.name == "mcp.search" and tool.scope == "mcp"
    assert tool.reversible is False          # conservative default -> confirm path

    # ungranted mcp scope -> refused, invoker never called
    ex, _ = _executor(st.VoiceSettings())
    ex.registry.register(tool)
    out = ex.run("mcp.search", {"q": "x"})
    assert not out.executed and out.decision.verdict is Verdict.REFUSE
    assert calls == []

    # granted + confirmed -> runs the invoker
    ex2, _ = _executor(st.VoiceSettings(permissions={"mcp": True}))
    ex2.registry.register(bridge_tool(spec, invoker))
    out2 = ex2.run("mcp.search", {"q": "x"}, confirmed=True)
    assert out2.executed and out2.result.output == {"echo": {"q": "x"}}
