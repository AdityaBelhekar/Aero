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

## Open item (network-blocked, not a blocker)

`large-v3-turbo` (large-v3 accuracy, ~4× faster) is the likely upgrade for
**open-mic + snappier PTT**, but its ~1.6 GB HuggingFace download failed 3×
here on connection resets (WinError 10054), incl. with `hf_transfer`. It's cached
partially and **resumes** — re-run when on a stable network / VPN:
```
HF_HUB_ENABLE_HF_TRANSFER=1 python spikes/s3_stt_probe.py --model large-v3-turbo
```
Fallbacks if turbo underwhelms on CPU: `distil-large-v3`, or **AI4Bharat
IndicWhisper** (R-3 fallback, Indic-specialised, Devanagari output).

## Status: S-3 COMPLETE

Verdict reached on real audio. Whisper `small`, push-to-talk, Devanagari accepted.
Green-light Milestone 3 voice loop. Revisit the model for open-mic once a
faster-accurate model can be fetched.
