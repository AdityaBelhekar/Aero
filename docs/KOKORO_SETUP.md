# Aero's Real Voice — Kokoro (fast, natural, CPU)

Kokoro-82M is Aero's English voice: tiny (82M params), natural-sounding, and
**faster-than-realtime on CPU**. Measured on this box (2026-07-11): warm **RTF
~0.62–0.77×** (~1.6 s to synthesize ~2.5 s of speech), first call ~5 s incl.
model load. Contrast Parler at 277× (19 min/sentence) — this is why English-only
+ the right model wins. Default real voice for a CPU box.

Runs via `kokoro-onnx` (ONNX Runtime). Because it's ONNX, it can also use your
**integrated GPU** (Windows DirectML) for extra speed — a real win at this model
size, unlike the 0.9B Parler.

## 1. Install

```powershell
python -m pip install -e ".[kokoro]"
# == kokoro-onnx + soundfile
```

Optional — use your integrated GPU (Intel/AMD) via DirectML:
```powershell
python -m pip install onnxruntime-directml
```

## 2. Download the two model files (once)

Place both in `models/kokoro/` (gitignored):
- `kokoro-v1.0.onnx` (~310 MB) —
  https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/kokoro-v1.0.onnx
- `voices-v1.0.bin` (~26 MB) —
  https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/voices-v1.0.bin

```powershell
mkdir models\kokoro
curl -L -o models\kokoro\kokoro-v1.0.onnx  https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/kokoro-v1.0.onnx
curl -L -o models\kokoro\voices-v1.0.bin   https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/voices-v1.0.bin
```
(Flaky network? `curl -L -C -` resumes a partial download.)

## 3. Pick Aero's voice and use it

```powershell
python -m aero.cli voices                       # lists Kokoro voices + status
python -m aero.cli voices --set am_michael      # switches engine=kokoro
python -m aero.cli speak "chal bhai, let's build"  # audition
python -m aero.cli voice                         # full loop with the Kokoro voice
python -m aero.cli voices --engine sapi          # back to the placeholder voice
```

Aero is a young Indian male; Kokoro has no Indian-English voice, so the closest
fits are warm young male voices: `am_michael`, `am_adam`, `am_fenrir` (American)
or `bm_george`, `bm_lewis` (British). Female options exist too (`af_heart` is the
highest-graded). Full catalog: Kokoro-82M `VOICES.md` on HuggingFace.

## Notes
- Output is 24 kHz mono; Aero plays it directly.
- `SpeechIntent.pace` maps to Kokoro's `speed` (Kokoro has no emotion model yet;
  the affective fields are carried for a future backend).
- If the model files are missing, `health_check()` is False and the voice loop
  falls back to SAPI, telling you — nothing breaks.
- Selection persists in `AERO_HOME/settings.json`; model files under `models/`
  are gitignored.
