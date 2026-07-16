"""ActuatorJournal — the append-only record of everything the hands tried (AERO-ACT-504).

Every tool call — allowed and run, refused by the gate, awaiting confirmation, or a
dry-run — is written here with its decision and outcome. This is what makes actions
*accountable*: the user (via the memory/permissions UI) can see exactly what Aero
did, what it was stopped from doing, and why. Separate from the vault's mutation
``audit_log``; this is the log of the hands, not of memory writes.

Writes go straight to the ``actuator_log`` table on the vault connection and commit
immediately, so a crash mid-action never loses the record of the attempt.
"""

from __future__ import annotations

import json

from aero.hands.consent import ConsentDecision, Verdict
from aero.hands.tool import ToolResult
from aero.vault.connection import Vault, now_iso


class ActuatorJournal:
    def __init__(self, vault: Vault):
        self.vault = vault

    def record(
        self,
        decision: ConsentDecision,
        params: dict | None,
        *,
        executed: bool = False,
        dry_run: bool = False,
        result: ToolResult | None = None,
    ) -> int:
        outcome = None
        error = None
        if result is not None:
            outcome = "ok" if result.ok else "error"
            error = result.error
        cur = self.vault.conn.execute(
            "INSERT INTO actuator_log "
            "(ts, tool, scope, params_json, verdict, reason, executed, dry_run, "
            " outcome, error) VALUES (?,?,?,?,?,?,?,?,?,?)",
            (
                now_iso(), decision.tool, decision.scope,
                json.dumps(params or {}, ensure_ascii=False),
                decision.verdict.value, decision.reason,
                int(executed), int(dry_run), outcome, error,
            ),
        )
        self.vault.conn.commit()
        return cur.lastrowid

    def recent(self, limit: int = 50, *, tool: str | None = None) -> list[dict]:
        sql = "SELECT * FROM actuator_log"
        args: list = []
        if tool:
            sql += " WHERE tool = ?"
            args.append(tool)
        sql += " ORDER BY id DESC LIMIT ?"
        args.append(limit)
        return [dict(r) for r in self.vault.conn.execute(sql, args).fetchall()]

    def count(self, *, verdict: Verdict | None = None) -> int:
        if verdict is None:
            return self.vault.conn.execute(
                "SELECT COUNT(*) AS n FROM actuator_log").fetchone()["n"]
        return self.vault.conn.execute(
            "SELECT COUNT(*) AS n FROM actuator_log WHERE verdict = ?",
            (verdict.value,)).fetchone()["n"]
