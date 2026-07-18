# Spike S-8 — Pi latency (gates M15 "Body") — NOTES / DEFERRED

**Date:** 2026-07-18
**Status:** OPEN — blocked on real hardware (a Raspberry Pi 5 + mic/speaker/display).
The **software** side of Body (M15) is built and tested: host abstraction, hardware
I/O layer, the shared-rig face output, robot profile, and systemd autostart. This
spike is the on-device latency measurement that decides the Pi's default brain
setup. Framing recorded now so the run is fast when a Pi is on hand.

## Question

Can a Pi run Aero's loop at an acceptable latency, and where does the brain live —
locally, or offloaded to a LAN/cloud machine?

## What to measure (3 days, on a Pi 5)

- **Local reflex brain**: a small model (gemma-class small / Phi-class) via Ollama
  on the Pi — tokens/sec, RAM, first-token latency. Is it usable for reflex + the
  `complete_json` tagging pass?
- **LAN-offloaded brain**: point the `litellm` profile at a LAN desktop / cloud —
  measure round-trip vs. local. `apply_pi_brain_preset()` already wires exactly
  this (reflex=local, primary=litellm), so the spike is a measurement, not new code.
- **Voice loop**: Piper/Kokoro TTS + Whisper/Moonshine STT on the Pi — is the
  round-trip within the PRD §24 budget? Moonshine (pure ONNX, no torch) is the
  likely STT pick on ARM.
- **Presence**: the avatar rig on the attached display-face — idle CPU %, frame
  rate. Same rendering question as S-11 (web vs Godot), now on ARM.
- **Hardware I/O**: servo/LED latency via gpiozero (fill in `GpioHardware`'s pin
  wiring for the specific robot).

## Expected outcome (hypothesis)

Per R-13: local-only likely misses latency for anything hard, so the **documented
Pi default is `apply_pi_brain_preset` — a small local reflex model + a LAN/cloud
brain** for chat. The two-speed router (M8) makes this a settings choice. Confirm
the numbers, then write `S8_VERDICT.md` and set the default.

## What's already in place (no Pi needed)

- `body.host.detect_host()` classifies `linux-arm`; `default_tts`/`hardware_capable`
  switch correctly.
- `body.hardware` — interface + Null/Mock/GPIO backends; `build_hardware` picks
  GPIO only on a capable board.
- `body.face` — the same `AvatarState` renders to a desktop overlay or a Pi
  display-face (AERO-BODY-805).
- `body.robot` — `RobotProfile`, `apply_pi_brain_preset`, `systemd_unit` for
  autostart.

## Status: DEFERRED — software complete, on-device latency verdict pending a Pi.
