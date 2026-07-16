"""Tool protocol + registry (AERO-ACT-501). Hermetic — nothing real runs."""

from __future__ import annotations

import pytest

from aero.hands.registry import ToolRegistry, default_registry
from aero.hands.tool import Tool, ToolResult


def _spy_tool(name="t", scope="apps", **kw):
    calls = []
    def run(params):
        calls.append(params)
        return ToolResult(ok=True, output="done")
    return Tool(name, scope, "desc", run, **kw), calls


def test_tool_describe():
    t, _ = _spy_tool(hard_gate=True, reversible=False, params=("x",))
    d = t.describe()
    assert d["scope"] == "apps" and d["hard_gate"] is True
    assert d["reversible"] is False and d["params"] == ["x"]


def test_tool_invoke_runs_side_effect():
    t, calls = _spy_tool()
    r = t.invoke({"a": 1})
    assert r.ok and r.output == "done"
    assert calls == [{"a": 1}]


def test_tool_invoke_catches_exceptions():
    def boom(params):
        raise RuntimeError("kaboom")
    t = Tool("x", "apps", "d", boom)
    r = t.invoke({})
    assert r.ok is False and "kaboom" in r.error


def test_registry_register_get_list():
    reg = ToolRegistry()
    t, _ = _spy_tool("open_url", "browser")
    reg.register(t)
    assert reg.get("open_url") is t
    assert reg.get("missing") is None
    assert [x.name for x in reg.list()] == ["open_url"]


def test_registry_rejects_duplicate():
    reg = ToolRegistry()
    t, _ = _spy_tool("dup")
    reg.register(t)
    with pytest.raises(ValueError):
        reg.register(t)


def test_default_registry_has_expected_tools():
    reg = default_registry()
    names = {t.name for t in reg.list()}
    assert {"open_url", "open_app", "media_control", "list_files"} <= names


def test_default_registry_empty_trash_is_hard_gate():
    t = default_registry().get("empty_trash")
    assert t.hard_gate is True and t.reversible is False
    assert t.scope == "files"


def test_list_files_tool_reads_directory(tmp_path):
    (tmp_path / "a.txt").write_text("x")
    (tmp_path / "b.txt").write_text("y")
    t = default_registry().get("list_files")
    r = t.invoke({"path": str(tmp_path)})
    assert r.ok and r.output["entries"] == ["a.txt", "b.txt"]


def test_echo_tools_have_no_real_side_effect():
    t = default_registry().get("open_url")
    r = t.invoke({"url": "http://x"})
    assert r.ok and r.output["action"] == "open_url"
