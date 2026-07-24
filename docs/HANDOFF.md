# AERO — Handoff (continue in a new session)

**Purpose:** everything a fresh session needs to continue Aero without re-deriving
context. Read top-to-bottom, then pick from "WHAT TO DO NEXT".

**Last updated:** 2026-07-24, after building **M4 Proactivity** (the impulse
generator + gate, thought threads, relationship model, self-memory) on top of the
v0.3 "Open Aero" plan (M8–M15) + connect-any-AI + the full voice marketplace.

---

## TL;DR — where things stand

- **Everything is architecturally built and unit-tested (546 passing), but almost
  nothing has run against a real service.** The whole session was hermetic —
  mocked HTTP, injected backends, no live models. That is the #1 thing to know.
- **Branch:** `feat/english-realtime-voice` (NOT `main` — it's ~42 commits ahead).
  All work (incl. M4) is committed + pushed to GitHub over SSH.
- **The v0.3 plan (M8–M15) is complete.** Plus: 21 brain providers, 3 OAuth logins,
  7 STT + 8 TTS engines (all cloud adapters written incl. Google).
- **The biggest conceptual hole is now filled: M4 Proactivity is BUILT** —
  `proactive/` package: two-tier impulse generator (tier 1, no model) + impulse
  gate (tier 2, LLM, **structural default-silence**), thought threads, relationship
  model, self-memory logging of every decision incl. silences, feedback-learned
  thresholds. Wired into the daemon tick + `aero proactive` CLI. Never run live
  (like everything else) — the gate's LLM social eval has only met fake brains.

---

## ENVIRONMENT (Ubuntu — migrated from Windows mid-project)

- **OS:** Ubuntu 26.04. Ships Python **3.14**, which is too new for the ML wheels.
- **Python:** a **uv-managed 3.11 venv** at `/home/aditya/Desktop/Dev/Aero/.venv`.
  Run everything via `.venv/bin/python`. `uv` is at `~/.local/bin`.
- **Installed extras:** `dev,stt,embed` (torch 2.13, faster-whisper,
  sentence-transformers, sqlite-vec).
- **NOT installed (need sudo; user chose to skip for now):** `ffmpeg` (mic) and
  `ollama` + models `gemma4:e4b` + `embeddinggemma` (the brain). **So nothing that
  needs the live brain/voice can actually run yet.**
- **Vault:** plaintext (no `sqlcipher3`) — a warning prints; fine for dev.
- **Git:** SSH auth configured (key added to GitHub). `git push` works.
- Tests: `.venv/bin/python -m pytest -q` → **491 passed, 3 skipped**.

---

## WHAT'S DONE (all committed + pushed)

Pre-session baseline: M1–M3 (encrypted vault, memory core, partial voice), 60 tests.

### The v0.3 "Open Aero" plan — M8–M15, all built

- **M8 Open Brain** (`cognition/`): brain registry of swappable profiles
  (`registry.py`), two-speed router (`router.py` — chat→primary, tagging→reflex,
  privacy guard, degrade-never-die), keyring key vault (`keys.py`).
- **M9 Presence** (`presence/`): the avatar *puppeteer* — `AvatarState`, rig
  manifest, emotion map (SpeechIntent→Emotion), animation state machine, ambient
  fidget scheduler, `PresenceDriver`. **No renderer** (the puppet) — needs a 3D
  model + spikes S-11/S-12.
- **M10 Control App** (`control/`): `ControlService.dispatch(op,params)` — the
  whole management API (status/brain/voice/persona/perms/memory/hands/eyes/play/
  body). Local-socket IPC server + client wired into the daemon. `aero control`
  CLI. Persona dials + permissions + kill switch in settings. **Tauri GUI is
  scaffolded (`ui/control-app/`) but never compiled** (needs webkit+Rust+display).
- **M11 Voice Marketplace** (`voice/`, `perception/`): engine catalog
  (`voice/catalog.py`), fallback chain (`voice/fallback.py`), voice keyring,
  lip-sync feed (`voice/lipsync.py`, audio→avatar mouth). All cloud adapters
  written: `voice/cloud_tts.py` (ElevenLabs/Sarvam/Cartesia/Google),
  `perception/cloud_stt.py` (Deepgram/Sarvam/Google).
- **M12 Little Hands** (`hands/`): consent gate (`consent.py` — kill-switch >
  default-deny > hard-gate-confirm > allow, all structural code), actuator audit
  journal (`journal.py` + `actuator_log` table), executor (`executor.py` — the
  only path a tool runs), user-authorable skills, MCP bridge. **S-10 consent
  red-team PASSED** (`spikes/S10_VERDICT.md`).
- **M13 Eyes** (`perception/vision.py`, `ocr.py`, `vision_router.py`):
  consent-gated ephemeral capture (screen/camera scopes), OCR interface,
  scene-change sampler, multimodal routing (CognitionService.see + CloudCognition
  vision). **Real capture unavailable headless** — grabbers report
  `available()=False` until a display/camera exists.
- **M14 Play** (`play/`): GameConnector interface, anti-cheat policy (spectate-only
  games structurally refuse actions), Minecraft LAN bridge (needs an external Node
  Mineflayer process), spectator (vision-only), voice+game+avatar fusion.
- **M15 Body** (`body/`): platform abstraction (`host.py` — detects windows/
  linux-desktop/linux-arm/headless; fixes the Windows-only tier0), hardware I/O
  (`hardware.py` — servos/LEDs/display-face, no-op when absent), shared face rig
  (`face.py`), robot profile + Pi brain preset + systemd autostart (`robot.py`).

### Post-plan extras (user-requested)

- **Connect any AI** (`cognition/providers.py`, `discovery.py`, `account.py`): 21
  brain providers — 6 local (Ollama/LM Studio/llama.cpp/Jan/vLLM/LocalAI, with
  `--discover`), 12 cloud-by-key (incl. Claude/ChatGPT/Grok/Gemini/Kimi/DeepSeek/
  Cohere/Perplexity/Qwen/Cerebras/NVIDIA/Mistral/Together/Fireworks), 3 OAuth
  logins (OpenRouter PKCE, Hugging Face auth-code, GitHub device). `aero brain
  --providers/--discover/--login/--oauth-client`.
- **KEY BOUNDARY (do not cross):** no path uses a consumer **ChatGPT/Claude
  subscription** — that requires ToS-violating web-session reverse-proxying and was
  explicitly declined 3×. "Log in and use all models" = **OpenRouter** (one login
  reaches Claude/GPT/Grok/etc. legitimately). Keep this line.

---

## WHAT'S LEFT / NOT DONE

### Missing core features (biggest gaps)

1. ~~**Proactivity — impulse generator + gate (M4, PRD §7).**~~ **BUILT** this
   session (`src/aero/proactive/`). Two-tier: tier-1 impulse generation (cheap,
   no model, never timer-based per AERO-PRO-001) + tier-2 LLM gate with
   *structural* default-silence (kill switch / quiet hours / staleness / below-
   threshold all short-circuit to silence in code, before any token is spent).
   Every decision incl. silences logged to `self_memory` (AERO-PRO-006). Feedback
   learning routes interruption tolerance → gate threshold, joke/quality →
   relationship (AERO-FBK-003). Daemon surfaces a "speak" as a quiet text message
   on the `proactive` raw-event channel. See `docs/PROACTIVITY_SETUP.md`.
2. ~~**Thought threads**~~ **BUILT** — `proactive/threads.py`: active→dormant→
   resolved lifecycle, cap 20, trigger matching feeds tier-1 reactivation.
3. ~~**Relationship model**~~ **BUILT** — `proactive/relationship.py`: slow-moving
   dims with bounded per-nudge delta (AERO-REL-003), conservative cold-start seeds
   (AERO-COLD-003). *Gates the threshold* (familiarity) + moved by feedback.
4. **Attention history / heat** — feeds retrieval rerank; **still not implemented**
   (the one M4-adjacent piece left; AERO-ATT-001).

**Proactivity's own gaps:** the tier-1 producers are a starter set (novelty,
return-from-away, repeated-failure, thread-reactivation) — no humour/contradiction/
memory-activation producers yet, and `recent_failures` is passed as 0 by the
daemon (no failure detector wired). The gate's LLM social eval has never met a
real brain.

