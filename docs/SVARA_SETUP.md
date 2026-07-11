# Enabling Aero's Real Voice (Svara-TTS)

Aero speaks through a swappable TTS backend. The default is Windows SAPI (a
robotic placeholder). The **real Aero Voice** is [Svara-TTS](https://huggingface.co/kenpath/svara-tts-v1)
— 38 voice profiles across 19 Indian languages, offline-capable.

Aero talks to Svara as a **server** (OpenAI-compatible speech API), exactly like
it talks to Ollama for the LLM. You run the Svara server; Aero points at it and
stays a thin client. This keeps Aero light and lets the model run wherever the
compute is.

## Reality check (your hardware)

Svara is an Orpheus-style model — LLM-class compute per utterance.
- **On a GPU:** fast, real-time capable. This is the intended setup.
- **On CPU only (your current box):** it *works* but is **slow** (many seconds
  per sentence), same as turbo STT was. Fine for trying it; not for snappy chat.

## 1. Start the Svara server

Official inference: https://github.com/Kenpath/svara-tts-inference

**GPU (recommended):**
```bash
git clone https://github.com/Kenpath/svara-tts-inference
cd svara-tts-inference
pip install -r requirements.txt
# OpenAI-compatible server (model auto-downloads from HF on first run):
python -m vllm.entrypoints.openai.api_server \
    --model kenpath/svara-tts-v1 --port 8080
# (the repo also ships a FastAPI wrapper that adds the SNAC decoder;
#  follow its README so /v1/audio/speech returns WAV)
```

**CPU / no vLLM:** vLLM targets Linux+CUDA. On Windows-CPU, use the repo's
FastAPI path with `SNAC_DEVICE=cpu`, or run under WSL2. Expect slow synthesis.

The endpoint Aero expects:
```
POST http://localhost:8080/v1/audio/speech
{ "model": "svara-tts-v1", "voice": "hi_male", "input": "...", "response_format": "wav" }
```

## 2. Point Aero at it and pick your voice

```powershell
# see all 38 voices and whether the server is reachable
python -m aero.cli voices

# choose your voice (this also switches the engine to svara)
python -m aero.cli voices --set hi_male      # young Indian male, Hindi
# other natural fits for Aero: mr_male (Marathi), en_male (Indian English)

# audition it
python -m aero.cli speak "chal bhai, code karte hain" 

# use it in the full loop
python -m aero.cli voice
```

If the server isn't reachable, Aero automatically falls back to SAPI and tells
you — nothing breaks.

## 3. Voice profiles

Format: `{language}_{gender}`. Languages: en, hi, mr, bn, ta, te, kn, ml, gu,
pa, or, as, ur, sa, ne, kok, mai, sd, doi — each with `_male` and `_female`.
Run `aero voices` for the full list with names.

## Switching back
```powershell
python -m aero.cli voices --engine sapi
```

## Notes
- Svara's output is 24 kHz mono; Aero requests `wav` and plays it directly.
- Your selection persists in `AERO_HOME/settings.json`.
- Once you have a GPU (or a hosted Svara server), just update the base URL /
  keep localhost — no code change needed.
- The `settings.json` and any downloaded models under `models/` are gitignored.
