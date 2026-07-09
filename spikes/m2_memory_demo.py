"""Milestone 2 end-to-end demo: raw events -> consolidation -> retrieval.

Drives the full memory write+read loop against the real models (gemma4:e4b for
tagging, embeddinggemma for anchoring) on a throwaway vault. Not a unit test —
an integration smoke you can eyeball to confirm the heart of Phase 0 works:

  * events get tagged into episodic/semantic memories with conservative social
    metadata,
  * memories are embedded and linked into the association graph,
  * a code-switched query retrieves the right memories *with provenance*,
  * a Wild-Recall query surfaces associatively-linked material.

Run: python spikes/m2_memory_demo.py
"""

from __future__ import annotations

import sys
import tempfile
import uuid
import warnings
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from aero.cognition.embeddings import OllamaEmbedder  # noqa: E402
from aero.cognition.ollama_backend import OllamaCognition  # noqa: E402
from aero.memory.consolidation import Consolidator  # noqa: E402
from aero.memory.retrieval import RetrievalContext, RetrievalPipeline  # noqa: E402
from aero.memory.store import MemoryStore  # noqa: E402
from aero.vault.connection import now_iso, open_vault  # noqa: E402

EVENTS = [
    "Aditya bottom-fragged in Valorant tonight and blamed his mouse again, laughing about it.",
    "Aditya said dark roast coffee is too bitter, he prefers a smoother medium roast now.",
    "Aditya started a new AI side-project at 2am, super excited, then abandoned it by morning.",
    "Aditya kept hitting the same build error for an hour and got visibly frustrated.",
    "Aditya opened Instagram during a focus session when an assignment was due soon.",
    "Aditya mentioned his friend Rohan is coming over this weekend to game.",
]


def main() -> int:
    llm = OllamaCognition()
    emb = OllamaEmbedder()
    if not llm.health_check():
        print("FAIL: gemma4:e4b not available."); return 1
    if not emb.health_check():
        print("FAIL: embeddinggemma not available."); return 1

    tmp = Path(tempfile.mkdtemp()) / "demo.vault"
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        vault = open_vault(tmp)
    store = MemoryStore(vault, actor="user")

    # 1) Seed raw events (as if logged from chat/observation).
    for ev in EVENTS:
        vault.conn.execute(
            "INSERT INTO raw_events(id, ts, channel, payload) VALUES(?,?,?,?)",
            (uuid.uuid4().hex, now_iso(), "chat", ev),
        )
    vault.conn.commit()
    print(f"seeded {len(EVENTS)} raw events\n")

    # 2) Consolidate (LLM tagging + embed + graph).
    print("consolidating (LLM tagging, thinking off)...")
    result = Consolidator(store, llm, emb).run()
    print(f"  processed={result.processed} memories={result.memories_created} "
          f"edges={result.edges_created} skipped={result.skipped}\n")

    mems = vault.conn.execute(
        "SELECT summary, kind, importance FROM memories "
        "WHERE summary NOT LIKE 'concept:%' ORDER BY kind"
    ).fetchall()
    print("stored memories:")
    for m in mems:
        print(f"  [{m['kind']:<8} imp={m['importance']:.2f}] {m['summary']}")

    pipe = RetrievalPipeline(store, emb)

    # 3) Normal retrieval with a code-switched query.
    print("\n--- retrieval: \"bhai coffee kasa pahije mala?\" ---")
    for r in pipe.retrieve(RetrievalContext("bhai coffee kasa pahije mala, dark ki medium?")):
        print(f"  ({r.score:.2f}) {r.memory.summary}")
        print(f"        why: {', '.join(r.reasons)}")

    # 4) Wild Recall: humour-seeking around a failure moment.
    print("\n--- Wild Recall: bottom-fragged again (want_humour) ---")
    pipe.cfg.wild = True
    ctx = RetrievalContext("aditya just bottom-fragged in valorant again",
                           want_humour=True)
    hits = pipe.retrieve(ctx)
    if not hits:
        print("  (nothing cleared the social-fit filter — correct if nothing is roast_allowed yet)")
    for r in hits:
        print(f"  ({r.score:.2f}) {r.memory.summary}")
        print(f"        why: {', '.join(r.reasons)}")

    vault.close()
    print("\nOK: full memory loop ran end-to-end.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
