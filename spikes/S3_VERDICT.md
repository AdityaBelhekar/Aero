# Spike S-3 Verdict — code-switched STT (PARTIAL / infrastructure)

**Date:** 2026-07-10
**Backend:** faster-whisper 1.2.1 (CTranslate2), int8, CPU
**Hardware:** Windows 11, 16 GB RAM laptop, CPU-only (torch installed is +cpu)
**Probe:** `spikes/s3_stt_probe.py`

## Status: **infrastructure complete, pipeline validated; accuracy verdict BLOCKED on real recordings.**

The whole STT chain works end-to-end and the speed/accuracy tradeoff on this CPU
is characterised. What's missing is the thing only Aditya can provide: his own
code-switched speech. Synthetic English (Windows SAPI) was used to validate the
pipeline, not to judge multilingual accuracy.

## Measured (clean English, SAPI audio — pipeline smoke test)

| Model | mean WER | mean RTF (warm) | Fit for live voice? |
|---|---|---|---|
| `small` (int8) | 0.00 | ~1.7 (2.0 incl. load) | **No** — slower than realtime on CPU |
| `base` (int8)  | 0.08 | ~0.5 | **Yes** — comfortably faster than realtime |

RTF = compute ÷ audio. Must be < 1.0 for live voice (PRD Section 24). Short clips
inflate RTF (fixed VAD/beam overhead); real utterances amortise it. `beam_size=5`
was used — greedy (`beam_size=1`) would be faster still.

## The real finding (risk R-3 confirmed)

On a CPU there's genuine tension between **multilingual accuracy** (wants a bigger
model — `small`/`medium`) and **realtime latency** (wants a smaller model —
`base`/`tiny`). Clean English hides this because even `base` nails it; Marathi/
Hindi code-switch is where `base` will likely weaken and force `small`, which is
too slow on CPU. Paths forward, in order:

1. **Get Aditya's recordings** (spikes/s3_testset/README.md, ~15 min) and run
   both `base` and `small`. This decides everything below.
2. If `small` is needed for accuracy but too slow: try **greedy decoding**,
   **distil-whisper** (2–4× faster, multilingual variants), or **GPU offload**
   (needs a CUDA GPU + `compute_type=float16` — this box is CPU-only today).
3. If Whisper-family accuracy on romanised Marathi is poor: **AI4Bharat
   IndicWhisper / IndicConformer** (the R-3 fallback named in the plan).
4. If none hit both bars on this hardware: **push-to-talk only** for Milestone 3
   (transcribe after the user stops — RTF < 1.0 with `base` is fine for that),
   defer open-mic until hardware/models improve.

## Delivered infrastructure

- `aero/perception/stt.py` — `STTService` interface + `FasterWhisperBackend`
  (model-swappable like cognition; IndicWhisper can drop in).
- `aero/eval/wer.py` — WER + CER (CER reported because romanised spelling makes
  WER harsh); Devanagari-aware normalisation.
- `spikes/s3_stt_probe.py` — manifest-driven benchmark: WER, CER, RTF, verdict.
- `spikes/s3_testset/` — recording protocol + 10 code-switched reference
  sentences + manifest, ready for Aditya's WAVs.

## Recommendation

Green-light **Milestone 3 planning** with **push-to-talk first** (base model,
RTF < 1.0 already met). Gate open-mic / model choice on Aditya's recordings.
Don't assume text-chat throughput numbers transfer to voice — measure STT+LLM+TTS
together under the pipeline.
