# AERO — v0.3 "Open Aero" Plan

**Version:** 0.3 (planning)
**Date:** 2026-07-13
**Prior docs:** `Aero-PRD-v0.2.md` (requirements), `Aero-Implementation-Plan.md` (M1–M7, spikes S-1..S-4)
**Codebase this builds on:** M1–M3 done — encrypted vault, two-speed memory brain, always-on daemon, local (gemma4:e4b) **and** cloud brains, real-time English voice, swappable STT/TTS. 60 passing tests.

> **On the version number.** You asked for a "v0.2" plan, but the repo already ships `Aero-PRD-v0.2.md` (the doc the current build implements). To avoid overwriting it, this is numbered **v0.3**. The number is cosmetic — this is the "take Aero to new levels" plan.

---

## 0. What Aero Is (and Is Not)

**Aero is a friend who lives in your laptop.** A partner. Someone who's *there* — on your screen, doing his own thing, ready to talk, chill, react, roast you at 2am when you're losing in Valorant. He remembers you. He has a face and a body you can see.

**Aero is NOT a coding agent, an assistant, or a productivity tool.** He *can* do helpful things if you ask and allow it — but that's a side effect of being a good companion, not his job. His job is **presence and personality.**

Everything in this plan serves that. The pluggable brains, the voices, the little hands, the eyes — they exist so Aero can *be a better friend*, more expressive, more present, more himself. If a feature makes Aero more of a tool and less of a buddy, we don't build it.

### The shape of v0.3

Two things you can see and touch:

1. **Aero on your screen** — a **windowless, transparent, always-on-top overlay** rendering a **3D robot avatar** (model + animations *you* author). He idles, wanders, fidgets, reacts to what's happening, talks with lip-sync and expressions. This is the heart of the product.
2. **The Control App** — a normal window where you configure him: log into AI accounts, pick/manage brains, choose voices, grant or revoke what he's allowed to do, browse his memories, set his mood/personality. This is the "settings & login" surface.

Everything else (open brains, voice marketplace, little hands, eyes, games, and eventually a physical Pi body) plugs into those two.

---

## 1. Guiding Rules (extends the v0.2 rules)

The v0.2 rules stand (*memory before mouth, state over weights, budgets are gates, de-risk with spikes, instrument everything*). v0.3 adds:

6. **Companion first, capability second.** Every feature is judged by "does this make Aero a better friend to have around?" — not "is this useful?". Presence, personality, and expressiveness outrank functionality.
7. **Consent is the API.** Aero acts on your machine/world only through capabilities you explicitly granted — gated, logged, revocable. A friend you let borrow your car still asks before selling it. No silent side effects.
8. **The core is provider-agnostic.** No brain/voice/tool vendor name appears anywhere except behind an adapter. Swapping models or voices is a Control-App click, never a code change. (We already do this for brain via `CognitionService` and voice via `build_tts`/`build_stt` — v0.3 generalises it.)
9. **Degrade, never die.** Every paid/cloud capability has a free/local fallback. Aero must still be *himself* — think, speak, listen, remember, and be on screen — fully offline.
10. **Presence is portable.** The same Aero (persona + memory + avatar) runs as a screen overlay on a laptop today and on a Raspberry Pi robot tomorrow. Platform-specific bits sit behind ports, never in the core.
11. **You make the body, we make it live.** You author the 3D model and its animation clips. Aero's job is to *drive* them intelligently — pick the right animation for the moment, lip-sync to speech, express the mood. The rig is content; the puppeteer is code.

---

## 2. The Pillars

Ordered by what makes Aero *Aero*. Presence and the app come first; capabilities plug in after.

### Pillar 1 — Presence: Aero on your screen (the 3D avatar overlay)

**This is the soul of v0.3.** A windowless desktop character that's just... there.

