# Spike S-2 Verdict — embedding quality on romanised Hindi/Marathi

**Date:** 2026-07-09
**Model:** `embeddinggemma` via Ollama (768-dim)
**Probe:** `spikes/s2_embedding_probe.py`

## Result: **PASS** (90% top-1) — use embeddinggemma for the retrieval anchor.

10 code-switched / romanised queries against an 8-item memory bank; 9 landed
their intended memory at rank #1.

| Metric | Value |
|---|---|
| Top-1 accuracy | 9/10 = **90%** (bar: 80%) |
| Dimension | 768 |
| Typical correct sim | 0.53–0.68 |

### The one miss
"kaam kartaना gaani aikto" (listens to music while working) matched `instagram`
over `coldplay`. The `coldplay` memory text ("likes listening to music while
working") is itself weak/generic, and the query mixed Devanagari fragments — a
borderline case, not a systemic failure.

## Takeaways for Milestone 2
- Risk R-4 (embeddings choking on romanised Marathi/Hindi) is **retired** for
  Phase-0 scale. No transliteration-normalisation fallback needed yet.
- Absolute cosine values are modest (~0.5–0.68 for correct hits), so retrieval
  should rank by *relative* similarity, not an absolute threshold — which the
  pipeline already does.
- Watch for weak/generic memory summaries (like the coldplay one) diluting
  retrieval; the consolidation tagger should produce specific summaries.
- embeddinggemma must be kept warm alongside gemma4:e4b (two models resident).
  Confirm this fits the RAM budget (AERO-BGT-001) once both run under the daemon.
