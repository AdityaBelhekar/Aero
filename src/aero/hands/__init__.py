"""Little Hands — the things Aero can *do* on your machine (v0.3 Pillar 5).

Framed as a friend doing you a favour, never an autonomous agent: launch an app,
open a URL, control media, organise a folder you allowed. Every capability is
opt-in, scoped, reversible-where-possible, and **audited**.

This is the plan's *safety milestone*: nothing here executes without passing the
consent gate (consent.py). The layering:

    Tool         one atomic action, declaring its scope + reversibility
    ToolRegistry the typed catalog of available tools
    ConsentGate  default-deny; reversible+granted -> act; irreversible -> confirm;
                 kill switch -> nothing; every decision explained
    HandsExecutor registry + gate + audit journal — the only way a tool runs

If a tool would delete, send, buy, or post, it is a **hard-gate** action that
always requires explicit confirmation, no matter how much authority is granted
(AERO-AUTH-002). That rule is structural here, not a prompt suggestion.
"""

from aero.hands.consent import ConsentDecision, ConsentGate, Verdict
from aero.hands.registry import ToolRegistry, default_registry
from aero.hands.tool import Tool, ToolResult

__all__ = [
    "ConsentDecision",
    "ConsentGate",
    "Tool",
    "ToolRegistry",
    "ToolResult",
    "Verdict",
    "default_registry",
]