**What it is:**
- A **frameless, transparent, always-on-top** window (optionally click-through) that renders your **3D robot model** somewhere on the desktop — a corner, floating, wandering.
- Driven by an **animation state machine** fed by Aero's live state over the existing local IPC from the daemon:
  - **Ambient/idle** — random micro-behaviours so he never looks frozen: look around, stretch, fidget, glance at what you're doing, occasional bored/playful bits.
  - **Listening** — when the mic is hot (push-to-talk or wake).
  - **Thinking** — while the brain is generating.
  - **Speaking** — lip-sync + gestures timed to TTS audio.
  - **Emotion/mood** — driven by `SpeechIntent`'s affective fields (already in the codebase, PRD §30): happy, teasing, tired, hyped, etc. mapped to expression/pose.
  - **Actions** — one-off animations you author ("wave", "facepalm", "dance", "point at screen") that Aero can trigger on cue or when a moment calls for it.
- **You author** the model + clips (Blender/Godot); Aero maps clip names → states/emotions via a **rig manifest** (a JSON that says "this clip = talking, this one = happy-idle, these = fidgets"). New animations = drop a clip + add a manifest line. No code change.

**Design decisions:**
- **Rendering stack is a spike (S-11).** Two honest options: a web stack (transparent Tauri/Electron window + Three.js / react-three-fiber rendering a glTF/GLB) vs. a native engine (Godot with a transparent window). Web = easiest transparency + overlay + shipping; Godot = better animation tooling and closer to the eventual robot/face. You have both in your toolbox — the spike decides. glTF/GLB is the interchange either way.
- **Lip-sync is a spike (S-12).** Simplest reliable path: viseme/amplitude analysis of the TTS audio stream → jaw/mouth blendshape. If the chosen TTS engine emits phoneme timings, use those (crisper). Must work for whichever voice engine is active (Pillar 3).
- **Idle behaviour is a personality system, not random noise.** A weighted scheduler picks ambient animations by mood + time of day + what you're doing (Tier-0 world state already knows your active window). "It's 2am and you're in Valorant" → a specific set of reactions. This is where Aero feels *alive* vs. a screensaver.
- **The overlay is a thin client.** All brains/memory/voice live in the daemon; the overlay just renders state + plays audio + forwards mic/clicks. Keeps it cheap and keeps the same daemon reusable for the physical Pi face later (Pillar 8).
- **Interaction:** click/drag him around, click to talk, he can react to being poked. Small touches sell the friendship.

**New requirements:** `AERO-PRES-101` transparent always-on-top avatar overlay · `AERO-PRES-102` animation state machine (idle/listen/think/speak/emotion/action) · `AERO-PRES-103` rig manifest (clip→state/emotion mapping, user-extensible) · `AERO-PRES-104` lip-sync from TTS audio · `AERO-PRES-105` personality-driven ambient behaviour scheduler (mood + world-state) · `AERO-PRES-106` direct interaction (drag, poke, click-to-talk).

---

### Pillar 2 — The Control App (login, settings, management)

The normal window where the human tunes their friend. This is also where "login to your AI account" actually happens — properly, via a real OAuth/login webview, not a sketchy headless session.

