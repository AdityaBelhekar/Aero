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

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from aero.cognition.embeddings import EmbeddingService, cosine
from aero.cognition.service import CognitionService
from aero.memory.models import Memory, SocialMeta
from aero.memory.store import MemoryStore
from aero.prompts.reconcile import reconcile_messages
from aero.prompts.tagging import tagging_messages
from aero.vault.connection import now_iso

# How long raw events linger after consolidation before the sweep may drop them
# (AERO-CON-010). High-importance events get no expiry (kept indefinitely).
RAW_RETENTION_DAYS = 30
IMPORTANCE_KEEP_FOREVER = 0.75

# A new semantic belief this close (cosine) to an existing one is treated as
# about the same thing, and reconciled rather than duplicated. Embeddings run
# modest (S-2), so this is deliberately not too high.
SEMANTIC_MATCH_THRESHOLD = 0.60


@dataclass
class ConsolidationResult:
    processed: int
    memories_created: int
    edges_created: int
    skipped: int
    beliefs_reinforced: int = 0
    beliefs_revised: int = 0     # contradiction -> corrected belief
    beliefs_decayed: int = 0     # staleness sweep lowered confidence
    beliefs_dormant: int = 0     # staleness sweep demoted below the floor


def _clamp01(x, default=0.0) -> float:
    try:
        return max(0.0, min(1.0, float(x)))
    except (TypeError, ValueError):
        return default


def _parse_ts(ts: str | None) -> datetime | None:
    if not ts:
        return None
    try:
        dt = datetime.fromisoformat(ts)
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


