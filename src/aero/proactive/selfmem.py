"""Self-memory — Aero remembers what it did, including its silences.

AERO-SELF-001: Aero remembers its own actions, mistakes, initiated conversations,
and corrections. AERO-PRO-006 sharpens this for proactivity: *every* gate decision
— including staying silent — is logged with its reasoning, so a suppressed impulse
can still inform a later moment ("I noticed this an hour ago but you were busy").

This is a thin typed writer/reader over the ``self_memory`` table (schema v1).
Writes go through the audited ``Repository`` like every other memory mutation.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from aero.memory.store import MemoryStore
from aero.vault.connection import now_iso


@dataclass
class SelfMemoryEntry:
    id: str
    ts: str
    action: str            # 'spoke' | 'stayed_silent' | 'acted' | 'delegated' | ...
    context: str | None
    outcome: str | None
    lesson: str | None

    def to_dict(self) -> dict:
        return {"id": self.id, "ts": self.ts, "action": self.action,
                "context": self.context, "outcome": self.outcome, "lesson": self.lesson}


class SelfMemoryLog:
    """Append + read Aero's memory of its own decisions."""

    def __init__(self, store: MemoryStore):
        self.store = store

    def record(self, action: str, *, context: str | None = None,
               outcome: str | None = None, lesson: str | None = None) -> str:
        """Log one self-action. ``context`` should carry the *reasoning* so a
        suppressed impulse can be resurfaced later (AERO-PRO-006)."""
        entry_id = uuid.uuid4().hex
        self.store.repo.insert("self_memory", {
            "id": entry_id,
            "ts": now_iso(),
            "action": action,
            "context": context,
            "outcome": outcome,
            "lesson": lesson,
        })
        return entry_id

    def recent(self, *, limit: int = 20, action: str | None = None
               ) -> list[SelfMemoryEntry]:
        sql = "SELECT * FROM self_memory"
        params: tuple = ()
        if action is not None:
            sql += " WHERE action = ?"
            params = (action,)
        sql += " ORDER BY ts DESC, id DESC LIMIT ?"
        params = (*params, limit)
        rows = self.store.vault.conn.execute(sql, params).fetchall()
        return [SelfMemoryEntry(r["id"], r["ts"], r["action"], r["context"],
                                r["outcome"], r["lesson"]) for r in rows]

    def counts(self) -> dict[str, int]:
        """How many of each action Aero has taken — the honest activity ledger."""
        rows = self.store.vault.conn.execute(
            "SELECT action, COUNT(*) AS n FROM self_memory GROUP BY action"
        ).fetchall()
        return {r["action"]: r["n"] for r in rows}
