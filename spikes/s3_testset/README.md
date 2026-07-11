# S-3 STT Test Set — Recording Protocol

A real S-3 verdict needs **your** voice: your accent and the exact way you mix
English, Hindi, and Marathi. Synthetic audio can smoke-test the pipeline but
can't tell us whether the model understands *you*.

## What to do (~15 minutes)

1. Record yourself reading each sentence below, one audio file per sentence.
2. Save as WAV (mono, 16 kHz preferred; the harness resamples anyway) in this
   folder, named `01.wav`, `02.wav`, ...
3. Speak naturally — your real accent, real pace. Don't over-enunciate; the point
   is real-world usage.
4. The reference transcripts are already in `manifest.tsv` (matching numbers).

Recording options:
- Windows Voice Recorder app (export/convert to WAV via ffmpeg if it saves .m4a:
  `ffmpeg -i clip.m4a -ar 16000 -ac 1 01.wav`)
- Or Audacity → Export as WAV.

Then run:
```
python spikes/s3_stt_probe.py --model small
```
Try `--model medium` too if `small`'s accuracy is weak and RTF still < 1.0.

## Sentences (read these; they're also in manifest.tsv)

1. bhai ye assignment ka deadline kal aahe and I haven't even started yet
2. mala vatat this approach wrong aahe, model la context samajla pahije
3. arey nako yaar, genuinely boltoy, valorant khelायचं nahi aaj
4. can you open our thing, the local AI project wala folder
5. raat ko late tak code karta hoon, that's when I focus best
6. coffee smooth medium roast havi, dark roast is too bitter for me
7. wait actually this could work, ek second thamb
8. instagram scroll karat basu nako, assignment complete kar pehle
9. bhai mouse ka problem hai, that's why I bottom-fragged, seriously
10. weekend la Rohan yenar aahe, we'll game together the whole night

These deliberately cover: Marathi+English switch, Hindi+English switch, tech
vocabulary inside vernacular, romanised verbs with Devanagari fragments, and
casual filler — the exact patterns Aero must handle (PRD Section 5).

## What the numbers mean

- **WER** (word error rate) — harsh on romanised spelling variants ("nahi"/"nahin").
- **CER** (character error rate) — more forgiving; better signal for "is this
  transcript usable downstream by memory/consolidation".
- **RTF** (realtime factor) — compute ÷ audio length. Must be **< 1.0** for live
  voice, ideally well under, to fit the ≤1.2 s voice budget (PRD Section 24).

If `small` gives WER under ~0.25 and RTF under ~0.6, that's a green light for
Milestone 3. If accuracy is weak, next candidates are `medium` (slower) or an
AI4Bharat IndicWhisper model (risk R-3 fallback path).
