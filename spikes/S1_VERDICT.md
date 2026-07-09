# Spike S-1 Verdict — Gemma 4 E4B viability

**Date:** 2026-07-09
**Model:** `gemma4:e4b` via Ollama 0.31.1 (9.6 GB)
**Hardware:** Windows 11, 16 GB RAM laptop (Aditya's target machine)
**Probe:** `spikes/s1_e4b_probe.py`

## Result: **PASS** — proceed with Gemma 4 E4B as Aero's core model.

| Gate | Criterion | Measured | Verdict |
|---|---|---|---|
| Throughput | ≥ 8 tok/s sustained decode | **8.8 tok/s** | PASS (marginal) |
| JSON tagging | 4/4 valid structured tags | **4/4** | PASS |
| Code-switch + register | human judgement | natural Hinglish, friend register | PASS |

## Key finding: Gemma 4 E4B is a reasoning model

The raw Ollama response carries a `thinking` field. Left enabled, the model
spends the entire token budget on hidden chain-of-thought and returns **empty
`content`** (`done_reason: length`). This caused the first probe runs to report
0/4 JSON and blank chat replies despite tokens being generated.

**Decision:** Aero runs Gemma 4 E4B with **thinking OFF by default**
(`think: false`, wired into `OllamaCognition`). Rationale:
- Casual companion replies don't need visible CoT; it hurts the register.
- Chain-of-thought blows the latency budgets (PRD Section 24).
- Thinking can be re-enabled per-call for genuinely hard reasoning (e.g. the
  impulse gate in Phase 2) via `OllamaCognition(think=True)`.

## Notes / caveats for later phases

- **Throughput is marginal (~9 tok/s on CPU).** Fine for *text* chat with
  streaming (time-to-first-token is what matters, and that's good). For *voice*
  (Phase 1) this is the tight spot — a long spoken reply at 9 tok/s may lag the
  ≤1.2 s voice budget. Mitigations when we get there: keep spoken replies short
  (already Aero's style), sentence-stream into TTS, and check GPU/iGPU offload
  in Ollama. Re-measure under the voice pipeline; do not assume text numbers
  transfer.
- **Model load is ~40 s cold**, ~1 s warm. The daemon must keep the model warm
  (Ollama `keep_alive`) so first interaction of a session isn't a 40 s stall.
- **JSON quality is genuinely good** — tags are sensible and match the
  consolidation schema, including reasonable `roast_value`/`sensitivity`
  estimates. This de-risks Milestone 2's write path (R-6) considerably.
- Model naming: the tag is `gemma4:e4b` (Gemma 4, E4B edge variant). PRD's
  "Gemma 4 E4B" is correct; earlier uncertainty (pre-cutoff knowledge) resolved.

## Implications for the stack

- Ollama is the serving layer (llama.cpp underneath). Plan updated: we talk to
  Ollama's HTTP API via `OllamaCognition` instead of raw `llama-cpp-python`.
- `think` toggle and warm-keep are now hard requirements on the cognition layer.
- **Green light for Milestone 2 (memory core)** against this model.