**What it holds:**
- **Accounts & brains** — log into AI accounts (OAuth in an embedded webview), paste API keys (stored in the OS keyring, never in a file), point at a LiteLLM proxy, pick/switch the active brain, set the routing policy (private-local vs. big-cloud), see a live cost meter + spend cap.
- **Voice** — browse the STT/TTS catalog, pick per role, preview voices, manage engine keys/servers. (Extends today's `aero voices`.)
- **Permissions** — grant/revoke what Aero may do (files, shell, apps, browser, games), scoped and revocable, with the audit log visible. The **kill switch** lives here.
- **Personality & mood** — dials for how Aero behaves: chattiness, roast-level, formality, quiet hours. Persona lives in the vault; this edits it.
- **Memory browser** — see/search/edit/forget what Aero remembers (the optional M2 memory-browser UI from v0.2, now first-class). A friend you can ask "what do you remember about me?" and correct.
- **Avatar** — load your model, map clips in the rig manifest, position/scale the overlay, pick idle-behaviour intensity.

**Design decisions:**
- **Two windows, one daemon.** The overlay (Pillar 1) and the Control App are both thin clients over the existing daemon IPC. This is exactly the "daemon runs headless, UI attaches" split the v0.2 impl plan already anticipated.
- **Tauri preferred** (RAM footprint — the v0.2 plan already leaned this way), Electron acceptable. If S-11 picks Godot for the avatar, the Control App can still be Tauri; they only share the IPC contract.
- **OAuth-in-app legitimises account login.** Hosting a real provider login in a webview is far more robust and ToS-friendly than driving a headless session — it turns risky Spike S-6 into a mostly-solved UX problem.

**New requirements:** `AERO-APP-201` Control App shell (Tauri, daemon IPC client) · `AERO-APP-202` account login (OAuth webview) + keyring key storage · `AERO-APP-203` brain manager (pick/switch/route/cost cap) · `AERO-APP-204` voice manager · `AERO-APP-205` permissions & kill-switch UI · `AERO-APP-206` personality/mood dials · `AERO-APP-207` memory browser.

---

### Pillar 3 — The Open Brain (any model powers the friend)

Aero's *personality lives in the vault, not the weights* — so the brain is a swappable engine.

**Where we are:** `CognitionService` (chat + `complete_json` + `health_check`) is the whole contract; `OllamaCognition` (local) and `CloudCognition` (OpenAI-compatible) implement it; `build_brain()` picks one. **The seam exists — we widen it.**

**Target — configure any brain, ranked by how much we do for the user:**

| Mode | User provides | Adapter |
|---|---|---|
| **Local** | nothing (gemma4:e4b default) | `OllamaCognition` (exists) |
| **API key** | provider + key (OpenAI, Anthropic, Groq, OpenRouter, Sarvam-LLM…) | `CloudCognition`, generalised |
| **LiteLLM proxy** | one base URL to their gateway | `CloudCognition` at that URL — **works today**, needs a preset + docs |
| **Account login** | OAuth via the Control App | `AccountCognition` (much easier now that login is a webview, not headless) |

**Design decisions:**
- **LiteLLM is the recommended power path** — `CloudCognition` already speaks OpenAI-compatible, so a local LiteLLM proxy unlocks ~100 providers for near-zero code. Cheapest big win.
- **A brain registry** replaces the two-way `brain` string: named profiles (`{id, adapter, base_url, model, key_env, cost_tier, supports_vision}`), switchable per context — private-local for personal talk, big-cloud for hard stuff. The daemon already keeps the local model warm.
- **Two-speed routing survives as a router** — cheap/private/local for reflex + memory-tagging (the `complete_json` pass should use the *cheapest reliable* brain to control cost), strong brain when needed.
- **Personality is prompt+memory, not model.** The persona (`prompts/persona.py`) + vault ride on top of whatever brain — so switching models changes *how smart/fast/expensive* Aero is, never *who* he is.

**New requirements:** `AERO-BRAIN-301` brain registry & profiles · `AERO-BRAIN-302` LiteLLM proxy support + preset · `AERO-BRAIN-303` brain router (cost/privacy/capability policy) · `AERO-BRAIN-304` keyring-based key vault · `AERO-BRAIN-305` account-login brain (via Control-App OAuth).

---

### Pillar 4 — The Voice Marketplace (how he sounds)

**Where we are:** `build_tts`/`build_stt` already switch between SAPI/Svara/Parler/Kokoro (TTS) and Whisper/IndicConformer (STT). **Marketplace foundation exists.**

**Target — a catalog the user browses, mixing free/local and paid/cloud:**

| | Free / local | Paid / cloud |
|---|---|---|
| **STT** | Whisper (small…turbo), Moonshine, IndicConformer | Sarvam STT, Deepgram, ElevenLabs Scribe |
| **TTS** | Kokoro, Svara, Piper, SAPI | ElevenLabs, Sarvam TTS, Cartesia, PlayHT |

**Design decisions:**
- **Formalise the contract:** extract `STTEngine` / `TTSEngine` protocols (mirroring `CognitionService`) + a registry, so the `settings.py` if-ladder becomes a lookup and third-party engines are drop-ins.
- **Voice must feed the face.** The active TTS engine must expose audio (and ideally phoneme timing) to the avatar's lip-sync (Pillar 1). Streaming engines (ElevenLabs, Cartesia) keep the real-time loop snappy — first-audio-out fast.
- **Emotion mapping:** `SpeechIntent` affective fields drive both the *voice* (on engines that support emotion — ElevenLabs/Svara) and the *face* expression, in sync. No-op gracefully elsewhere.
- **Fallback chain** (Rule 9): paid server down/out-of-credits → fall to a local voice, tell the user once, never hard-stall.

**New requirements:** `AERO-VOX-401` `STT/TTSEngine` protocols + registry · `AERO-VOX-402` capability catalog (cost/latency/lang/emotion) · `AERO-VOX-403` streaming synthesis + lip-sync feed · `AERO-VOX-404` keyring keys + fallback chain.

---

### Pillar 5 — Little Hands (fun & allowed helpful actions — NOT a coding agent)

Aero *can* do things on your machine — but framed as a friend doing you a favour, always opt-in, never his identity. Think "hey Aero, open Spotify / what's on my screen / clean my Downloads / drop this in Minecraft" — not "autonomous engineering agent".

**Model:** tools (atomic actions) → skills (little recipes) → connectors (apps/games), all behind consent.

**Design decisions:**
- **Deliberately light and playful.** Launch apps, control media, read/organise files in an allowed folder, open a URL, react to notifications, run a user-authored skill. High-risk stuff (shell, arbitrary writes) is off unless the user deliberately turns it on.
- **MCP client bridge** — expose Aero's tool layer as an MCP client so existing MCP servers become capabilities behind the same consent gate. Big reach, little code. (This is the "any tool" analogue of LiteLLM for brains.)
- **Consent framework (the load-bearing safety part):** default-deny per scope; reversible+granted → act; irreversible (delete/send/buy/post) → **always confirm**; ungranted → refuse + explain. Every call audited in the vault (extends the existing mutation journal). Global **kill switch**. Red-teamed (S-10) before anything ships.
- **Tool-calling wants a capable brain** → the router (Pillar 3) escalates to a strong brain for action turns, stays local for chat.
- **Coding help, if wanted, is just one optional skill** (invoke Claude Code in a repo you point at) — an add-on for the technical user, explicitly *not* the centre of gravity.

**New requirements:** `AERO-ACT-501` tool protocol + typed registry · `AERO-ACT-502` capability grants (per-scope, vault, revocable) · `AERO-ACT-503` tiered confirmation · `AERO-ACT-504` actuator audit journal · `AERO-ACT-505` user-authorable skills · `AERO-ACT-506` MCP client bridge · `AERO-ACT-507` kill switch + dry-run.

---

### Pillar 6 — Eyes (so he can react to what's happening)

Vision exists so Aero can *react like a friend in the room* — see the game, the meme, the error, and comment.

**Design decisions:**
- **Tier 1 — Screen.** On trigger (you ask, or a Tier-0 event fires), grab the active window → local OCR (RapidOCR/Paddle) for cheap text, or a multimodal brain for real understanding. Builds on `perception/tier0.py` (already tracks active window/process/idle). This makes "roast you at 2am in Valorant" literally possible — Aero *sees* the scoreboard.
- **Tier 2 — Camera** (optional, local-only) — presence/expression, so the desk robot feels aware of you.
- **Vision is a brain capability** (`supports_vision` in the registry), not a separate stack. Off by default, per-source consent, frames ephemeral unless you ask him to remember one. Sample sparsely to control cost.

**New requirements:** `AERO-VIS-601` screen capture + OCR · `AERO-VIS-602` multimodal brain routing · `AERO-VIS-603` camera tier (local-only) · `AERO-VIS-604` vision consent & ephemerality.

---

### Pillar 7 — Play (games together, Minecraft first)

The friend who actually joins in.

**Design decisions:**
- **Minecraft** via a headless bot bridge (Mineflayer / a Fabric mod exposing a local socket) that joins your **LAN world**. Aero sees state (position, inventory, entities, chat), reasons with the brain, acts (mine/build/follow), and talks — by voice *and* in-game chat. Memory ties it together ("we built the river base last week"). It's a game-scoped **actuator** under the same consent model.
- **Voice + game + avatar fused** — the magic moment: you're in the world, you talk to Aero, he answers *and* acts, and the on-screen face reacts.
- **`GameConnector` interface** (join/observe/act/leave) so Minecraft is first but not last.
- **Where automation is banned (competitive games), Aero is a spectator** — vision (Pillar 6) reads the screen and he *watches & roasts*, never automates. Explicit per-game: *plays* vs. *watches*.

**New requirements:** `AERO-PLAY-701` `GameConnector` interface · `AERO-PLAY-702` Minecraft LAN bridge (actuator) · `AERO-PLAY-703` voice+game+avatar fusion · `AERO-PLAY-704` spectator mode (vision-only commentary) · `AERO-PLAY-705` per-game consent + anti-cheat policy.

---

### Pillar 8 — A Body (Raspberry Pi → real robot, later)

The physical extension of the *same* Aero — persona, memory, voice, and the same face, now on a desk robot.

**Design decisions:**
- **Same daemon, platform ports.** Core is portable Python already; SAPI (Windows TTS) and ctypes window hooks get Linux/ARM implementations behind a platform abstraction. Kokoro/Piper/Svara are the Pi-friendly voices.
- **The overlay's avatar becomes the robot's face** — render the same rig on a small attached display (the "eyes"), same state machine, same lip-sync. The screen character and the robot are literally the same puppet.
- **Compute-constrained → the brain router shines** — a Pi likely runs a small local reflex model + a LAN/cloud LiteLLM brain for anything hard. A settings choice, not a fork.
- **Hardware I/O layer** — mic array, speaker, display-face, optional servos/LEDs for head-turn and mood. Behind an interface, so "no servos" just no-ops. **Spike S-8 proves Pi latency before we commit.**

**New requirements:** `AERO-BODY-801` platform abstraction (perception/TTS/audio ports) · `AERO-BODY-802` ARM/Linux daemon + autostart · `AERO-BODY-803` hardware I/O (mic array, speaker, display-face, GPIO/servos) · `AERO-BODY-804` robot profile config · `AERO-BODY-805` shared rig on the physical face.

---

## 3. Architecture: how it slots onto the existing core

```
   ┌─────────────────────┐     ┌─────────────────────┐
   │  AVATAR OVERLAY      │     │  CONTROL APP         │   two thin clients,
   │  (windowless 3D)     │     │  (settings/login)    │   one shared daemon
   └──────────┬──────────┘     └──────────┬──────────┘
              └───────────── IPC ──────────┘
                            │
        ┌───────────────────▼────────────────────┐
        │   DAEMON  (keep-warm • brain router •   │  runs on Windows now,
        │   consent gate • audit • state → avatar)│  Raspberry Pi later
        └───────────────────┬────────────────────┘
                            │
  ┌─────────┬───────────────┼───────────────┬──────────┬──────────┐
  │ BRAIN   │ VOICE         │ HANDS         │ EYES     │ PLAY     │ BODY
  │ registry│ STT/TTS       │ tools+skills  │ screen/  │ game     │ Pi/robot
  │ +router │ registry      │ +MCP+consent  │ camera   │ connectors│ ports
  └─────────┴───────────────┴───────────────┴──────────┴──────────┘
                            │
                 ┌──────────▼──────────┐
                 │  VAULT (unchanged)  │  identity • memory • grants • audit
                 └─────────────────────┘
```

- **Nothing above the vault is new *shape*** — it's the same interface-behind-a-registry pattern Aero already uses for brain and voice, extended to the avatar, tools, vision, and games.
- **The daemon gains three jobs:** stream **state to the avatar**, run the **brain router**, and enforce the **consent gate** (every action passes through it).
- **The vault gains two tables:** capability grants + the actuator audit journal (extensions of existing patterns).
- **The overlay and Control App are the "UI attaches to headless daemon" split** the v0.2 plan already called for.

---

## 4. Milestones (continuing M1–M7; M1–M3 done)

Presence-first. Capabilities plug in after Aero is *there* and configurable.

| # | Milestone | Delivers | Depends on |
|---|---|---|---|
| **M8** | **Open Brain** | Brain registry, LiteLLM preset, per-turn router, keyring keys. Quick widen of an existing seam; the personality needs a home. | current build |
| **M9** | **Presence** | The windowless 3D avatar overlay: rig manifest, animation state machine, lip-sync, personality-driven idle behaviour, click-to-talk. **The heart.** | M8, your model+clips |
| **M10** | **Control App** | Tauri app: account login (OAuth), brain + voice managers, personality dials, memory browser, permissions + kill switch. | M8, M9 |
| **M11** | **Voice Marketplace** | `STT/TTSEngine` protocols + registry, catalog, streaming + lip-sync feed, first paid engine (Sarvam or ElevenLabs), fallback chain. | M9 (lip-sync), M10 (keys UI) |
| **M12** | **Little Hands** | Tool protocol, consent framework, audit, kill switch, MCP bridge, first playful skills. *The safety milestone — nothing ships until consent is airtight.* | M8 (strong brain), M10 (grants UI) |
| **M13** | **Eyes** | Screen capture + OCR, multimodal routing, consent/ephemerality. Camera optional. | M8, M12 (consent) |
| **M14** | **Play (Minecraft)** | `GameConnector`, Minecraft LAN bridge, voice+game+avatar fusion, spectator mode. | M12, M9, voice loop |
| **M15** | **Body (Pi/robot)** | Platform ports, ARM daemon, hardware I/O, shared rig on a physical face, robot profile. | M8–M13 portable |

**v0.3 "he's really here" milestone** = M8→M11: Aero stands on your screen as a 3D character, powered by any brain you chose, speaking in a voice you picked with a face that lip-syncs and emotes — all configured from an app where you logged in and tuned him. Hands, eyes, games, and a physical body come after that foundation of *presence*.

---

## 5. De-risking Spikes (written verdict each, before their milestone)

- **S-5 — LiteLLM + router (2 days).** `CloudCognition` → local LiteLLM proxy, 3+ providers through one seam; prototype cost/latency routing. *Gate: M8.*
- **S-11 — Avatar render stack (3 days).** Transparent overlay rendering an animated glTF: **web (Tauri + Three.js) vs. Godot**. Test transparency, always-on-top, click-through, animation blending, RAM/CPU idle cost. *Gate: M9. Highest-uncertainty spike — do it early.*
- **S-12 — Lip-sync (2 days).** Drive a mouth blendshape from live TTS audio (viseme/amplitude, or phoneme timing if the engine gives it). Must work across voice engines. *Gate: M9.*
- **S-6 — Account login via webview (2 days).** OAuth/login in an embedded webview → a working brain session. Now a UX spike, not a scary headless one. *Gate: M10.*
- **S-7 — Tool-calling quality (3 days).** Local vs. cloud brain on multi-tool orchestration + structured calls. Sets the router's escalation policy. *Gate: M12.*
- **S-10 — Consent red-team (2 days).** Adversarially try to make Aero do something irreversible without confirmation. **Consent model must survive this before any hand ships.** *Gate: M12.*
- **S-9 — Minecraft bridge (2 days).** Headless bot into a LAN world, read state, execute a build from Aero. *Gate: M14.*
- **S-8 — Pi latency (3 days).** Daemon + small local brain + Piper/Kokoro + the avatar on a Pi 5; measure loop latency + RAM. Decides local-vs-LAN-brain on Pi. *Gate: M15.*

---

## 6. Budgets & Gates (extends PRD §24)

- **Presence cost.** The idle avatar overlay must be cheap — target low single-digit % CPU and modest RAM when Aero is just standing there (S-11 sets the number). He's on screen all day; he can't be a space heater.
- **Latency.** Real-time voice first-audio-out stays snappy even with streaming paid TTS; face begins moving as audio starts. Actions acknowledge < 500 ms.
- **Cost.** With paid brain/voice, a live cost meter + a hard user-set monthly cap enforced by the router; tagging/consolidation uses the cheapest reliable brain.
- **RAM.** Windows core still ≤ 12 GB *including* the overlay. Pi profile has its own budget (S-8).
- **Safety (hard gate):** no hand ships until default-deny proven, irreversible actions always confirm, every call audited, kill switch works, S-10 passes.
- **Offline / plane test:** all cloud off → Aero still stands on screen, thinks (local brain), speaks (local voice), hears, remembers, and runs granted *local* actions. Every release.

---

## 7. Risks

| ID | Risk | Mitigation |
|---|---|---|
| R-9 | **Hands = attack surface.** Bad decision + broad grant = real damage. | Default-deny, tiered confirm, audit, kill switch, S-10. M12 is "the safety milestone". |
| R-17 | **The avatar looks dead/janky** — kills the whole "friend" feeling. | Idle-behaviour *personality* system (not random noise), lip-sync + emotion sync, S-11/S-12 early. Presence quality is the product. |
| R-18 | **Overlay is a resource hog** (always on screen). | Thin client, budget gate in S-11, throttle idle animation when unfocused/on battery. |
| R-11 | **Weak local brain can't orchestrate tools.** | Router escalates for action turns (S-7). |
| R-10 | **Account login fragile/ToS-risky.** | OAuth-in-webview (S-6) instead of headless; API-key + LiteLLM cover the ask regardless. |
| R-12 | **Paid lock-in / cost surprise.** | Adapters + free fallback (Rule 9); spend cap; cost meter. |
| R-13 | **Pi can't hit latency locally.** | S-8; LAN-offloaded brain as documented Pi default. |
| R-14 | **Game bans from automation.** | Play only where allowed (Minecraft LAN); competitive = spectator/vision-only. |
| R-15 | **Vision leaks screen/camera to cloud.** | Off by default, per-source consent, local OCR preferred, ephemeral frames. |
| R-16 | **Scope explosion** (8 pillars, solo cadence). | Strict order; each pillar independently shippable; body/games explicitly *after* presence + config land. |

---

## 8. Open Questions

1. **Avatar stack** — web (Three.js in a Tauri overlay) or Godot? *(S-11)* — bias: web for shipping speed + transparency, unless animation authoring pushes to Godot.
2. **Model/animation pipeline** — what format + tooling do *you* want to author in (Blender → glTF? Godot native? VRM?), and what's the minimum clip set for a lively v1 (idle × N, talk, a few emotions, a few actions)? *(pre-M9)*
3. **Brain routing** — auto (Aero picks by task) vs. manual (you pick per context) vs. both? *(M8)*
4. **First paid voice** — Sarvam (Indic-native, fits the code-switch identity) or ElevenLabs (top quality, English-first)? *(M11)* — bias: **Sarvam**.
5. **Personality controls** — how much is user-tunable (roast level, chattiness, quiet hours) vs. fixed Aero character? *(M10)*
6. **Skill format** — reuse Claude Code's skill shape (shareable) or a leaner Aero-native one? *(M12)*
7. **Physical body scope for v1** — screen-face on a display only, or commit to servos/movement? *(M15)* — bias: face-first, servos as a "robot profile" add-on.

---

## 9. Why This Order

- **M8 (Open Brain)** is a near-free widen of an existing seam and gives the personality a home on any model — do it first, quick.
- **M9 (Presence)** is the soul — Aero *appears*, has a face, lip-syncs, idles with personality. Nothing else matters if he doesn't feel alive on screen.
- **M10 (Control App)** lets a human actually own and tune their friend — login, models, voices, memory, permissions.
- **M11 (Voice)** makes him *sound* like whatever you want, synced to the face.
- **M12 (Hands)** — where we slow down and make consent unbreakable, because everything after depends on it.
- **M13–M14** turn capability into companionship: he reacts to your screen, plays Minecraft with you.
- **M15 (Body)** is the payoff — the same friend, now a robot on your desk — and it only works because brain, voice, presence, and hands were built portable.

Same Aero. A face you can see, a friend you configure, running on any brain and any voice — on your screen today, on your desk tomorrow. Built for fun, built to be *there*.

---

*Companion to `Aero-PRD-v0.2.md` and `Aero-Implementation-Plan.md`. New ID families: `AERO-PRES-*` (presence/avatar), `AERO-APP-*` (control app), `AERO-BRAIN-*`, `AERO-VOX-4xx`, `AERO-ACT-*`, `AERO-VIS-6xx`, `AERO-PLAY-*`, `AERO-BODY-*`. Spikes S-5..S-12 continue S-1..S-4.*
