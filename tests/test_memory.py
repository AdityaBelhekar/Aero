"""Memory-layer tests — hermetic (fake LLM + fake embedder, no model needed).

These lock in the store/consolidation/retrieval behaviour independent of the
live models, so CI stays fast and deterministic. The live end-to-end path is
exercised separately by spikes/m2_memory_demo.py.
"""

from __future__ import annotations

import warnings
from pathlib import Path

import pytest

from aero.cognition.embeddings import EmbeddingService
from aero.cognition.service import ChatMessage, CompletionResult, GenerationStats
from aero.memory.consolidation import Consolidator
from aero.memory.models import Memory, SocialMeta
from aero.memory.retrieval import RetrievalContext, RetrievalPipeline
from aero.memory.store import MemoryStore
from aero.vault.connection import now_iso, open_vault


# -- fakes -----------------------------------------------------------------
class FakeEmbedder(EmbeddingService):
    """Deterministic bag-of-words vectors over a tiny fixed vocabulary, so
    'coffee' texts are near each other without any model."""

    VOCAB = ["coffee", "roast", "valorant", "mouse", "code", "error",
             "instagram", "rohan", "night", "project"]

    def __init__(self):
        self.model_name = "fake"
        self.dim = len(self.VOCAB)

    def embed(self, text: str):
        t = text.lower()
        return [float(t.count(w)) for w in self.VOCAB]

    def embed_batch(self, texts):
        return [self.embed(t) for t in texts]

    def health_check(self):
        return True


class FakeLLM:
    """Returns a canned tag dict per event keyword, and (optionally) a canned
    reconciliation verdict for belief-reconcile calls."""

    model_name = "fake"

    def __init__(self, tags_by_keyword: dict[str, dict], reconcile: dict | None = None):
        self.tags = tags_by_keyword
        self.reconcile = reconcile

    def complete_json(self, messages, *, temperature=0.2, max_tokens=None):
        stats = GenerationStats(1, 1, 0.01)
        system = messages[0].content.lower()
        # Reconcile calls carry the reconciliation system prompt.
        if "belief" in system and "existing" in messages[-1].content.lower():
            return self.reconcile, CompletionResult("{}", stats)
        user = messages[-1].content.lower()
        for kw, tag in self.tags.items():
            if kw in user:
                return tag, CompletionResult("{}", stats)
        return None, CompletionResult("", GenerationStats(0, 0, 0.01))

    def chat(self, messages, *, temperature=0.7, max_tokens=None):
        return CompletionResult("ok", GenerationStats(1, 1, 0.01))

    def health_check(self):
        return True


@pytest.fixture()
def store(tmp_path: Path):
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        v = open_vault(tmp_path / "m.vault")
    yield MemoryStore(v, actor="user")
    v.close()


# -- store -----------------------------------------------------------------
def test_add_memory_defaults_conservative(store):
    mid = store.add_memory(Memory(summary="test", kind="episodic"))
    social = store.get_social(mid)
    assert social.roast_allowed is False
    assert social.private_only is True


def test_reinforce_belief_records_history(store):
    mid = store.add_memory(Memory(summary="likes tea", kind="semantic", confidence=0.5))
    store.reinforce_belief(mid, confidence=0.8, reason="said it again")
    mem = store.get(mid)
    assert mem.confidence == pytest.approx(0.8)
    assert mem.evidence_count == 2
    hist = store.vault.conn.execute(
        "SELECT reason FROM beliefs_history WHERE belief_id=?", (mid,)
    ).fetchall()
    assert len(hist) == 1


