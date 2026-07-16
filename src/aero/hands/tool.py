"""Tool — one atomic action Aero can perform, with its safety metadata (AERO-ACT-501).

A tool is deliberately small: a name, the permission *scope* it needs (matching
settings.PERMISSION_SCOPES), whether it's *reversible*, whether it's a *hard-gate*
action (delete/send/buy/post — always confirm, AERO-AUTH-002), a human description,
and a ``run`` callable that does the actual side-effect.

The side-effect lives in ``run`` and is only ever invoked by the HandsExecutor
*after* the consent gate approves — so a Tool object on its own is inert. Keeping
``run`` injectable also makes every tool testable without touching the real OS.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ToolResult:
    ok: bool
    output: Any = None
    error: str | None = None
    dry_run: bool = False


# A tool's side-effect: params in, ToolResult out. Raising is fine — the executor
# catches and journals the failure.
RunFn = Callable[[dict], ToolResult]


@dataclass
class Tool:
    name: str
    scope: str                       # permission scope required (settings.PERMISSION_SCOPES)
    description: str
    run: RunFn
    reversible: bool = True          # can its effect be undone?
    #: Hard-gate: irreversible + consequential (delete/send/buy/post). ALWAYS
    #: requires explicit confirmation regardless of how much authority is granted.
    hard_gate: bool = False
    #: Declared parameter names (for validation / UI hints). Optional.
    params: tuple[str, ...] = field(default_factory=tuple)

    def describe(self) -> dict:
        return {
            "name": self.name, "scope": self.scope, "description": self.description,
            "reversible": self.reversible, "hard_gate": self.hard_gate,
            "params": list(self.params),
        }

    def invoke(self, params: dict) -> ToolResult:
        """Run the side-effect. NEVER call this directly — go through the
        HandsExecutor so consent + audit are enforced. Present so tests and the
        executor share one code path."""
        try:
            return self.run(params or {})
        except Exception as e:  # a tool blowing up is a normal outcome, not a crash
            return ToolResult(ok=False, error=f"{type(e).__name__}: {e}")
