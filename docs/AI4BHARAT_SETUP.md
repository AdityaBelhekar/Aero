# Enabling AI4Bharat Backends (IndicConformer STT + Indic Parler-TTS)

Aero's ear (STT) and mouth (TTS) are swappable. This adds two **AI4Bharat**
backends, scoped to **English + Marathi** — Aditya speaks English-heavy with
Marathi mixed in, and these models are trained for exactly that.

- **STT:** `ai4bharat/indicconformer_stt_mr_hybrid_ctc_rnnt_large` — 120M
  Conformer, Marathi-primary, Devanagari output (gemma4 reads it natively),
  hybrid CTC (fast) / RNNT (accurate) heads.
- **TTS:** `ai4bharat/indic-parler-tts` — 0.9B; you *describe* the voice in
  words instead of picking a fixed profile.

Both are optional and **heavy + CPU-slow** — kept behind the same interfaces as
Whisper/SAPI, so nothing else changes. If a backend isn't installed, Aero falls
back automatically (Whisper for STT, SAPI for TTS) and says so.

## Reality check (your hardware: Windows, 16 GB, CPU-only)

- **IndicConformer (STT):** 120M params — CPU-runnable. CTC decoding is the fast
  path. See `spikes/S3_VERDICT.md` + the benchmark below for whether it beats
  Whisper `small` on Aditya's voice.
- **Indic Parler (TTS):** 0.9B, LLM-style generation. **MEASURED on this box
  (2026-07-11): 1162 s to generate a 4.2 s line — RTF ≈ 277x.** The backend works
  end-to-end (real 44.1 kHz mono speech, verified non-silent; intent→description
  mapping applied) but ~19 min/sentence is unusable for live voice. Also pulls
  `google/flan-t5-large` (text encoder) + `ylacombe/dac_44khz` (audio codec).
  **Verdict: Parler is GPU-only for real use.** CPU-friendly Aero voice = AI4Bharat
  VITS (`vits_rasa_13`). The `ParlerTTS` backend stays wired for a GPU box.

## 1. Install (isolated venv recommended for NeMo)

NeMo pulls a large dependency tree and can shift `torch`/`numpy` versions, so
install the STT stack in its **own venv** to keep the main env's tests green:

```powershell
python -m venv .venv-nemo
.\.venv-nemo\Scripts\python.exe -m pip install -U pip wheel setuptools
.\.venv-nemo\Scripts\python.exe -m pip install "nemo_toolkit[asr]"
```

> ⚠️ **The model card's fork requirement is real — upstream PyPI NeMo canNOT
> load this model.** Empirically confirmed 2026-07-11 with `nemo_toolkit==2.7.3`:
> the `.nemo` uses a `tokenizer.type: multilingual` (per-language `langs` map)
> AND a custom `multisoftmax` RNNT decoder — both are AI4Bharat-fork-only.
> Upstream fails first with `KeyError: 'dir'` (routes the multilingual tokenizer
> through the monolingual path); patching the tokenizer to `agg` then hits
> `RNNTDecoder.__init__() got an unexpected keyword argument 'multisoftmax'`.
> So you MUST build AI4Bharat's fork (`git clone AI4Bharat/NeMo`,
> `git checkout nemo-v2`, `bash reinstall.sh`) — which is Linux-oriented and
> pulls Linux-only deps (pynini). On this Windows/CPU box that build does not
> complete; use **WSL2 or a Linux/GPU box** for IndicConformer, or fall back to
> Whisper `small` (already benchmarked, works — see spikes/S3_VERDICT.md) or the
> Sarvam API online-boost tier. The `IndicConformerSTT` backend + download +
> probe path are all wired and ready for a box where the fork builds.

TTS (Parler) installs cleanly into the main env:

```powershell
python -m pip install -e ".[parler]"
# == parler-tts (from git if PyPI lags) + transformers + soundfile
# if PyPI has no parler-tts wheel:
python -m pip install "git+https://github.com/huggingface/parler-tts.git"
```

### Gated access (one-time, required)

All three AI4Bharat models are **gated** (`gated=auto`). Before the weights will
download you must click **"Agree and access repository"** on each page, logged in
as the HF account whose token is cached (`~/.cache/huggingface/token`). Approval
is instant (auto-grant) — but until you accept, downloads 403 with
`GatedRepoError: ... not in the authorized list` (this is **not** the flaky
network — it's terms-not-accepted):

- https://huggingface.co/ai4bharat/indicconformer_stt_mr_hybrid_ctc_rnnt_large
- https://huggingface.co/ai4bharat/indic-parler-tts

Then `huggingface-cli login` (or set `HF_TOKEN`) if not already cached.

Model weights auto-download from HuggingFace on first use into the HF cache
(`models/` is gitignored). **This network also drops big HF pulls**
(`WinError 10054`) — just re-run; downloads resume.

## 2. Benchmark STT before adopting (we have the data)

Decide empirically on Aditya's 10 real clips (`spikes/s3_testset`). Judge by
**reading the outputs**, not WER — WER against romanised references is unfair to
Devanagari output (see `spikes/S3_VERDICT.md`). Care about: are the English words
right? the Marathi? and RTF < 1.0 for live voice.

```powershell
$env:PYTHONIOENCODING = "utf-8"
# from the NeMo venv (has nemo); runs aero from source:
.\.venv-nemo\Scripts\python.exe spikes\s3_stt_probe.py --backend indic --decoder ctc
.\.venv-nemo\Scripts\python.exe spikes\s3_stt_probe.py --backend indic --decoder rnnt
# compare against the incumbent:
python spikes\s3_stt_probe.py --model small
```

If IndicConformer wins on Aditya's voice → adopt it (below). If not → keep
Whisper `small`.

## 3. Select the backends

```powershell
# STT: pass 'indic' as the model in the voice loop
python -m aero.cli voice --model indic          # IndicConformer (CTC)
python -m aero.cli voice --model small          # Whisper (default)

# TTS: switch the engine (persists in AERO_HOME/settings.json)
python -m aero.cli voices --engine parler
python -m aero.cli speak "chal bhai, code karte hain"   # audition
python -m aero.cli voices --engine sapi          # switch back
```

Persisted STT choice lives in `settings.json` (`stt_model`); `--model` overrides
it per run.

## 4. If Parler is too slow on CPU (likely)

Fallbacks in priority order (all swap in as one new `TTSService` file):
1. **`ai4bharat/vits_rasa_13`** (VITS — light, CPU-fast, Indian voices) ← best.
2. `ai4bharat/IndicF5` (F5-TTS).
3. **Sarvam API** (Saaras codemix STT + Bulbul TTS) — cloud, paid, best
   code-switch; good "online boost" tier if local disappoints.
4. Keep SAPI placeholder.

## Notes
- Everything (weights, `settings.json`, the venv) is gitignored. Never commit
  audio or the vault — voice is biometric.
- IndicConformer needs **16 kHz mono WAV** (Aero's mic capture already produces
  this; the S-3 testset is already converted).