# -- consolidation ---------------------------------------------------------
def test_consolidation_creates_memory_and_edges(store):
    store.vault.conn.execute(
        "INSERT INTO raw_events(id, ts, channel, payload) VALUES('e1',?,?,?)",
        (now_iso(), "chat", "Aditya bottom-fragged in valorant and blamed his mouse"),
    )
    store.vault.conn.commit()
    llm = FakeLLM({"valorant": {
        "summary": "Aditya bottom-fragged in Valorant and blamed his mouse.",
        "kind": "episodic", "topics": ["valorant"], "people": [],
        "emotion": "amused", "is_failure": True, "importance": 0.3,
        "emotional_weight": 0.2, "sensitivity": 0.3,
        "roast_value": 0.7, "roast_allowed": True,
        "associations": ["roast_material", "excuses"],
    }})
    res = Consolidator(store, llm, FakeEmbedder()).run()
    assert res.memories_created == 1
    assert res.edges_created > 0
    # raw event marked consolidated
    row = store.vault.conn.execute(
        "SELECT consolidated_into FROM raw_events WHERE id='e1'"
    ).fetchone()
    assert row["consolidated_into"] is not None


def _seed_belief(store, emb, summary, confidence=0.6, evidence=1):
    from aero.memory.models import Memory
    mem = Memory(summary=summary, kind="semantic", confidence=confidence,
                 evidence_count=evidence, source_type="repeated_observation")
    store.add_memory(mem)
    store.set_embedding(mem.id, emb.embed(summary))
    return mem.id


def test_consolidation_contradiction_revises_belief(store):
    emb = FakeEmbedder()
    bid = _seed_belief(store, emb, "Aditya likes dark roast coffee", confidence=0.7)
    store.vault.conn.execute(
        "INSERT INTO raw_events(id, ts, channel, payload) VALUES('c1',?,?,?)",
        (now_iso(), "chat", "Aditya says medium roast coffee is better now"),
    )
    store.vault.conn.commit()
    llm = FakeLLM(
        {"coffee": {
            "summary": "Aditya prefers medium roast coffee now", "kind": "semantic",
            "topics": ["coffee"], "people": [], "emotion": "neutral",
            "is_failure": False, "importance": 0.4, "emotional_weight": 0.1,
            "sensitivity": 0.2, "roast_value": 0.2, "roast_allowed": False,
            "associations": [],
        }},
        reconcile={
            "relation": "contradicts",
            "statement": "Aditya now prefers medium roast coffee, previously dark roast",
            "confidence": 0.75, "reason": "stated a change",
        },
    )
    res = Consolidator(store, llm, emb).run(sweep=False)
    assert res.beliefs_revised == 1
    assert res.memories_created == 0  # folded into existing, no duplicate
    updated = store.get(bid)
    assert "previously dark" in updated.summary
    hist = store.vault.conn.execute(
        "SELECT COUNT(*) AS n FROM beliefs_history WHERE belief_id=?", (bid,)
    ).fetchone()["n"]
    assert hist == 1


def test_consolidation_reinforcement_raises_confidence(store):
    emb = FakeEmbedder()
    bid = _seed_belief(store, emb, "Aditya codes at night on his project", confidence=0.5)
    store.vault.conn.execute(
        "INSERT INTO raw_events(id, ts, channel, payload) VALUES('r1',?,?,?)",
        (now_iso(), "chat", "Aditya was coding late at night on his project again"),
    )
    store.vault.conn.commit()
    llm = FakeLLM(
        {"night": {
            "summary": "Aditya codes at night on his project", "kind": "semantic",
            "topics": ["night", "code", "project"], "people": [], "emotion": "neutral",
            "is_failure": False, "importance": 0.4, "emotional_weight": 0.0,
            "sensitivity": 0.2, "roast_value": 0.1, "roast_allowed": False,
            "associations": [],
        }},
        reconcile={"relation": "reinforces",
                   "statement": "Aditya codes at night on his project",
                   "confidence": 0.8, "reason": "seen again"},
    )
    res = Consolidator(store, llm, emb).run(sweep=False)
    assert res.beliefs_reinforced == 1
    assert store.get(bid).confidence == pytest.approx(0.8)
    assert store.get(bid).evidence_count == 2


