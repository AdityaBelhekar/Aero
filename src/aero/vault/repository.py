"""Mutation layer that guarantees the audit journal (AERO-VLT-002).

Every insert/update/delete to a memory-bearing table goes through here so that a
``before``/``after`` snapshot lands in ``audit_log``. Read paths can hit the
connection directly; writes should not, or the journal loses coverage.

This is deliberately small and generic for Milestone 1 — typed repositories for
each memory system arrive in Milestone 2. The point right now is that the
audit-on-write invariant exists from the very first row written.
"""

from __future__ import annotations

import json
from typing import Any, Mapping

from aero.vault.connection import Vault, now_iso

# Tables whose mutations are journaled. audit_log and meta are intentionally
# excluded (journaling the journal is noise; meta is bookkeeping).
_JOURNALED = {
    "memories",
    "memory_social",
    "edges",
    "embeddings",
    "raw_events",
    "beliefs_history",
    "boundaries",
    "self_memory",
    "thought_threads",
    "relationship_state",
    "permissions",
}


def _row_to_dict(row: Any) -> dict | None:
    if row is None:
        return None
    return {k: row[k] for k in row.keys()}


class Repository:
    """Audited CRUD over the vault."""

    def __init__(self, vault: Vault, *, actor: str = "system"):
        self.vault = vault
        self.actor = actor

    def _journal(self, table: str, op: str, row_id: Any, before: Any, after: Any) -> None:
        if table not in _JOURNALED:
            return
        self.vault.conn.execute(
            "INSERT INTO audit_log(ts, table_name, op, row_id, before_json, after_json, actor) "
            "VALUES(?,?,?,?,?,?,?)",
            (
                now_iso(),
                table,
                op,
                str(row_id) if row_id is not None else None,
                json.dumps(before, ensure_ascii=False) if before is not None else None,
                json.dumps(after, ensure_ascii=False) if after is not None else None,
                self.actor,
            ),
        )

    def _fetch(self, table: str, pk_col: str, pk: Any) -> dict | None:
        row = self.vault.conn.execute(
            f"SELECT * FROM {table} WHERE {pk_col} = ?", (pk,)
        ).fetchone()
        return _row_to_dict(row)

    # -- public API --------------------------------------------------------
    def insert(self, table: str, values: Mapping[str, Any], *, pk_col: str = "id") -> Any:
        cols = list(values.keys())
        placeholders = ", ".join("?" for _ in cols)
        self.vault.conn.execute(
            f"INSERT INTO {table} ({', '.join(cols)}) VALUES ({placeholders})",
            tuple(values[c] for c in cols),
        )
        pk = values.get(pk_col)
        after = self._fetch(table, pk_col, pk) if pk is not None else dict(values)
        self._journal(table, "insert", pk, None, after)
        self.vault.conn.commit()
        return pk

    def update(self, table: str, pk: Any, changes: Mapping[str, Any], *, pk_col: str = "id") -> None:
        before = self._fetch(table, pk_col, pk)
        assignments = ", ".join(f"{c} = ?" for c in changes)
        self.vault.conn.execute(
            f"UPDATE {table} SET {assignments} WHERE {pk_col} = ?",
            (*changes.values(), pk),
        )
        after = self._fetch(table, pk_col, pk)
        self._journal(table, "update", pk, before, after)
        self.vault.conn.commit()

    def delete(self, table: str, pk: Any, *, pk_col: str = "id") -> None:
        before = self._fetch(table, pk_col, pk)
        self.vault.conn.execute(f"DELETE FROM {table} WHERE {pk_col} = ?", (pk,))
        self._journal(table, "delete", pk, before, None)
        self.vault.conn.commit()

    # -- convenience -------------------------------------------------------
    def count(self, table: str) -> int:
        return self.vault.conn.execute(f"SELECT COUNT(*) AS n FROM {table}").fetchone()["n"]

    def audit_count(self) -> int:
        return self.vault.conn.execute(
            "SELECT COUNT(*) AS n FROM audit_log"
        ).fetchone()["n"]
