"""MemoryStore — typed, audited read/write over the vault's memory tables.

All writes go through the audited ``Repository`` so the journal and provenance
stay intact. Reads hit the connection directly. Embedding storage lives here too
(as float32 blobs); a real ANN index (sqlite-vec) can replace the linear scan in
``iter_embeddings`` later without changing callers — retrieval only asks the
store for "memories with vectors".
"""

from __future__ import annotations

import json
from typing import Iterator

from aero.cognition.embeddings import Vector, pack_vector, unpack_vector
from aero.memory.models import Edge, Memory, SocialMeta, new_id
from aero.vault.connection import Vault, now_iso
from aero.vault.repository import Repository


def _row_to_memory(row) -> Memory:
    return Memory(
        id=row["id"],
        kind=row["kind"],
        summary=row["summary"],
        body=row["body"],
        confidence=row["confidence"],
        evidence_count=row["evidence_count"],
        source_type=row["source_type"],
        importance=row["importance"],
        decay_score=row["decay_score"],
        status=row["status"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


class MemoryStore:
    def __init__(self, vault: Vault, *, actor: str = "system"):
        self.vault = vault
        self.repo = Repository(vault, actor=actor)

    # -- writes ------------------------------------------------------------
    def add_memory(self, mem: Memory) -> str:
        ts = now_iso()
        mem.created_at = mem.created_at or ts
        mem.updated_at = ts
        self.repo.insert("memories", {
            "id": mem.id,
            "kind": mem.kind,
            "summary": mem.summary,
            "body": mem.body,
            "created_at": mem.created_at,
            "updated_at": mem.updated_at,
            "confidence": mem.confidence,
            "evidence_count": mem.evidence_count,
            "source_type": mem.source_type,
            "importance": mem.importance,
            "decay_score": mem.decay_score,
            "status": mem.status,
        })
        social = mem.social or SocialMeta()
        self.repo.insert("memory_social", {
            "memory_id": mem.id,
            "roast_value": social.roast_value,
            "roast_allowed": int(social.roast_allowed),
            "sensitivity": social.sensitivity,
            "private_only": int(social.private_only),
            "emotional_weight": social.emotional_weight,
            "callback_fatigue": social.callback_fatigue,
            "successful_callbacks": social.successful_callbacks,
            "negative_reactions": social.negative_reactions,
            "last_used_at": social.last_used_at,
        }, pk_col="memory_id")
        return mem.id

    def set_embedding(self, memory_id: str, vector: Vector) -> None:
        # embeddings table has no audit value (derived data); write directly.
        self.vault.conn.execute(
            "INSERT INTO embeddings(memory_id, dim, vector) VALUES(?,?,?) "
            "ON CONFLICT(memory_id) DO UPDATE SET dim=excluded.dim, vector=excluded.vector",
            (memory_id, len(vector), pack_vector(vector)),
        )
        self.vault.conn.commit()

    def link(self, src_id: str, dst_id: str, relation: str, weight: float = 1.0) -> None:
        """Add (or strengthen) an associative edge. Undirected pairs should be
        linked both ways by the caller when symmetry is wanted."""
        existing = self.vault.conn.execute(
            "SELECT weight FROM edges WHERE src_id=? AND dst_id=? AND relation=?",
            (src_id, dst_id, relation),
        ).fetchone()
        if existing:
            # Composite-key row; the generic single-PK Repository.update doesn't
            # fit, so strengthen the edge weight directly.
            self.vault.conn.execute(
                "UPDATE edges SET weight = weight + ? WHERE src_id=? AND dst_id=? AND relation=?",
                (weight, src_id, dst_id, relation),
            )
            self.vault.conn.commit()
        else:
            self.repo.insert("edges", {
                "src_id": src_id, "dst_id": dst_id, "relation": relation,
                "weight": weight, "created_at": now_iso(),
            }, pk_col="src_id")

    def reinforce_belief(
        self,
        memory_id: str,
        *,
        confidence: float,
        reason: str,
        new_summary: str | None = None,
        increment_evidence: bool = True,
    ) -> None:
        """Revise a semantic belief, recording the prior state (AERO-EVO-003).

        Handles all three evolution paths: reinforcement (higher confidence),
        contradiction (``new_summary`` carries the corrected belief that keeps
        useful history), and staleness decay (lower confidence, no new evidence).
        The old state is always preserved in ``beliefs_history`` so provenance
        can explain both the current belief and how it got here.
        """
        before = self.vault.conn.execute(
            "SELECT confidence, evidence_count, summary FROM memories WHERE id=?",
            (memory_id,),
        ).fetchone()
        if before is None:
            return
        rev = self.vault.conn.execute(
            "SELECT COALESCE(MAX(revision_no),0)+1 AS n FROM beliefs_history WHERE belief_id=?",
            (memory_id,),
        ).fetchone()["n"]
        prior = json.dumps({
            "confidence": before["confidence"],
            "evidence_count": before["evidence_count"],
            "summary": before["summary"],
        }, ensure_ascii=False)
        self.repo.insert("beliefs_history", {
            "belief_id": memory_id,
            "revision_no": rev,
            "prior_state": prior,
            "reason": reason,
            "ts": now_iso(),
        }, pk_col="belief_id")
        changes = {
            "confidence": max(0.0, min(1.0, confidence)),
            "evidence_count": before["evidence_count"] + (1 if increment_evidence else 0),
            "updated_at": now_iso(),
        }
        if new_summary is not None:
            changes["summary"] = new_summary
        self.repo.update("memories", memory_id, changes)

    def set_status(self, memory_id: str, status: str) -> None:
        self.repo.update("memories", memory_id, {"status": status, "updated_at": now_iso()})

    def active_semantic_beliefs(self) -> list[Memory]:
        rows = self.vault.conn.execute(
            "SELECT * FROM memories WHERE kind='semantic' AND status='active'"
        ).fetchall()
        return [_row_to_memory(r) for r in rows]

    # -- reads -------------------------------------------------------------
    def get(self, memory_id: str) -> Memory | None:
        row = self.vault.conn.execute(
            "SELECT * FROM memories WHERE id=?", (memory_id,)
        ).fetchone()
        return _row_to_memory(row) if row else None

    def get_social(self, memory_id: str) -> SocialMeta | None:
        row = self.vault.conn.execute(
            "SELECT * FROM memory_social WHERE memory_id=?", (memory_id,)
        ).fetchone()
        if row is None:
            return None
        return SocialMeta(
            roast_value=row["roast_value"],
            roast_allowed=bool(row["roast_allowed"]),
            sensitivity=row["sensitivity"],
            private_only=bool(row["private_only"]),
            emotional_weight=row["emotional_weight"],
            callback_fatigue=row["callback_fatigue"],
            successful_callbacks=row["successful_callbacks"],
            negative_reactions=row["negative_reactions"],
            last_used_at=row["last_used_at"],
        )

    def iter_embeddings(self, *, kinds: tuple[str, ...] = ("episodic", "semantic", "core")
                        ) -> Iterator[tuple[str, Vector]]:
        """Yield (memory_id, vector) for active memories that have an embedding.

        Linear scan for now — correct and fine at Phase-0 scale (AERO-VLT-005).
        Swap in sqlite-vec here when scale demands (AERO-RET-003)."""
        placeholders = ",".join("?" for _ in kinds)
        rows = self.vault.conn.execute(
            f"SELECT e.memory_id, e.vector FROM embeddings e "
            f"JOIN memories m ON m.id = e.memory_id "
            f"WHERE m.status='active' AND m.kind IN ({placeholders})",
            kinds,
        ).fetchall()
        for r in rows:
            yield r["memory_id"], unpack_vector(r["vector"])

    def neighbors(self, memory_id: str) -> list[Edge]:
        rows = self.vault.conn.execute(
            "SELECT src_id, dst_id, relation, weight, created_at FROM edges WHERE src_id=?",
            (memory_id,),
        ).fetchall()
        return [
            Edge(r["src_id"], r["dst_id"], r["relation"], r["weight"], r["created_at"])
            for r in rows
        ]

    def core_memories(self) -> list[Memory]:
        # Concept nodes (summary 'concept:*') are graph scaffolding, not identity;
        # they are excluded from the identity working set.
        rows = self.vault.conn.execute(
            "SELECT * FROM memories WHERE kind='core' AND status='active' "
            "AND summary NOT LIKE 'concept:%' ORDER BY importance DESC"
        ).fetchall()
        return [_row_to_memory(r) for r in rows]

    def active_boundaries(self) -> list[dict]:
        rows = self.vault.conn.execute(
            "SELECT topic_or_memory, rule FROM boundaries"
        ).fetchall()
        return [{"topic_or_memory": r["topic_or_memory"], "rule": r["rule"]} for r in rows]
