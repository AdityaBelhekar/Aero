"""Spike S-2 — embedding quality on romanised Hindi/Marathi + code-switching.

The retrieval anchor step (AERO-RET-001) is only as good as the embedding
model's grasp of how Aditya actually writes: romanised Marathi/Hindi mixed with
English. Risk R-4 is that an off-the-shelf embedder treats "mala coffee havi" as
noise. This probe checks whether realistic code-switched queries land nearest
their correct memory.

Method: a small memory bank (English facts about Aditya) + queries phrased in
romanised/code-switched form. For each query we rank all memories by cosine and
check the intended memory is top-1 (and report its rank otherwise).

Pass bar (pragmatic for a solo dev set): >= 80% top-1. Below that, apply the
R-4 fallback (transliteration normalisation) before Milestone 2 leans on it.

Run (after `ollama pull embeddinggemma`):
    python spikes/s2_embedding_probe.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from aero.cognition.embeddings import OllamaEmbedder, cosine  # noqa: E402

# id -> canonical (English) memory text
MEMORIES = {
    "coffee": "Aditya prefers smooth medium roast coffee and finds dark roast too bitter.",
    "valorant": "Aditya plays Valorant and gets tilted when he bottom-frags.",
    "night_coding": "Aditya often codes on his AI projects late at night.",
    "assignment": "Aditya tends to start college assignments at the last minute.",
    "marathi": "Aditya speaks Marathi and Hindi mixed with English.",
    "aero_project": "Aditya is building Aero, a local AI companion that lives on his laptop.",
    "coldplay": "Aditya likes listening to music while working.",
    "instagram": "Aditya gets distracted by Instagram when he should be studying.",
}

# (query, expected memory id) — queries in Aditya's real register
QUERIES = [
    ("mala strong dark coffee nako, bitter lagto", "coffee"),
    ("bhai valorant madhe aaj bottom frag kela", "valorant"),
    ("raat ko late tak code karta rehta hu apne project pe", "night_coding"),
    ("assignment last minute la start karto nehmi", "assignment"),
    ("mi marathi hindi english sagla mix karun boltoy", "marathi"),
    ("apna local AI companion banवा राहिलो aahe", "aero_project"),
    ("kaam kartaना gaani aikto", "coldplay"),
    ("study karायचं sodun instagram scroll karto", "instagram"),
    ("coffee smooth medium roast havi", "coffee"),
    ("valorant khelताna tilt hoto", "valorant"),
]


def main() -> int:
    emb = OllamaEmbedder()
    print(f"Embed model: {emb.model_name}   Host: {emb.host}")
    if not emb.health_check():
        print("\nFAIL: embeddinggemma not available. Run: ollama pull embeddinggemma")
        return 1

    ids = list(MEMORIES.keys())
    mem_vecs = {i: v for i, v in zip(ids, emb.embed_batch([MEMORIES[i] for i in ids]))}
    print(f"dim = {emb.dim}\n")

    correct = 0
    for query, expected in QUERIES:
        qv = emb.embed(query)
        ranked = sorted(ids, key=lambda i: cosine(qv, mem_vecs[i]), reverse=True)
        top = ranked[0]
        rank = ranked.index(expected) + 1
        hit = top == expected
        correct += hit
        mark = "OK " if hit else "MISS"
        score = cosine(qv, mem_vecs[expected])
        print(f"  [{mark}] rank#{rank} sim={score:.3f}  \"{query[:42]}\"")
        if not hit:
            print(f"         got '{top}' instead of '{expected}'")

    pct = 100 * correct / len(QUERIES)
    print("\n" + "=" * 60)
    print(f"S-2 top-1 accuracy: {correct}/{len(QUERIES)} = {pct:.0f}%")
    verdict = "PASS" if pct >= 80 else "FAIL -> apply R-4 transliteration fallback"
    print(f"Verdict: {verdict}")
    return 0 if pct >= 80 else 2


if __name__ == "__main__":
    raise SystemExit(main())