### Built but NEVER RUN LIVE (the verification debt)

- **Nothing has executed against a real service this whole session.** All hermetic.
- **~20 cloud brain adapters + 8 cloud voice adapters** — written to documented API
  shapes, unit-tested for request shaping, **never called live**. Each needs one
  real key + one call. This is where surprises will be.
- **OAuth logins** (OpenRouter/HF/GitHub) — flows per spec, never hit live; HF +
  GitHub need registered OAuth apps first.
- **TTS on Linux:** default is SAPI (**Windows-only, dead on Ubuntu**). Kokoro/Svara
  are the Linux paths but were never stood up/tested.

### Needs external things (not just code)

- **M9 avatar renderer** — Aditya's 3D model/clips + spike S-11 (web/Three.js vs
  Godot) + S-12 (lip-sync). Wayland/X11 matters on 26.04.
- **M10 Tauri GUI** — `sudo apt install libwebkit2gtk-4.1-dev` + Rust + a display.
- **M13 real capture** — a display (screen) / camera device.
- **M14 Minecraft** — a Node Mineflayer bridge process against a LAN world.
- **M15 Pi** — real hardware; spike S-8 (latency) deferred.

### Housekeeping

- Branch not merged to `main`. README still says "Milestone 2".
- 7 pre-existing ruff errors in files not touched this session
  (`voice/loop.py`, `voice/mic_stream.py`, `voice/mic.py`, `memory/store.py`,
  `memory/consolidation.py`).
- Deferred spikes: S-6, S-7, S-8, S-11, S-12 (all have NOTES files under `spikes/`).

---

## KEY GOTCHAS / LESSONS

- **Run via `.venv/bin/python`** (uv Python 3.11). System `python3` is 3.14 and
  will break ML deps.