def test_staleness_sweep_decays_and_demotes(store):
    emb = FakeEmbedder()
    bid = _seed_belief(store, emb, "Aditya likes obscure trivia", confidence=0.3, evidence=1)
    # Backdate last-reinforced to 200 days ago.
    from datetime import datetime, timedelta, timezone
    old = (datetime.now(timezone.utc) - timedelta(days=200)).isoformat()
    store.vault.conn.execute("UPDATE memories SET updated_at=? WHERE id=?", (old, bid))
    store.vault.conn.commit()

    decayed, dormant = Consolidator(store, FakeLLM({}), emb).sweep_staleness()
    assert decayed == 1
    assert dormant == 1
    mem = store.get(bid)
    assert mem.confidence < 0.3      # decayed
    assert mem.status == "dormant"   # below floor


def test_staleness_sweep_spares_fresh_beliefs(store):
    emb = FakeEmbedder()
    bid = _seed_belief(store, emb, "Aditya likes coffee", confidence=0.8)
    decayed, dormant = Consolidator(store, FakeLLM({}), emb).sweep_staleness()
    assert decayed == 0
    assert store.get(bid).confidence == pytest.approx(0.8)


def test_consolidation_ignores_llm_roast_unless_true(store):
    store.vault.conn.execute(
        "INSERT INTO raw_events(id, ts, channel, payload) VALUES('e2',?,?,?)",
        (now_iso(), "chat", "Aditya failed an exam and was upset"),
    )
    store.vault.conn.commit()
    llm = FakeLLM({"exam": {
        "summary": "Aditya failed an exam and was upset.", "kind": "episodic",
        "topics": ["exam"], "people": [], "emotion": "sad", "is_failure": True,
        "importance": 0.6, "emotional_weight": 0.7, "sensitivity": 0.8,
        "roast_value": 0.4, "roast_allowed": "yes",  # not the boolean True
        "associations": [],
    }})
    Consolidator(store, llm, FakeEmbedder()).run()
    mid = store.vault.conn.execute(
        "SELECT id FROM memories WHERE summary LIKE 'Aditya failed%'"
    ).fetchone()["id"]
    assert store.get_social(mid).roast_allowed is False  # AERO-WRT-003


# -- retrieval -------------------------------------------------------------
def _seed(store, emb, summary, **social):
    mem = Memory(summary=summary, kind="episodic", social=SocialMeta(**social))
    store.add_memory(mem)
    store.set_embedding(mem.id, emb.embed(summary))
    return mem.id


def test_retrieval_ranks_relevant_first(store):
    emb = FakeEmbedder()
    _seed(store, emb, "Aditya likes medium roast coffee")
    _seed(store, emb, "Aditya plays valorant with his mouse")
    pipe = RetrievalPipeline(store, emb)
    hits = pipe.retrieve(RetrievalContext("what coffee roast does he like"))
    assert hits
    assert "coffee" in hits[0].memory.summary.lower()


def test_humour_filter_blocks_non_roastable(store):
    emb = FakeEmbedder()
    _seed(store, emb, "Aditya valorant mouse fail", roast_allowed=False)
    pipe = RetrievalPipeline(store, emb)
    hits = pipe.retrieve(RetrievalContext("valorant", want_humour=True))
    assert hits == []  # nothing is roast_allowed


def test_humour_filter_allows_roastable(store):
    emb = FakeEmbedder()
    _seed(store, emb, "Aditya valorant mouse fail", roast_allowed=True, private_only=True)
    pipe = RetrievalPipeline(store, emb)
    hits = pipe.retrieve(RetrievalContext("valorant", want_humour=True, private_ok=True))
    assert len(hits) == 1


def test_private_memory_hidden_when_others_present(store):
    emb = FakeEmbedder()
    _seed(store, emb, "Aditya coffee secret", private_only=True)
    pipe = RetrievalPipeline(store, emb)
    hits = pipe.retrieve(RetrievalContext("coffee", private_ok=False))
    assert hits == []