class Consolidator:
    def __init__(self, store: MemoryStore, llm: CognitionService, embedder: EmbeddingService):
        self.store = store
        self.llm = llm
        self.embedder = embedder

    def run(self, *, limit: int = 50, sweep: bool = True) -> ConsolidationResult:
        rows = self.store.vault.conn.execute(
            "SELECT id, ts, channel, payload FROM raw_events "
            "WHERE consolidated_into IS NULL ORDER BY ts LIMIT ?",
            (limit,),
        ).fetchall()

        processed = created = edges = skipped = reinforced = revised = 0
        for row in rows:
            processed += 1
            tag = self._tag(row["payload"])
            if tag is None:
                skipped += 1
                continue
            _id, n_edges, action = self._store_from_tag(tag, source_event_id=row["id"])
            edges += n_edges
            if action == "created":
                created += 1
            elif action == "reinforced":
                reinforced += 1
            elif action == "revised":
                revised += 1

        decayed = dormant = 0
        if sweep:
            decayed, dormant = self.sweep_staleness()

        return ConsolidationResult(
            processed, created, edges, skipped,
            beliefs_reinforced=reinforced, beliefs_revised=revised,
            beliefs_decayed=decayed, beliefs_dormant=dormant,
        )

    # -- steps -------------------------------------------------------------
    def _tag(self, event_text: str) -> dict | None:
        parsed, _ = self.llm.complete_json(tagging_messages(event_text), max_tokens=400)
        if not isinstance(parsed, dict) or "summary" not in parsed:
            return None
        return parsed

    def _store_from_tag(self, tag: dict, *, source_event_id: str) -> tuple[str, int, str]:
        kind = tag.get("kind")
        if kind not in ("episodic", "semantic"):
            kind = "episodic"

        summary = str(tag["summary"])
        vec = None
        try:
            vec = self.embedder.embed(summary)
        except Exception:
            pass

        # Semantic beliefs reconcile against what Aero already believes, so the
        # understanding evolves instead of accumulating duplicates/contradictions.
        if kind == "semantic" and vec is not None:
            match = self._nearest_semantic(vec)
            if match is not None:
                existing_id, sim = match
                folded = self._reconcile_into(existing_id, summary, tag, source_event_id)
                if folded is not None:
                    return folded  # (id, edges, 'reinforced'|'revised')

        # Otherwise store a fresh memory (episodic, or a genuinely new belief).
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
            summary=summary,
            kind=kind,  # type: ignore[arg-type]
            source_type="repeated_observation" if kind == "semantic" else "inference",
            importance=_clamp01(tag.get("importance"), 0.5),
            social=social,
        )
        self.store.add_memory(mem)
        if vec is not None:
            self.store.set_embedding(mem.id, vec)
        n_edges = self._wire_associations(mem, tag)
        self._mark_consolidated(source_event_id, mem.id, mem.importance)
        return mem.id, n_edges, "created"

    def _nearest_semantic(self, vec) -> tuple[str, float] | None:
        best_id, best_sim = None, -1.0
        for mem_id, mvec in self.store.iter_embeddings(kinds=("semantic",)):
            s = cosine(vec, mvec)
            if s > best_sim:
                best_id, best_sim = mem_id, s
        if best_id is not None and best_sim >= SEMANTIC_MATCH_THRESHOLD:
            return best_id, best_sim
        return None

    def _reconcile_into(self, existing_id: str, new_summary: str, tag: dict,
                        source_event_id: str) -> tuple[str, int, str] | None:
        """Reconcile a new observation with an existing belief. Returns the fold
        result, or None to fall through and create a fresh belief (unrelated)."""
        existing = self.store.get(existing_id)
        if existing is None:
            return None
        parsed, _ = self.llm.complete_json(
            reconcile_messages(existing.summary, existing.confidence, new_summary),
            max_tokens=250,
        )
        if not isinstance(parsed, dict):
            return None
        relation = str(parsed.get("relation", "")).lower()
        if relation not in ("reinforces", "contradicts"):
            return None  # unrelated (or garbage) -> caller creates a new belief

        statement = str(parsed.get("statement") or existing.summary)
        confidence = _clamp01(parsed.get("confidence"), existing.confidence)
        reason = str(parsed.get("reason") or relation)

        self.store.reinforce_belief(
            existing_id,
            confidence=confidence,
            reason=f"{relation}: {reason}",
            new_summary=statement if statement != existing.summary else None,
        )
        # Keep the anchor vector aligned with the (possibly corrected) statement.
        try:
            self.store.set_embedding(existing_id, self.embedder.embed(statement))
        except Exception:
            pass
        # New evidence's associations attach to the surviving belief.
        surviving = self.store.get(existing_id)
        n_edges = self._wire_associations(surviving, tag) if surviving else 0
        self._mark_consolidated(source_event_id, existing_id, existing.importance)
        return existing_id, n_edges, ("reinforced" if relation == "reinforces" else "revised")

    def _mark_consolidated(self, source_event_id: str, memory_id: str, importance: float) -> None:
        expires = None if importance >= IMPORTANCE_KEEP_FOREVER else (
            (datetime.now(timezone.utc) + timedelta(days=RAW_RETENTION_DAYS)).isoformat()
        )
        self.store.vault.conn.execute(
            "UPDATE raw_events SET consolidated_into=?, expires_at=? WHERE id=?",
            (memory_id, expires, source_event_id),
        )
        self.store.vault.conn.commit()

    def sweep_staleness(
        self,
        *,
        now: datetime | None = None,
        base_horizon_days: float = 90.0,
        floor: float = 0.25,
        decay: float = 0.6,
    ) -> tuple[int, int]:
        """Decay confidence of beliefs not reinforced within their horizon, and
        demote those falling below the floor to dormant (AERO-EVO-002, AERO-DEC-001).

        The horizon scales with evidence: a belief backed by many observations
        survives longer without reinforcement than a one-off inference.
        """
        now = now or datetime.now(timezone.utc)
        decayed = dormant = 0
        for belief in self.store.active_semantic_beliefs():
            last = _parse_ts(belief.updated_at)
            if last is None:
                continue
            age_days = (now - last).total_seconds() / 86400.0
            horizon = min(base_horizon_days * (0.5 + 0.1 * belief.evidence_count),
                          base_horizon_days * 3)
            if age_days <= horizon:
                continue
            new_conf = belief.confidence * decay
            self.store.reinforce_belief(
                belief.id,
                confidence=new_conf,
                reason=f"staleness decay after {age_days:.0f}d unreinforced",
                increment_evidence=False,
            )
            decayed += 1
            if new_conf < floor:
                self.store.set_status(belief.id, "dormant")
                dormant += 1
        return decayed, dormant

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