- **gemma4:e4b is a reasoning model → thinking OFF** (handled in `OllamaCognition`;
  keep it). Cold load ~40s; daemon keeps it warm.
- **Devanagari STT output is fine** — gemma4 reads it; don't require romanised.
- **The consent gate + play anti-cheat are STRUCTURAL (code, not prompts).** Two
  red-teams pass (S-10 consent, play anti-cheat). Don't weaken these; re-run their
  tests after any change near actions/games.
- **Everything follows one pattern:** interface → registry of profiles → builder →
  (consent gate where it acts). Brains, voices, tools, games, providers all mirror
  it. New backends implement the interface; nothing else changes.
- **Cloud adapters isolate one network method** (`_send`/`_post`) so request
  shaping is unit-tested without the network. When verifying live, that's the
  method that actually hits the wire.
- **Never commit audio/vault** (`.gitignore` covers `*.wav *.m4a rec/ data/
  models/ *.vault`). Voice = biometric.
- **End commit messages with** `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`.

---

## COMMANDS CHEAT-SHEET

```bash
cd /home/aditya/Desktop/Dev/Aero
PY=.venv/bin/python

$PY -m pytest -q                       # 491 passing
$PY -m aero.cli brain --providers      # 21 AI providers (local/key/login)
$PY -m aero.cli brain --discover       # which local model servers are running
$PY -m aero.cli brain --login openrouter   # OAuth login (untested live)
$PY -m aero.cli voices --catalog       # 7 STT + 8 TTS engines
$PY -m aero.cli control ops            # every control-plane operation
$PY -m aero.cli hands tools            # consented actions
$PY -m aero.cli eyes status            # vision sources + grants
$PY -m aero.cli play games             # play/spectate policy
$PY -m aero.cli body status            # host/robot/hardware
$PY -m aero.cli proactive status       # M4: gate state + relationship + threads
$PY -m aero.cli proactive simulate --app impulse.py --title generator.py --hour 14  # one hermetic gate tick

# needs sudo (skipped for now):  sudo apt install ffmpeg
#                                curl -fsSL https://ollama.com/install.sh | sh
```

---

## FILE MAP (new since M3)

```
src/aero/
  proactive/  impulse.py generator.py threshold.py gate.py threads.py
              relationship.py selfmem.py loop.py   # M4 — the impulse gate
  cognition/  registry.py router.py keys.py providers.py discovery.py account.py
              cloud_backend.py(see) service.py(see/VisionUnsupported)
  presence/   state.py rig.py emotion.py state_machine.py ambient.py driver.py
  control/    service.py ipc.py            # management API + daemon socket
  hands/      tool.py registry.py consent.py journal.py executor.py skills.py mcp_bridge.py
  perception/ vision.py ocr.py vision_router.py cloud_stt.py   (+ tier0/stt/indic/moonshine)
  voice/      catalog.py fallback.py lipsync.py cloud_tts.py   (+ tts/svara/kokoro/parler/…)
  play/       connector.py minecraft.py spectator.py fusion.py
  body/       host.py hardware.py face.py robot.py
  daemon.py   # tick() now also runs proactive._maybe_proact (M4)
  settings.py # widened: brain registry, persona dials, permissions, robot, oauth_client_ids, proactive
  cli.py      # + brain(expanded) control hands eyes play body proactive
ui/control-app/           # Tauri scaffold (uncompiled)
docs/  OPEN_BRAIN_SETUP CONTROL_APP_SETUP VOICE_MARKETPLACE LITTLE_HANDS EYES_SETUP
       PLAY_SETUP BODY_SETUP PRESENCE_SETUP PROACTIVITY_SETUP  (+ this file)
spikes/ S5_VERDICT S10_VERDICT S8_NOTES S11_S12_NOTES
tests/  ~56 files, 546 tests  (6 new: test_proactive_* + daemon proactive surface)
Aero-v0.3-Open-Aero-Plan.md   # the plan just completed
```

---

## WHAT TO DO NEXT (pick one — user will decide)

1. **Prove ONE path live** — now the biggest remaining risk. E.g. get an OpenRouter
   key, run one real `aero chat` turn; or `aero proactive simulate` against a real
   gemma4 to see the gate's social eval actually judge a moment; or stand up Kokoro
   TTS and hear one line. Turns "546 tests pass" into "it actually works."
2. **Finish M4's tail** — attention-history heat feeding retrieval rerank
   (AERO-ATT-001, the one M4-adjacent piece skipped); wire a real `recent_failures`
   detector into the daemon; add more tier-1 producers (humour opportunity,
   contradiction-with-habit, memory-activation). All hermetic.
3. **Consolidate** — merge branch→main, refresh README/status, tidy the 7 ruff nits.
4. **Unblock a visual piece** — author a starter 3D model (M9 avatar) or install the
   Tauri toolchain (M10 GUI).

**Recommendation:** #1 — the codebase is now broad, deep (M4 fills the last core
gap), and well-tested, but has still never met reality. That gap is the tension.
