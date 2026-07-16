"""MCP bridge — turn MCP-server tools into gated Aero tools (AERO-ACT-506).

The "any tool" analogue of LiteLLM for brains: existing MCP servers expose tools;
this wraps each as an Aero ``Tool`` so it flows through the *same* consent gate,
journal, and executor. Big reach, little code — the safety machinery is reused
wholesale.

Conservative by default (v0.3 Rule 7 — consent is the API): a bridged tool lands
in the ``mcp`` permission scope (grant it explicitly), and unless a spec says
otherwise it's treated as **irreversible** — so it hits the confirmation path
rather than running silently, because we can't know what a third-party tool does.

The transport (an actual MCP client session) is injected as ``invoker`` — a
callable ``(tool_name, params) -> result`` — so the bridge logic is real and
testable now, and wiring a live MCP client later is just supplying that callable.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

from aero.hands.tool import Tool, ToolResult

# invoker(tool_name, params) -> raw result (any JSON-able value). Supplied by a
# real MCP client session, or a fake in tests.
Invoker = Callable[[str, dict], object]


@dataclass
class MCPToolSpec:
    name: str
    description: str = ""
    reversible: bool = False      # conservative: unknown third-party effect
    hard_gate: bool = False
    params: tuple[str, ...] = field(default_factory=tuple)


def bridge_tool(spec: MCPToolSpec, invoker: Invoker, *, scope: str = "mcp") -> Tool:
    """Wrap one MCP tool as a consent-gated Aero Tool."""
    def run(params: dict) -> ToolResult:
        try:
            out = invoker(spec.name, params or {})
            return ToolResult(ok=True, output=out)
        except Exception as e:
            return ToolResult(ok=False, error=f"{type(e).__name__}: {e}")

    return Tool(
        name=f"mcp.{spec.name}",
        scope=scope,
        description=spec.description or f"MCP tool {spec.name}",
        run=run,
        reversible=spec.reversible,
        hard_gate=spec.hard_gate,
        params=spec.params,
    )


def bridge_all(specs: list[MCPToolSpec], invoker: Invoker, *,
               scope: str = "mcp") -> list[Tool]:
    """Wrap a server's advertised tools. Register the results in a ToolRegistry to
    make them available to the executor (behind the mcp-scope grant)."""
    return [bridge_tool(s, invoker, scope=scope) for s in specs]
