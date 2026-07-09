"""Consolidation — turn raw events into structured, embedded, linked memories.

This is the memory *write path* (AERO-WRT-001, AERO-CON-001). It runs on demand
here; the daemon will call it during idle periods (Milestone 2e / plan). Steps
per unconsolidated event:

  1. LLM tags the event (thinking off) using the versioned tagging prompt.
  2. A Memory is created with conservative social defaults (AERO-WRT-003).
  3. The memory summary is embedded (retrieval anchor data).
  4. Association edges are created from the tag's topics/emotion/associations,
     wired to lightweight concept nodes so future events on the same theme
     connect (this is what later enables Wild Recall).
  5. The raw event is marked consolidated with a rolling expiry (AERO-CON-010).

It is deliberately conservative: a single event becomes at most one memory, and
belief-merging / contradiction handling is layered on next. Correctness first.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from aero.cognition.embeddings import EmbeddingService
from aero.cognition.service import CognitionService
from aero.memory.models import Memory, SocialMeta
from aero.memory.store import MemoryStore
from aero.prompts.tagging import tagging_messages
from aero.vault.connection import now_iso

# How long raw events linger after consolidation before the sweep may drop them
# (AERO-CON-010). High-importance events get no expiry (kept indefinitely).
RAW_RETENTION_DAYS = 30
IMPORTANCE_KEEP_FOREVER = 0.75


@dataclass
class ConsolidationResult:
    processed: int
    memories_created: int
    edges_created: int
    skipped: int


def _clamp01(x, default=0.0) -> float:
    try:
        return max(0.0, min(1.0, float(x)))
    except (TypeError, ValueError):
        return default


class Consolidator:
    def __init__(self, store: MemoryStore, llm: CognitionService, embedder: EmbeddingService):
        self.store = store
        self.llm = llm
        self.embedder = embedder

    def run(self, *, limit: int = 50) -> ConsolidationResult:
        rows = self.store.vault.conn.execute(
            "SELECT id, ts, channel, payload FROM raw_events "
            "WHERE consolidated_into IS NULL ORDER BY ts LIMIT ?",
            (limit,),
        ).fetchall()

        processed = created = edges = skipped = 0
        for row in rows:
            processed += 1
            tag = self._tag(row["payload"])
            if tag is None:
                skipped += 1
                continue
            mem_id, n_edges = self._store_from_tag(tag, source_event_id=row["id"])
            created += 1
            edges += n_edges
        return ConsolidationResult(processed, created, edges, skipped)

    # -- steps -------------------------------------------------------------
    def _tag(self, event_text: str) -> dict | None:
        parsed, _ = self.llm.complete_json(tagging_messages(event_text), max_tokens=400)
        if not isinstance(parsed, dict) or "summary" not in parsed:
            return None
        return parsed

    def _store_from_tag(self, tag: dict, *, source_event_id: str) -> tuple[str, int]:
        kind = tag.get("kind")
        if kind not in ("episodic", "semantic"):
            kind = "episodic"

        social = SocialMeta(
            roast_value=_clamp01(tag.get("roast_value"), 0.0),
            # Trust the model's roast_allowed only when it's explicitly True;
            # anything else stays False (AERO-WRT-003).
            roast_allowed=bool(tag.get("roast_allowed") is True),
            sensitivity=_clamp01(tag.get("sensitivity"), 0.5),
            private_only=True,
            emotional_weight=_clamp01(tag.get("emotional_weight"), 0.0),
        )
        mem = Memory(
            summary=str(tag["summary"]),
            kind=kind,  # type: ignore[arg-type]
            source_type="repeated_observation" if kind == "semantic" else "inference",
            importance=_clamp01(tag.get("importance"), 0.5),
            social=social,
        )
        self.store.add_memory(mem)

        # 3) embed the summary for retrieval anchoring
        try:
            vec = self.embedder.embed(mem.summary)
            self.store.set_embedding(mem.id, vec)
        except Exception:
            pass  # embedding is recoverable later; don't lose the memory

        # 4) association edges to concept nodes
        n_edges = self._wire_associations(mem, tag)

        # 5) mark the raw event consolidated with rolling expiry
        expires = None if mem.importance >= IMPORTANCE_KEEP_FOREVER else (
            (datetime.now(timezone.utc) + timedelta(days=RAW_RETENTION_DAYS)).isoformat()
        )
        self.store.vault.conn.execute(
            "UPDATE raw_events SET consolidated_into=?, expires_at=? WHERE id=?",
            (mem.id, expires, source_event_id),
        )
        self.store.vault.conn.commit()
        return mem.id, n_edges

    def _wire_associations(self, mem: Memory, tag: dict) -> int:
        """Link this memory to concept nodes for topics/people/emotion/associations.

        Concept nodes are themselves lightweight ``core``-kind memories keyed by a
        stable summary, so repeated themes converge on the same node and the graph
        grows dense where the user's life is dense. Retrieval spreads across these.
        """
        labels: list[tuple[str, str]] = []
        for t in tag.get("topics", []) or []:
            labels.append(("topic", str(t)))
        for p in tag.get("people", []) or []:
            labels.append(("person", str(p)))
        emo = tag.get("emotion")
        if emo and str(emo).lower() != "neutral":
            labels.append(("emotion", str(emo)))
        if tag.get("is_failure"):
            labels.append(("failure", "failure"))
        for a in tag.get("associations", []) or []:
            rel = "roast_material" if "roast" in str(a).lower() else "association"
            labels.append((rel, str(a)))

        n = 0
        for relation, label in labels:
            concept_id = self._concept_node(label)
            self.store.link(mem.id, concept_id, relation, weight=1.0)
            self.store.link(concept_id, mem.id, relation, weight=1.0)  # symmetric
            n += 1
        return n

    def _concept_node(self, label: str) -> str:
        """Get-or-create a concept node by normalized label."""
        norm = label.strip().lower()
        key = f"concept:{norm}"
        row = self.store.vault.conn.execute(
            "SELECT id FROM memories WHERE kind='core' AND summary=?", (key,)
        ).fetchone()
        if row:
            return row["id"]
        node = Memory(summary=key, kind="core", importance=0.3, source_type="inference")
        self.store.add_memory(node)
        return node.id
