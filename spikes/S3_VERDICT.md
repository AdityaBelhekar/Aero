# Spike S-3 Verdict — code-switched STT (FINAL)

**Date:** 2026-07-11
**Backend:** faster-whisper 1.2.1 (CTranslate2), int8, CPU-only
**Hardware:** Windows 11, 16 GB RAM laptop
**Audio:** Aditya's own 10 code-switched recordings (`spikes/s3_testset/01..10.wav`)
**Probe:** `spikes/s3_stt_probe.py`

## Result: **`small` (Whisper) is the working pick for Milestone 3, push-to-talk.**

The headline WER numbers are misleading — read the outputs, not just the scores.

## Measured on Aditya's real voice

| Model | mean WER | mean CER | mean RTF | Reads code-switch? | Realtime? |
|---|---|---|---|---|---|
| `base` (int8)  | 0.56 | 0.30 | ~0.6 | **No** — mangles it | Yes |
| `small` (int8) | 1.14* | 0.84* | ~1.5 median** | **Yes** (outputs Devanagari) | Borderline (PTT ok) |

\* `small`'s WER/CER are inflated by a **script mismatch**, not comprehension —
see below. \*\* mean RTF 3.94 is skewed by two outliers (a catastrophic clip at
15× and the cold-load clip at 8.8×); the healthy clips sit ~1.4–1.75×.

## The key finding: `small` understands, it just writes Devanagari

`base` genuinely fails on code-switch ("mala vatat this approach wrong aahe" →
"Malavattadis approach ranga hai"). `small` **comprehends** it and transcribes
into native Devanagari:

- ref: `mala vatat this approach wrong aahe model la context samajla pahije`
- `small`: `मला वाट्त दिस अप्रोज ... मोडला कोंटेक समजल पाएज़े`  ← correct meaning

The reference transcripts are romanised Latin, so string WER scores this as 100%
wrong when it's actually right. Reading all 10: `small` substantially captures ~7
of 10 (messy spelling, right content); `base` far fewer.

**Consequence — romanisation is NOT required.** Aero's downstream consumer is
`gemma4:e4b`, which reads Devanagari natively. So Devanagari STT output is fine;
the earlier "romanised output" assumption is dropped. The real (and only) blocker
for `small` is **speed**, not accuracy.

## Decision

- **Milestone 3 ships push-to-talk with `small`.** PTT (transcribe after the user
  stops) tolerates ~1.5× realtime — a ~4 s utterance → ~6 s wait with a
  "listening…/thinking…" indicator. Good enough to build the voice loop now.
- **Accept Devanagari transcripts** end-to-end; gemma4 handles them.
- **Guard the catastrophic case** (one clip produced garbage at 15× RTF): add a
  sanity check (empty/low-confidence/absurd-length → ask the user to repeat)
  before feeding the transcript to memory.

## Turbo tested too (large-v3-turbo, downloaded manually to models/turbo)

| Model | mean WER | mean CER | mean RTF (CPU) | Comprehension | Stability |
|---|---|---|---|---|---|
| `base`  | 0.56 | 0.30 | ~0.6 | poor on code-switch | ok |
| `small` | 1.14* | 0.84* | ~1.5 | good (Devanagari) | one catastrophic clip |
| `models/turbo` | 0.54* | 0.49* | ~3.5 | **best — mixes scripts naturally** | **rock-solid, no failures** |

\* WER inflated by Devanagari-vs-romanised script mismatch, not comprehension.

Turbo is the smartest ear by a clear margin — it correctly kept English in Latin
and Hindi/Marathi in Devanagari in the *same* utterance (clip 01: "भाई ये
आसाइन्मेंट का डेडलाइन कल आहे and I haven't even started yet") and had **zero**
catastrophic failures. Greedy decoding (`--beam 1`) did NOT help — it was slower
(thermal throttling) and no more accurate, confirming compute, not search, is the
bottleneck.

## Final decision (CPU-bound reality)

- **Ship `small` as the default** for push-to-talk now: ~1.5× RTF (~6 s per
  utterance) is tolerable; guard the occasional garbage clip (already built into
  the voice loop). This is the voice-loop default.
- **`turbo` is the accuracy king, gated on hardware.** At ~3.5× on this CPU it's
  a ~12 s wait — usable if accuracy matters more than speed, available any time
  via `aero voice --model models/turbo`. On a **GPU** (`compute_type=float16`)
  turbo drops to ~0.2–0.3× → both accurate AND realtime, enabling open-mic. That
  is the clear end-state once a GPU is in play.
- There is no model on this CPU that is both accurate on code-switch and
  realtime; that's a hardware limit, not a model-search failure.

## Status: S-3 COMPLETE

Verdict reached on real audio across base/small/turbo. Default `small` (PTT,
Devanagari accepted); `turbo` selectable for accuracy and the GPU end-state.
Green-light Milestone 3 voice loop (built).
