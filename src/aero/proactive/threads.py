"""Thought threads — persistent unresolved ideas that reactivate on triggers.

AERO-THT-001: a thought thread is a persistent *unresolved* idea (not a
consciousness claim) with associations and **reactivation triggers** — file
paths, topics, projects, people. When the world matches a trigger, the thread
reactivates and can become a THOUGHT_THREAD impulse: "wait — I think we
approached this backwards."

AERO-THT-002 lifecycle: ``active`` → ``dormant`` (aged out or the user lost
interest) → ``resolved`` (explicitly closed or superseded). An **active cap**
(default 20) keeps the working set from flooding — when a new thread would push
past the cap, the least-recently-active thread goes dormant.

Storage is the ``thought_threads`` table (schema v1); writes go through the
audited ``Repository``. Trigger matching is a cheap case-insensitive substring
test against world-state signals — no model call (this feeds tier 1).
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass

from aero.memory.store import MemoryStore
from aero.vault.connection import now_iso

#: AERO-THT-002 active-thread cap — the working set never floods.
ACTIVE_CAP = 20


@dataclass
class ThoughtThread:
    id: str
    statement: str
    status: str                 # 'active' | 'dormant' | 'resolved'
    triggers: list[str]
    created_at: str
    last_active: str

    def matches(self, *signals: str | None) -> bool:
        """True if any non-empty signal contains any trigger (case-insensitive)."""
        hay = " ".join(s.lower() for s in signals if s)
        if not hay:
            return False
        return any(t.strip() and t.lower() in hay for t in self.triggers)

    def to_dict(self) -> dict:
        return {"id": self.id, "statement": self.statement, "status": self.status,
                "triggers": self.triggers, "created_at": self.created_at,
                "last_active": self.last_active}


def _row_to_thread(row) -> ThoughtThread:
    triggers = json.loads(row["triggers_json"]) if row["triggers_json"] else []
    return ThoughtThread(row["id"], row["statement"], row["status"], triggers,
                         row["created_at"], row["last_active"])


class ThoughtThreadStore:
    """Typed read/write over ``thought_threads`` with the AERO-THT-002 lifecycle."""

    def __init__(self, store: MemoryStore, *, active_cap: int = ACTIVE_CAP):
        self.store = store
        self.active_cap = active_cap

    # -- writes ------------------------------------------------------------
    def open(self, statement: str, triggers: list[str] | None = None) -> ThoughtThread:
        """Start a new active thread. If this would exceed the active cap, the
        least-recently-active thread is demoted to dormant first."""
        ts = now_iso()
        thread = ThoughtThread(uuid.uuid4().hex, statement, "active",
                               triggers or [], ts, ts)
        self.store.repo.insert("thought_threads", {
            "id": thread.id,
            "statement": statement,
            "status": "active",
            "triggers_json": json.dumps(thread.triggers, ensure_ascii=False),
            "created_at": ts,
            "last_active": ts,
        })
        self._enforce_cap()
        return thread

    def touch(self, thread_id: str) -> None:
        """Mark a thread reactivated now (bumps last_active, revives if dormant)."""
        self.store.repo.update("thought_threads", thread_id,
                               {"status": "active", "last_active": now_iso()})

    def set_status(self, thread_id: str, status: str) -> None:
        self.store.repo.update("thought_threads", thread_id,
                               {"status": status, "last_active": now_iso()})

    def resolve(self, thread_id: str) -> None:
        """Close a thread — explicitly finished or superseded (AERO-THT-002)."""
        self.set_status(thread_id, "resolved")

    def _enforce_cap(self) -> None:
        active = self.active()
        overflow = len(active) - self.active_cap
        if overflow <= 0:
            return
        # Oldest-active first are demoted; active() is newest-first so take the tail.
        for thread in active[len(active) - overflow:]:
            self.store.repo.update("thought_threads", thread.id, {"status": "dormant"})

    # -- reads -------------------------------------------------------------
    def active(self) -> list[ThoughtThread]:
        rows = self.store.vault.conn.execute(
            "SELECT * FROM thought_threads WHERE status='active' "
            "ORDER BY last_active DESC"
        ).fetchall()
        return [_row_to_thread(r) for r in rows]

    def all(self, *, status: str | None = None) -> list[ThoughtThread]:
        sql = "SELECT * FROM thought_threads"
        params: tuple = ()
        if status is not None:
            sql += " WHERE status = ?"
            params = (status,)
        sql += " ORDER BY last_active DESC"
        rows = self.store.vault.conn.execute(sql, params).fetchall()
        return [_row_to_thread(r) for r in rows]

    def matching(self, *signals: str | None) -> list[ThoughtThread]:
        """Active threads whose triggers fire against the given world signals."""
        return [t for t in self.active() if t.matches(*signals)]
