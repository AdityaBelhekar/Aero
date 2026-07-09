"""Hybrid retrieval: anchor (vector) -> spread (graph) -> rerank -> select.

This implements AERO-RET-001. The graph *augments* the vector anchor rather than
replacing it: embeddings answer "what's semantically near this moment", the graph
answers "what associates with those", and the reranker weighs both against the
social context so what surfaces is not just relevant but *appropriate*.

Wild Recall (AERO-RET-004) is the same pipeline with the topical weight turned
down and association depth/creativity turned up — used only when a humorous or
social response is wanted, and still filtered for boundaries and fatigue.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from aero.cognition.embeddings import EmbeddingService, cosine
from aero.memory.models import Memory, Retrieved
from aero.memory.store import MemoryStore


@dataclass
class RetrievalContext:
    """What the reranker needs to know about the current moment to judge fit."""

    query_text: str
    private_ok: bool = True          # is it just Aditya, or others present?
    want_humour: bool = False        # gate asked for a social/roast response
    hot_topics: set[str] = field(default_factory=set)  # attention heat (AERO-ATT-001)
    now: datetime | None = None


@dataclass
class RetrievalConfig:
    anchor_k: int = 12
    spread_hops: int = 2
    spread_decay: float = 0.5        # activation multiplier per hop
    limit: int = 6
    # rerank weights
    w_anchor: float = 1.0
    w_activation: float = 0.6
    w_recency: float = 0.3
    w_decay: float = 0.4
    w_novelty: float = 0.2
    wild: bool = False               # Wild Recall mode


def _parse_ts(ts: str | None) -> datetime | None:
    if not ts:
        return None
    try:
        return datetime.fromisoformat(ts)
    except ValueError:
        return None


def _recency_score(created_at: str | None, now: datetime) -> float:
    dt = _parse_ts(created_at)
    if dt is None:
        return 0.0
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    age_days = max((now - dt).total_seconds() / 86400.0, 0.0)
    # Gentle decay: ~half-weight at ~30 days.
    return 1.0 / (1.0 + age_days / 30.0)


class RetrievalPipeline:
    def __init__(self, store: MemoryStore, embedder: EmbeddingService, config: RetrievalConfig | None = None):
        self.store = store
        self.embedder = embedder
        self.cfg = config or RetrievalConfig()

    def retrieve(self, ctx: RetrievalContext) -> list[Retrieved]:
        cfg = self.cfg
        now = ctx.now or datetime.now(timezone.utc)

        # 1) ANCHOR — vector similarity over embedded memories.
        qv = self.embedder.embed(ctx.query_text)
        sims: dict[str, float] = {}
        for mem_id, vec in self.store.iter_embeddings():
            sims[mem_id] = cosine(qv, vec)
        if not sims:
            return []
        anchors = sorted(sims, key=sims.get, reverse=True)[: cfg.anchor_k]

        # 2) SPREAD — activation flows from anchors across association edges.
        activation: dict[str, float] = {a: sims[a] for a in anchors}
        frontier = list(anchors)
        for _ in range(cfg.spread_hops):
            nxt: list[str] = []
            for node in frontier:
                base = activation.get(node, 0.0) * cfg.spread_decay
                if base <= 0.01:
                    continue
                for edge in self.store.neighbors(node):
                    add = base * edge.weight
                    # Wild Recall favours affective/social edges over topical ones.
                    if cfg.wild and edge.relation in {
                        "failure", "embarrassing", "roast_material", "funny", "emotion"
                    }:
                        add *= 1.8
                    prev = activation.get(edge.dst_id, 0.0)
                    if add > 0.01 and add > prev:
                        activation[edge.dst_id] = add
                        nxt.append(edge.dst_id)
            frontier = nxt
            if not frontier:
                break

        # 3) RERANK — combine signals, then apply the social-fit filter.
        boundaries = self._boundary_index()
        scored: list[Retrieved] = []
        for mem_id, act in activation.items():
            mem = self.store.get(mem_id)
            if mem is None or mem.status != "active":
                continue
            # Concept nodes conduct activation through the graph but are never
            # themselves results (they're scaffolding, not memories).
            if mem.kind == "core" and mem.summary.startswith("concept:"):
                continue
            if not self._social_ok(mem_id, mem, ctx, boundaries):
                continue
            anchor_sim = sims.get(mem_id, 0.0)
            recency = _recency_score(mem.created_at, now)
            novelty = self._novelty(mem_id, ctx.want_humour)
            topical = cfg.w_anchor * anchor_sim
            if cfg.wild:
                topical *= 0.4  # de-emphasise direct topical similarity
            score = (
                topical
                + cfg.w_activation * act
                + cfg.w_recency * recency
                + cfg.w_decay * mem.decay_score
                + cfg.w_novelty * novelty
            )
            reasons = self._reasons(mem_id, anchor_sim, act, recency, ctx)
            scored.append(Retrieved(
                memory=mem, score=score, anchor_similarity=anchor_sim,
                activation=act, reasons=reasons,
            ))

        scored.sort(key=lambda r: r.score, reverse=True)
        return scored[: cfg.limit]

    # -- social fit --------------------------------------------------------
    def _boundary_index(self) -> set[str]:
        return {b["topic_or_memory"] for b in self.store.active_boundaries()}

    def _social_ok(self, mem_id: str, mem: Memory, ctx: RetrievalContext, boundaries: set[str]) -> bool:
        # Explicit boundaries are override-proof (AERO-SAFE-003).
        if mem_id in boundaries:
            if ctx.want_humour:
                return False
        social = self.store.get_social(mem_id)
        if social is None:
            return True
        # Private memories don't surface when others may be present.
        if social.private_only and not ctx.private_ok:
            return False
        if ctx.want_humour:
            if not social.roast_allowed:
                return False
            # Don't reach for a fatigued joke (AERO-RET-005).
            if social.callback_fatigue >= 0.7:
                return False
        return True

    def _novelty(self, mem_id: str, want_humour: bool) -> float:
        social = self.store.get_social(mem_id)
        if social is None:
            return 0.5
        # Fresh (unfatigued) memories score higher, especially for humour.
        base = 1.0 - min(social.callback_fatigue, 1.0)
        return base

    def _reasons(self, mem_id, anchor_sim, act, recency, ctx) -> list[str]:
        r: list[str] = []
        if anchor_sim >= 0.5:
            r.append(f"semantically close to the moment (sim={anchor_sim:.2f})")
        if act > anchor_sim + 0.01:
            r.append("surfaced via association (Wild Recall)" if self.cfg.wild
                     else "surfaced via association")
        if recency >= 0.6:
            r.append("recent")
        return r or ["weak association"]
