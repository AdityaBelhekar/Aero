"""ToolRegistry + a starter set of tools (AERO-ACT-501).

The registry is the typed catalog the executor and UI read. The starter tools are
deliberately *light and playful* (v0.3 Pillar 5) and, for safety + portability,
their ``run`` currently **echoes intent** rather than driving the real OS — the
consent gate, audit journal, and skills are what M12 delivers; wiring each tool to
a real platform action (xdg-open, media keys, file ops in an allowed folder) is a
follow-on that changes only the ``run`` bodies, never the safety machinery around
them.

One deliberately dangerous entry (``empty_trash``: irreversible, hard-gate) exists
so the confirmation path and the S-10 red-team have a real hard-gate to exercise.
"""

from __future__ import annotations

from aero.hands.tool import Tool, ToolResult


class ToolRegistry:
    def __init__(self):
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        if tool.name in self._tools:
            raise ValueError(f"tool already registered: {tool.name}")
        self._tools[tool.name] = tool

    def get(self, name: str) -> Tool | None:
        return self._tools.get(name)

    def list(self) -> list[Tool]:
        return list(self._tools.values())

    def describe(self) -> list[dict]:
        return [t.describe() for t in self._tools.values()]


# -- starter tools (echo intent; see module docstring) ---------------------
def _echo(action: str):
    def run(params: dict) -> ToolResult:
        return ToolResult(ok=True, output={"action": action, "params": params})
    return run


def _list_files(params: dict) -> ToolResult:
    """The one genuinely-acting starter tool: a read-only directory listing
    (safe, reversible). Reads only; never writes."""
    import os
    path = params.get("path", ".")
    try:
        entries = sorted(os.listdir(path))[:200]
        return ToolResult(ok=True, output={"path": path, "entries": entries})
    except OSError as e:
        return ToolResult(ok=False, error=str(e))


def default_registry() -> ToolRegistry:
    reg = ToolRegistry()
    for tool in (
        Tool("open_url", "browser", "Open a URL in the browser",
             _echo("open_url"), reversible=True, params=("url",)),
        Tool("open_app", "apps", "Launch an application",
             _echo("open_app"), reversible=True, params=("name",)),
        Tool("close_app", "apps", "Close an application",
             _echo("close_app"), reversible=True, params=("name",)),
        Tool("media_control", "media", "Play/pause/skip media",
             _echo("media_control"), reversible=True, params=("action",)),
        Tool("list_files", "files", "List files in an allowed folder",
             _list_files, reversible=True, params=("path",)),
        Tool("move_file", "files", "Move/rename a file (undoable)",
             _echo("move_file"), reversible=True, params=("src", "dst")),
        # -- hard-gate: irreversible + consequential -> ALWAYS confirm --
        Tool("empty_trash", "files", "Permanently empty the trash",
             _echo("empty_trash"), reversible=False, hard_gate=True),
    ):
        reg.register(tool)
    return reg
