# Presence — putting Aero on your screen (M9 / AERO-PRES-1xx)

Pillar 1 of v0.3, the soul of the release: a windowless, transparent,
always-on-top 3D robot who's just *there* — idling with personality, listening,
thinking, talking with lip-sync, reacting to what you're doing.

**You make the body; the code makes it live** (Rule 11). Aditya authors the model
and animation clips; Aero decides which clip plays when. This doc covers the seam
between them — everything that's built and testable today — and points at what
still needs the real model + a display.

## What's built (asset-free, tested)

`src/aero/presence/` — the *puppeteer*. Pure logic, no renderer, runs without any
model:

| Piece | Role |
|---|---|
| `state.AvatarState` | the tiny JSON streamed to the overlay: animation, emotion, clip, one-shot action, lip-sync `mouth_open`, tags |
| `rig.RigManifest` | your clip↔meaning map (see below) |
| `state_machine.AvatarStateMachine` | live signals → animation state (idle/listening/thinking/speaking) + emotion + resolved clip |
| `emotion.emotion_from_intent` | `SpeechIntent` → avatar `Emotion`, in sync with the voice |
| `ambient.AmbientScheduler` | personality-weighted idle fidgets by time-of-day + world state + mood |
| `driver.PresenceDriver` | the one object the daemon ticks; ties it all together |

## The rig manifest (what you author)

A JSON file next to your `model.glb` that says what each clip *means*. Adding a
behaviour = author a clip + add one line. No code change.

```json
{
  "model": "aero.glb",
  "states": {
    "idle":      ["idle_base", "idle_relaxed"],
    "listening": ["listen"],
    "thinking":  ["think"],
    "speaking":  ["talk"]
  },
  "state_emotions": { "speaking": { "happy": "talk_happy", "tired": "talk_tired" } },
  "emotions":  { "happy": "face_happy", "teasing": "face_smirk",
                 "concerned": "face_concern" },
  "fidgets":   ["look_around", "stretch", "glance_at_screen", "bored_sigh"],
  "actions":   { "wave": "act_wave", "facepalm": "act_facepalm",
                 "point_at_screen": "act_point", "dance": "act_dance" },
  "lipsync":   { "blendshape": "mouthOpen" }
}
```

- **states** (required): the four animation states → clip name(s). `idle` can list
  several variants; the ambient scheduler picks among them.
- **state_emotions** (optional): emotion-specific override of a state clip
  (e.g. a happy talking loop). Falls back to the base state clip.
- **emotions** (optional): a facial/pose clip per emotion the renderer blends on
  top of the body animation.
- **fidgets** (optional but recommended): the idle micro-behaviours — this is what
  makes him feel alive. Suggested minimum: `look_around`, `stretch`,
  `glance_at_screen`, `bored_sigh`.
- **actions** (optional): named one-shot clips Aero can trigger on cue.
- **lipsync.blendshape**: the mesh blendshape the overlay drives from `mouth_open`.

Everything is optional with safe fallbacks — a half-authored rig still runs.
`RigManifest.validate()` lists gaps. Until you have a model, a `default_manifest()`
placeholder drives the whole stack (that's what the tests use).

**Minimum clip set for a lively v1:** `idle_base` + 3–4 fidgets + `listen` +
`think` + `talk`, plus a couple of actions (`wave`, `facepalm`). Emotions and
`state_emotions` can come later.

## The state→avatar contract (how it reaches the screen)

The daemon ticks `PresenceDriver` with Aero's live signals and streams the result:

```python
from aero.presence import PresenceDriver
driver = PresenceDriver(RigManifest.load("aero.rig.json"))

state = driver.tick(
    mic_hot=recorder.is_capturing,     # -> LISTENING
    thinking=brain.is_generating,      # -> THINKING
    speaking=tts.is_playing,           # -> SPEAKING + emotion + lip-sync
    intent=current_speech_intent,      # drives the emotion + face
    mouth_open=lipsync_amplitude,      # 0..1 for this audio frame (S-12)
    world=world_provider.last,         # Tier-0: drives idle fidget choice
)
ipc.send(state.to_json())              # overlay renders it; holds no logic
```

Priority is speaking > thinking > listening > idle; only idle consults the ambient
scheduler. The overlay is a **thin client** — it plays the clip named in the state
and drives the lip-sync blendshape; nothing more.

## Not built yet (needs a display + your model)

These are spikes S-11 / S-12 — see `spikes/S11_S12_NOTES.md`:

- **The overlay renderer itself** (transparent always-on-top window rendering the
  glTF). Web (Tauri + Three.js) vs Godot is the S-11 decision.
- **Lip-sync amplitude extraction** from the live TTS audio (S-12) — the code
  above takes `mouth_open` as input; producing it from audio is the spike.

Both need a real display and Aditya's authored assets to evaluate, so they're
deferred until the model exists and we pick the stack.
