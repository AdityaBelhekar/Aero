"""HandsExecutor — the only path a tool ever runs (AERO-ACT-501..504/507).

Ties the three safety pieces together: look the tool up in the registry, ask the
ConsentGate, journal the decision, and only then — if ALLOWed and not a dry-run —
invoke the side-effect, journalling the outcome too. Nothing else in Aero calls
``tool.invoke`` directly; going through here is what makes consent + audit
unbypassable.

Guarantees (the ones the S-10 red-team checks):
  * a REFUSE or an unconfirmed CONFIRM never executes;
  * a dry-run never executes, even when ALLOWed;
  * every attempt is journalled before and after, so the record can't be skipped
    by a tool that throws.
"""

from __future__ import annotations

from dataclasses import dataclass

from aero.hands.consent import ConsentDecision, ConsentGate, Verdict
from aero.hands.journal import ActuatorJournal
from aero.hands.registry import ToolRegistry
from aero.hands.tool import ToolResult


@dataclass
class ExecutionOutcome:
    decision: ConsentDecision
    executed: bool
    dry_run: bool = False
    result: ToolResult | None = None
    error: str | None = None      # set when the tool name is unknown

    def to_dict(self) -> dict:
        return {
            "decision": self.decision.to_dict() if self.decision else None,
            "executed": self.executed,
            "dry_run": self.dry_run,
            "result": (None if self.result is None else {
                "ok": self.result.ok, "output": self.result.output,
                "error": self.result.error}),
            "error": self.error,
        }


class HandsExecutor:
    def __init__(self, registry: ToolRegistry, gate: ConsentGate,
                 journal: ActuatorJournal | None = None):
        self.registry = registry
        self.gate = gate
        self.journal = journal

    def run(self, tool_name: str, params: dict | None = None, *,
            confirmed: bool = False, dry_run: bool = False) -> ExecutionOutcome:
        tool = self.registry.get(tool_name)
        if tool is None:
            return ExecutionOutcome(decision=None, executed=False,
                                    error=f"unknown tool: {tool_name}")

        decision = self.gate.evaluate(tool, params, confirmed=confirmed)

        # Dry-run: report the decision + what would happen, never touch the world.
        if dry_run:
            self._journal(decision, params, executed=False, dry_run=True)
            return ExecutionOutcome(decision, executed=False, dry_run=True)

        # Blocked (refused, or needs confirmation and didn't get it).
        if decision.verdict is not Verdict.ALLOW:
            self._journal(decision, params, executed=False)
            return ExecutionOutcome(decision, executed=False)

        # Approved -> run the side-effect and journal the outcome.
        result = tool.invoke(params or {})
        self._journal(decision, params, executed=True, result=result)
        return ExecutionOutcome(decision, executed=True, result=result)

    def _journal(self, decision, params, *, executed, dry_run=False, result=None):
        if self.journal is not None:
            self.journal.record(decision, params, executed=executed,
                                dry_run=dry_run, result=result)
