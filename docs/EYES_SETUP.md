# Eyes — Aero reacting to what's on screen (M13 / AERO-VIS-6xx)

Pillar 6 of v0.3. Vision exists so Aero can *react like a friend in the room* —
see the game, the meme, the error, and comment ("we are NOT bottom-fragging
again"). It is **off by default**, per-source consented, and frames are
**ephemeral** — held only long enough to be used, never stored unless you ask.

```
aero eyes status                 # sources, grants, availability
aero control perms.grant '{"scope":"screen","on":true}'   # allow screen
aero eyes look                   # capture one frame (gated)
aero eyes describe "what am I doing?"   # capture + ask a vision brain
```

## The tiers (AERO-VIS-002, event-driven)

- **Tier 0 — world state** (already built): active window/process/idle. Tells Aero
  *what* to look at, for free.
- **Tier 1 — screen + OCR**: on a trigger or a Tier-0 event, grab the active
  screen and read its text (RapidOCR, cheap, CPU). The `VisionSampler` only runs
  this when the scene actually changed and not too often, so it stays cheap.
- **Tier 2 — a vision brain**: send the frame to a `supports_vision` brain
  (gpt-4o, gemini-flash) for real understanding — reached only on "Aero look at
  this", a high-salience event, or when OCR wasn't enough.

## Consent & ephemerality (AERO-VIS-604)

- `screen` and `camera` are permission scopes (M10/M12), **default-deny**. No
  grant → no frame is ever captured. The **kill switch** forces both off.
- `Eyes.look()` is the only capture path, so the grant check can't be skipped.
- Frames are `ephemeral=True` — never written to the vault. Only an explicit
  `.keep()` (a "remember this" action, wired later) makes one persistent.
- Camera is **local-only**; a frame is read on demand and the device released.

## Install the capture backends (optional)

Vision degrades to "unavailable" without these — everything (consent, routing,
sampling) still works, it just can't grab a frame.

```bash
pip install -e ".[vision]"      # screen (mss) + Pillow + RapidOCR + numpy
pip install -e ".[camera]"      # + OpenCV for the camera tier
```

**Ubuntu note:** screen capture needs a display. On Wayland (Ubuntu 26.04 default)
mss works under XWayland; a pure-Wayland session may need a portal-based grabber —
that's a backend swap behind the same `Grabber` interface, no other change.

## Choosing the vision brain (AERO-VIS-602)

Vision is a brain capability, not a separate model. The `VisionRouter` picks:
explicit `settings.vision_profile` → the active brain if it sees → the first
vision-capable profile with a key. Set one:

```
aero brain --set-key openai <key>      # gpt-4o sees
aero control brain.set '{"profile":"openai"}'
# or pin a dedicated vision brain in settings.json: "vision_profile": "gemini"
```

Frames leave the device only when you invoke a cloud vision brain — the same
privacy trade-off as any cloud call, and only on an explicit look.

## What's real vs. scaffolded

Complete + tested: the capture interface, consent + ephemerality, scene-change
sampler, OCR interface, and multimodal routing (request shaping + brain
selection, hermetically tested). The **real grabbers** (`mss_screen_grabber`,
`opencv_camera_grabber`) are wired but can't run on a headless box — they report
`available()=False` until there's a display/camera, at which point the same code
path captures for real. No new plumbing needed then, just the deps + a display.
