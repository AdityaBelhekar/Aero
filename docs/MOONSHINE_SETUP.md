# Aero's Fast English Ear — Moonshine

Moonshine is an English-only ASR built for real-time on the edge: tiny (26M/58M),
**pure ONNX (no PyTorch)**, low latency on CPU. It's the speed play for Aero's
ears once the scope is English — a better fit than Whisper for a snappy voice
loop. (Code-switched Marathi is out of scope by design; that was the AI4Bharat
path. For English, Moonshine is faster and lighter.)

## 1. Install

```powershell
python -m pip install -e ".[moonshine]"
# == useful-moonshine-onnx  (provides `import moonshine_onnx`; pure ONNX, no torch)
```

## 2. Use it

Weights auto-download from HuggingFace on first use (tiny/base are small — quick).

```powershell
python -m aero.cli voice --model moonshine          # base (58M, more accurate)
python -m aero.cli voice --model moonshine/tiny     # tiny (26M, fastest)
python -m aero.cli voice --model small              # back to Whisper
```

Persist it as the default:
```powershell
# settings.json stt_model; or pass --model each run
```

Models:
- `moonshine/tiny` — 26M, lowest latency.
- `moonshine/base` — 58M, more accurate (Aero's default when you pass `moonshine`).

## Measured (2026-07-11, this CPU)

On Aditya's 10 *code-switched* clips (worst case — English-only model): the
**English words come through clean** ("is too bitter for me", "the whole night",
"can you open ... the local AI project"); the **Marathi words garble** (expected —
that's out of scope now). Mean warm **RTF ~1.05× on `base`**; `tiny` is faster.
On pure-English speech it's both cleaner and quicker.

## Notes
- English-only, 16 kHz mono (Aero's mic capture already produces this).
- Returns Latin-script English text — clean for the LLM and for reading logs.
- If `moonshine_onnx` isn't installed, `health_check()` is False and Aero keeps
  using the configured Whisper backend — nothing breaks.
- Pairs naturally with the Kokoro voice (docs/KOKORO_SETUP.md): fast English ear
  + fast English mouth = the real-time loop's two ends.
