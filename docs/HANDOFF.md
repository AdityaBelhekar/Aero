# AERO — Handoff (continue in a new chat)

**Purpose:** everything a fresh session needs to continue building Aero without
re-deriving context. Read this top-to-bottom, then start at "THE NEXT TASK".

**Repo:** `C:\Users\Aditya\Desktop\Aero` · GitHub `https://github.com/AdityaBelhekar/Aero.git` (branch `main`)
**Docs:** `Aero-PRD-v0.2.md` (requirements, IDs like AERO-XXX), `Aero-Implementation-Plan.md` (milestones/spikes).
**Env:** Windows 11, 16 GB RAM, **CPU-only (no GPU)**, Python 3.11, Ollama installed, ffmpeg installed.

---

## TL;DR — the decision just made

Switch Aero's **ears (STT)** and **mouth (TTS)** to **AI4Bharat**, scoped to
**English + Marathi only** (Hindi de-prioritised). Rationale: Aditya speaks
English-heavy with Marathi mixed in ("bhai assignment nhi zali ata ky kru"), and
AI4Bharat handles Indian-English + code-mixed Marathi.

- **STT:** `ai4bharat/indicconformer_stt_mr_hybrid_ctc_rnnt_large`
- **TTS:** `ai4bharat/indic-parler-tts`
- **Approach:** try it; if it fails / disappoints, swap (fallbacks noted below).
  Everything is behind swappable interfaces, so swapping is one new file.

**Do NOT rewrite what exists — just add two new backends + benchmark.**

---

## PROJECT STATE — what's already built & working (don't rebuild)

All committed & pushed. **60 tests pass** (`python -m pytest -q`). Milestones 1 & 2
done; Milestone 3 (voice) mostly done.

