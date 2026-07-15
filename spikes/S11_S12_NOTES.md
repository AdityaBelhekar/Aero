# Spikes S-11 (avatar render stack) & S-12 (lip-sync) — NOTES / DEFERRED

**Date:** 2026-07-15
**Status:** OPEN — blocked on (a) a real display to test transparency/always-on-top
and (b) Aditya's authored 3D model + animation clips. The **puppeteer** side (the
presence core: state machine, emotion map, ambient scheduler, driver — M9.1–M9.3)
is built and tested; these two spikes are the **puppet + rendering** side.

Recording the decision framing now so the live spike is fast when unblocked.

---

## S-11 — Avatar render stack (gates the overlay)

**Question:** what renders a transparent, always-on-top, click-through window
showing an animated glTF/GLB, cheaply, all day?

**Two honest options** (per v0.3 §Pillar 1):

| | Web: Tauri + Three.js / react-three-fiber | Godot (transparent window) |
|---|---|---|
| Transparency + always-on-top + click-through | Tauri window flags; well-trodden | supported; per-platform flags |
| Animation tooling / blending | decent (Three AnimationMixer) | **best** — built for this |
| Shipping ease | **easiest**, one webview | heavier runtime |
| Path to the robot face (Pillar 8) | re-render on device | **closer** (same engine on the Pi display) |
| Idle CPU/RAM (all-day budget) | must measure | must measure |

**Bias:** web (Tauri + Three.js) for shipping speed + transparency, *unless*
animation authoring/blending quality pushes to Godot. glTF/GLB is the interchange
format either way, so the manifest + `AvatarState` contract (already built) don't
change with the choice.

**What the live spike must measure (3 days):** transparency + always-on-top +
click-through actually work on Aditya's Ubuntu (Wayland vs X11 matters here);
animation blending between states looks smooth; **idle cost is low single-digit %
CPU + modest RAM** (he's on screen all day — budget gate, v0.3 §6). Feed it real
`AvatarState` JSON from `PresenceDriver` over the IPC.

**Ubuntu note:** transparency/always-on-top/click-through behave differently under
Wayland (Ubuntu 26.04 default) vs X11 — test the actual session type. This wasn't a
concern on the old Windows box; it is now.

## S-12 — Lip-sync (gates believable speaking)

**Question:** drive a mouth blendshape from live TTS audio.

**Plan:** simplest reliable path first — amplitude/viseme analysis of the TTS
audio stream → `AvatarState.mouth_open` (0..1) per frame → the blendshape named in
the rig's `lipsync.blendshape`. If the active TTS engine emits phoneme/viseme
timing, prefer that (crisper) and carry it in `AvatarState.viseme`.

**Already in place:** the contract — `PresenceDriver.tick(mouth_open=...)` and
`AvatarState.mouth_open` / `.viseme`. The spike only has to *produce* the amplitude
from audio and confirm it looks right across the voice engines (Kokoro/Svara/Parler,
and any cloud TTS from M11), which is why it pairs with the Voice Marketplace.

**Must work across engines** (Pillar 4): whatever voice is active, lip-sync reads
its audio. Streaming engines (first-audio-out fast) keep the mouth moving as sound
starts.

---

## When unblocked

1. Aditya authors a minimal rig (idle + 3–4 fidgets + listen/think/talk + a couple
   actions) and a `aero.rig.json` (format: `docs/PRESENCE_SETUP.md`).
2. Run S-11: stand up the overlay in the chosen stack, render the GLB, pipe
   `PresenceDriver` state over IPC, measure idle cost on Ubuntu (check Wayland/X11).
3. Run S-12: extract `mouth_open` from the live TTS audio; verify sync.
4. Write verdicts (`S11_VERDICT.md`, `S12_VERDICT.md`); wire the overlay as a thin
   IPC client of the daemon.
