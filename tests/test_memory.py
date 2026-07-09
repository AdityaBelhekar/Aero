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
    """Returns a canned tag dict per event keyword."""

    model_name = "fake"

    def __init__(self, tags_by_keyword: dict[str, dict]):
        self.tags = tags_by_keyword

    def complete_json(self, messages, *, temperature=0.2, max_tokens=None):
        user = messages[-1].content.lower()
        for kw, tag in self.tags.items():
            if kw in user:
                stats = GenerationStats(1, 1, 0.01)
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