**Brain / memory (Milestone 1–2, DONE):**
- `src/aero/vault/` — encrypted SQLite memory vault (schema v1, audit journal, backup/restore). CLI `aero init/status/backup/restore/smoke`.
- `src/aero/cognition/` — `CognitionService` interface + `OllamaCognition` (model `gemma4:e4b`, **thinking OFF by default** — it's a reasoning model, leaving it on returns empty content) + `OllamaEmbedder` (`embeddinggemma`, 768-dim).
- `src/aero/memory/` — store, consolidation (LLM tagging → episodic/semantic memories + graph edges + belief reconcile: reinforce/contradict/staleness sweep), hybrid retrieval (vector anchor → graph spread → rerank + Wild Recall + social-fit).
- `src/aero/prompts/` — versioned tagging/reconcile/persona prompts.
- `src/aero/working_set.py`, `src/aero/agent.py` — assemble context + run a memory-in-the-loop turn.
- `src/aero/perception/tier0.py` — Tier-0 world state (active window/process/idle via ctypes).
- `src/aero/daemon.py` — always-on daemon: keep models warm + idle consolidation. CLI `aero daemon`.
- **Proven:** preference told in session 1 survives consolidation + restart and resurfaces in session 2 with provenance.

**Two-speed brain + cloud option (added after the AI4Bharat spike):**
- `src/aero/effort.py` — `classify()` routes each turn `reflex` (banter/acks/commands)
  vs `deep` (memory-reaching/substantive). Memory-first: core identity is ALWAYS in
  the prompt; reflex skips only the expensive retrieval (and the embeddinggemma call,
  which was evicting gemma4 and forcing ~10s reloads). Measured: reflex ~2x faster.
- **The real latency wall is gemma4:e4b itself on CPU: ~5-11s/turn (prefill is
  free; it's the 9.6 GB model). No prompt trick fixes it — needs a smaller model or
  GPU, OR the cloud brain below.**
- `src/aero/cognition/cloud_backend.py` — `CloudCognition`, an OpenAI-compatible
  online brain (Groq/OpenAI/OpenRouter/Gemini) for real-time replies. Local gemma4
  stays the private default; cloud is opt-in via `aero brain --set cloud` (key from
  env, never persisted). Memory stays 100% local — only generation goes online.
  `settings.build_brain()` picks it. See `docs/CLOUD_BRAIN_SETUP.md`.

**Real-time hands-free loop (DONE + proven) — the no-button conversation:**
- `src/aero/voice/vad.py` — `VAD` iface, `EnergyVAD` (dep-free default), optional
  `SileroVAD`, and `VADSegmenter` (pure endpointing state machine — unit-tested).
- `src/aero/voice/mic_stream.py` — `MicStream` (sounddevice, optional) + pcm->wav.
- `src/aero/voice/realtime.py` — `RealtimeLoop`: mic -> VAD endpointing -> STT ->
  agent(+memory, two-speed) -> Kokoro, with **barge-in** (interruptible winsound
  playback). `handle_utterance` is the testable core. CLI: `aero voice --realtime`.
- Proven end-to-end on real audio: VAD auto-segmented one turn, Moonshine
  transcribed a synthesized English line **verbatim**, hands-free. Extras:
  `.[realtime]` (sounddevice) / `.[realtime_silero]`. See docs/REALTIME_SETUP.md.
- Tuning lives in `SegmenterConfig` (start_ms/end_silence_ms/preroll_ms) +
  `EnergyVAD.threshold`/`calibrate`; barge-in via `RealtimeLoop(barge_in_ms=...)`.

**English ear — Moonshine (fast English STT, DONE + proven):**
- `src/aero/perception/moonshine_stt.py` — `MoonshineSTT(STTService)` via
  `useful-moonshine-onnx` (import `moonshine_onnx`; pure ONNX, no torch). Models
  `moonshine/tiny` (26M) | `moonshine/base` (58M, default). Selected via
  `aero voice --model moonshine[/tiny]`; factory in `indic_stt.build_stt`.
  **Proven: clean English → near-verbatim** (Kokoro→Moonshine round-trip returned
  sentences word-for-word). Garbles Marathi by design (English-only — that's the
  point of the English pivot). RTF ~realtime on `base` (faster offline / on tiny).
  PyPI dist is `useful-moonshine-onnx`, NOT `moonshine-onnx`. See docs/MOONSHINE_SETUP.md.

**English voice — Kokoro (the CPU-fast real voice, DONE + proven):**
- `src/aero/voice/kokoro_tts.py` — `KokoroTTS(TTSService)` via `kokoro-onnx`.
  **Measured warm RTF ~0.62-0.77x on this CPU** (faster than realtime; first call
  ~5s incl. load). Real 24 kHz speech proven end-to-end. This is the answer to the
  Parler-277x dead end. Model files (~336 MB) in `models/kokoro/` (gitignored),
  downloaded from the kokoro-onnx v1.0 release. `engine=kokoro`, voices like
  `am_michael`/`bm_george` via `aero voices --set am_michael`. ONNX → can use the
  iGPU via onnxruntime-directml. See `docs/KOKORO_SETUP.md`.

**Voice (Milestone 3, current state):**
- `src/aero/perception/stt.py` — `STTService` interface + `FasterWhisperBackend` (Whisper `small` default, configurable beam). **This is the STT interface to implement against.**
- `src/aero/voice/speech_intent.py` — `SpeechIntent` (delivery: energy/pace/pauses/etc.) + SSML renderer + `intent_from_text()`.
- `src/aero/voice/tts.py` — `TTSService` interface + `SapiTTS` (Windows placeholder voice). **This is the TTS interface to implement against.**
- `src/aero/voice/svara_tts.py` — `SvaraTTS` (HTTP client to a Svara server; built but server never stood up). Example of the client-backend pattern.
- `src/aero/voice/mic.py` — push-to-talk mic capture via ffmpeg (no extra deps). `aero mics`.
- `src/aero/voice/loop.py` — `VoiceLoop` ties mic → STT → agent → intent → TTS. CLI `aero voice` (and `--text` mode).
- `src/aero/settings.py` — persisted TTS engine + voice choice (`AERO_HOME/settings.json`); `build_tts()` picks the backend. `aero voices` lists/selects.

**Spike verdicts (in `spikes/`):**
- **S-1** (`S1_VERDICT.md`): gemma4:e4b viable. It's a reasoning model → thinking OFF.
- **S-2** (`S2_VERDICT.md`): embeddinggemma 90% top-1 on romanised Marathi/Hindi.
- **S-3** (`S3_VERDICT.md`): tested base/small/turbo Whisper on Aditya's 10 real clips. small comprehends code-switch (outputs Devanagari, fine for gemma4) but ~1.5× RTF; turbo best+stable but ~3.5× (too slow on CPU); base too weak. **This is why we're now trying AI4Bharat.**

**Test recordings:** `rec/*.m4a` (Aditya's 10 code-switched sentences) → converted to `spikes/s3_testset/*.wav` (16k mono). References in `spikes/s3_testset/manifest.tsv`. **Audio is gitignored (biometric).**

---

## THE NEXT TASK — wire AI4Bharat STT + TTS

### Step 0 — confirm inference setup (do this first, network is flaky)
Read the HF model cards for exact inference code before installing:
- STT: https://huggingface.co/ai4bharat/indicconformer_stt_mr_hybrid_ctc_rnnt_large
- TTS: https://huggingface.co/ai4bharat/indic-parler-tts

Likely dependencies (verify):
- **IndicConformer** → NVIDIA **NeMo** (`nemo_toolkit[asr]`) — HEAVY. Check the model card for a lighter path (ONNX export, or the `ai4bharat/IndicConformer` repo's own inference). Loads via `nemo.collections.asr`. Outputs Devanagari; supports CTC and RNNT decoding. Claims Indian-English + code-mix support.
- **Indic Parler-TTS** → `pip install git+https://github.com/huggingface/parler-tts.git` + transformers. Input = text + a natural-language **description** of the voice (e.g. "a young male Indian voice, warm and casual"). ~a few GB. Output ~44.1 kHz wav.

### Step 1 — BENCHMARK STT before committing (empirical, we have the data)
Run the Marathi conformer against Aditya's 10 clips and compare to Whisper `small`:
- Harness: `spikes/s3_stt_probe.py` (currently takes `--model` for faster-whisper). Either add an IndicConformer path to it, or write a small parallel probe. Reference transcripts already in `spikes/s3_testset/manifest.tsv`.
- Decide by **reading the outputs**, not just WER (WER is unfair vs Devanagari — see S-3 verdict). Care about: does it get the English words right? the Marathi? and RTF (< 1.0 wanted for snappy voice).
- If conformer beats Whisper on Aditya's voice → adopt it. If not → keep Whisper `small`, revisit.

### Step 2 — implement the backends (same swappable pattern as existing)
- **STT:** new `src/aero/perception/indic_stt.py` → class `IndicConformerSTT(STTService)` implementing `transcribe(audio_path, language=None) -> Transcript` and `health_check()`. Mirror `FasterWhisperBackend`. Add it as a selectable `--model`/engine in `aero voice`.
- **TTS:** new `src/aero/voice/parler_tts.py` → class `ParlerTTS(TTSService)` implementing `synthesize(intent, out_path) -> SpeechResult`, `speak(intent)`, `health_check()`. Map `SpeechIntent` → a Parler voice-description string (Aero = young Indian male, warm, casual). Register in `settings.build_tts()` (add `engine == "parler"`) and in `aero voices` engine choices.
- Add optional extras in `pyproject.toml` (`[project.optional-dependencies]`): e.g. `indic_stt = [...]`, `parler = [...]`.
- Add hermetic tests (mock the heavy model, like `tests/test_svara.py` mocks HTTP): interface shape, engine selection, settings round-trip.

### Step 3 — wire selection + fallback
- `settings.py`: engine options become `sapi | svara | parler` (+ STT choice). Keep graceful fallback to SAPI/Whisper if a backend is unavailable.
- Update `docs/` with a short setup note (like `docs/SVARA_SETUP.md`).

### Step 4 — try it end-to-end, then decide
Run `aero voice`, talk, judge quality + latency. If Parler is too slow on CPU
(likely — it's LLM-style), fall back options in priority order:
1. **`ai4bharat/vits_rasa_13`** (VITS — light, CPU-fast, Indian voices) ← best CPU fallback
2. `ai4bharat/IndicF5` (F5-TTS)
3. Sarvam **API** (Saaras codemix STT + Bulbul TTS) — cloud, not open, but near-free with ₹1000 credits and best code-switch; good "online boost" tier if local disappoints
4. Keep SAPI placeholder

---

## KEY GOTCHAS / LESSONS (save yourself the pain)

- **Indic Parler-TTS backend PROVEN working but GPU-only (measured 2026-07-11).**
  `ParlerTTS` synthesizes real 44.1 kHz mono speech end-to-end (verified
  non-silent, intent→voice-description mapping works), but on this CPU it took
  **1162 s for a 4.2 s line — RTF ≈ 277x** (~19 min/sentence). Unusable live.
  Pulls flan-t5-large + dac_44khz alongside the 0.9B model. **Verdict: keep SAPI/
  the CPU-fast path; use Parler only on a GPU.** CPU-friendly Aero voice fallback
  = AI4Bharat VITS (`vits_rasa_13`). Backend + `engine=parler` wiring stay ready.
- **IndicConformer STT needs the AI4Bharat NeMo FORK — upstream PyPI NeMo can't
  load it (proven 2026-07-11).** The `.nemo` (downloaded OK to `models/indicconformer_mr/`)
  uses a `multilingual` tokenizer + `multisoftmax` RNNT decoder, both fork-only.
  With `nemo_toolkit==2.7.3` it dies on `KeyError: 'dir'`, then (after an
  agg-tokenizer config patch) on `RNNTDecoder ... unexpected kwarg 'multisoftmax'`.
  The fork's `bash reinstall.sh` is Linux-only (pynini) → doesn't build on this
  Windows box. **Verdict: STT stays Whisper `small` on this box;** run
  IndicConformer under WSL2 / Linux / GPU, or use the Sarvam API tier. The
  `IndicConformerSTT` backend, resilient downloader, and `--backend indic` probe
  are all wired and ready for such a box. TTS (Parler) is unaffected — it's a
  plain transformers model, downloadable and pip-installable (not gated for DL).
- **AI4Bharat models are GATED** — `indicconformer_stt_mr_hybrid_ctc_rnnt_large`,
  `indic-parler-tts` (and the umbrella `indicconformer`) are `gated=auto`. You must
  click "Agree and access repository" on each HF model page (logged in as the
  cached-token account, `ItsxxAdityaa`) before weights download. Auto-grant is
  instant, but until accepted the `.nemo`/weights 403 with `GatedRepoError ... not
  in the authorized list` — this is terms-not-accepted, NOT the network. `model_info`
  still returns metadata even when unaccepted, so gating check ≠ download works.
  See `docs/AI4BHARAT_SETUP.md`.
- **Downloads keep failing on this network** — HuggingFace resets connections (`WinError 10054 / ECONNRESET`) on large pulls. Turbo (1.6 GB) failed 3× incl. with `hf_transfer`. **Mitigations:** small models download fine; for big ones use `huggingface-cli download <repo> --local-dir models/<name>` and **re-run to resume**, or download in a browser/download-manager, or a VPN. `models/` is gitignored. Ollama registry stalled similarly once — same network issue, not the tools.
- **CPU-only, no GPU.** Every heavy model is slow: turbo STT ~3.5× RTF, Parler/Svara TTS will be seconds-per-sentence. VITS and small models are the CPU-friendly ones. This is a hardware ceiling; a GPU changes everything (turbo → ~0.2× etc.).
- **gemma4:e4b is a reasoning model** — always run with thinking OFF (already handled in `OllamaCognition`; keep it that way). Cold model load ~40s; the daemon keeps it warm.
- **Devanagari STT output is FINE** — gemma4 reads it natively downstream, so don't require romanised transcripts. WER against romanised references is misleading; judge by reading outputs.
- **Never commit audio or the vault** — `.gitignore` covers `*.wav *.m4a rec/ data/ models/ *.vault`. Voice = biometric.
- **Windows shell:** use `PYTHONIOENCODING=utf-8` for scripts printing Devanagari/emoji or the console crashes (cp1252). Tests run via `python -m pytest -q` (pyproject sets `pythonpath=src`).
- **Two-tier philosophy option:** local (open, private, default) + optional online boost (Sarvam API) when quality/speed matters. Sarvam speech is API-only/paid (open-core: LLMs open, voice closed). AI4Bharat is fully open (MIT) — the local answer.

---

## COMMANDS CHEAT-SHEET

```powershell
cd C:\Users\Aditya\Desktop\Aero
$env:PYTHONIOENCODING = "utf-8"

python -m pytest -q                         # 60 tests, all green
python -m aero.cli status                   # vault info
python -m aero.cli chat                      # text chat with memory
python -m aero.cli consolidate               # turn chat into memory (idle write path)
python -m aero.cli daemon                    # always-on: keep-warm + idle consolidation
python -m aero.cli voice                     # full voice loop (mic PTT -> STT -> Aero -> TTS)
python -m aero.cli voice --text              # no mic; type, Aero speaks
python -m aero.cli voices                    # list/select TTS voice + engine
python -m aero.cli mics                      # list microphones
python spikes/s3_stt_probe.py --model small  # STT benchmark on the 10 clips

ollama list                                  # gemma4:e4b + embeddinggemma present
```

---

## FILE MAP (where things live)

```
Aero-PRD-v0.2.md / Aero-Implementation-Plan.md   # requirements + plan
src/aero/
  cli.py                    # all subcommands
  config.py  settings.py    # paths; persisted voice/engine prefs
  daemon.py  agent.py  working_set.py
  vault/                    # encrypted memory store + backup + audit
  cognition/                # LLM + embeddings (Ollama), swappable
  memory/                   # store, consolidation, retrieval, models
  prompts/                  # tagging, reconcile, persona (versioned)
  perception/
    tier0.py                # world state (window/process/idle)
    stt.py                  # STTService + FasterWhisperBackend  <- add IndicConformerSTT
  voice/
    tts.py                  # TTSService + SapiTTS               <- add ParlerTTS
    svara_tts.py            # client-backend pattern example
    speech_intent.py  mic.py  loop.py
tests/                      # 60 tests (mirror patterns for new backends)
spikes/                     # S1/S2/S3 verdicts + probes + s3_testset (audio gitignored)
docs/SVARA_SETUP.md         # pattern for a backend setup doc
rec/                        # Aditya's m4a recordings (gitignored)
models/                     # downloaded weights go here (gitignored)
```

---

## SUGGESTED FIRST MESSAGE FOR THE NEW CHAT

> "Continue Aero. Read docs/HANDOFF.md. Task: benchmark
> `ai4bharat/indicconformer_stt_mr_hybrid_ctc_rnnt_large` against Whisper small on
> my 10 clips in spikes/s3_testset, then wire AI4Bharat STT + `ai4bharat/indic-parler-tts`
> as new swappable backends (English + Marathi scope). Don't rebuild existing stuff.
> Network drops big HF downloads — use resumable pulls to models/."
```
```
