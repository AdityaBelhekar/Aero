# Voice Marketplace — how Aero hears and speaks (M11 / AERO-VOX-4xx)

Pillar 4 of v0.3. Aero's ears (STT) and mouth (TTS) are a **catalog of swappable
engines** — mix free/local and paid/cloud, pick per role, and third-party engines
drop in behind the same interface. Same registry pattern as the brain (M8).

```
aero voices --catalog          # browse every STT + TTS engine
aero voices --engine kokoro    # pick a TTS engine
aero voice  --model whisper-small   # pick an STT engine for a session
```

## The catalog

Each engine is a `VoiceProfile` — capability metadata, not code:

| field | meaning |
|---|---|
| `role` | `tts` (mouth) or `stt` (ears) |
| `cost_tier` | `free-local` / `paid` |
| `local` / `private` | runs on-device, no key, nothing leaves the machine |
| `streaming` | emits audio/partials incrementally (keeps the loop snappy + the avatar's mouth moving) |
| `emotion` | TTS acts on `SpeechIntent` affect |
| `languages` | ISO-ish codes it covers |
| `key_env` | env var / keyring entry for the API key |
| `implemented` | is the adapter written yet? |

### Built-in engines

**TTS (mouth):** `kokoro` (fast English, CPU), `svara` (38 Indian voices),
`parler` (code-mix, heavy), `sapi` (Windows placeholder) — all local. Cloud
(adapters pending): `elevenlabs`, `sarvam_tts`, `cartesia`.

**STT (ears):** `whisper-small` (code-switch default), `whisper-turbo` (accurate,
GPU-wants), `moonshine` (fast English, streaming), `indic` (Marathi/NeMo) — all
local. Cloud (pending): `sarvam_stt`, `deepgram`.

Cloud entries are listed with `implemented=false` so the marketplace is honest —
you can see them before their adapter exists. Add your own or override a built-in
via `settings.json → voice_engines` (same shape as `brains`).

## Keys (never on disk)

Cloud voice engines resolve their key **OS-keyring → `key_env` env var**, filed
under a separate `aero-voice` keyring service (brain and voice keys never
collide):

```python
from aero.cognition import keys
keys.set_voice_key("elevenlabs", "el-...")   # keyring
# or:  export ELEVENLABS_API_KEY=el-...
```

Local engines are keyless.

## Fallback chain — degrade, never die (AERO-VOX-404)

Every cloud voice has a local backstop. `build_tts_with_fallback()` /
`FallbackTTS`/`FallbackSTT` wrap the chosen engine: if it's unreachable (server
down, out of credits, no key) or errors mid-call, Aero drops to a local engine
and sets `last_fallback` so the UI can say "cloud voice was down — used local".
Never a hard stall. Same `TTSService`/`STTService` interface, so callers never
know a swap happened.

**Offline test:** turn every cloud engine off and Aero still hears (Whisper) and
speaks (Kokoro/Svara/SAPI) entirely on-device.

## Lip-sync feed (AERO-VOX-403)

The active engine's audio drives the avatar's mouth (M9). `voice/lipsync.py` is an
envelope follower: PCM → per-frame `mouth_open` (0..1) → `PresenceDriver.tick(
speaking=True, mouth_open=...)`.

- **streaming engines:** `LipSync.frame_amplitude(chunk)` per audio chunk as it
  arrives — the mouth moves as sound starts.
- **whole-clip engines:** `envelope_for_wav(path)` gives the whole track.

Stdlib-only (works on any engine's output). If an engine emits phoneme/viseme
timing, that's preferred (crisper) via `AvatarState.viseme`; amplitude is the
always-available default.

## Emotion in sync

`SpeechIntent`'s affective fields drive both the *voice* (on emotion-capable
engines: ElevenLabs, Svara) and the *face* (via `presence/emotion.py`), so what
Aero says, how he says it, and how he looks all move together.

## What's next

The cloud adapters (`elevenlabs`, `sarvam`, `deepgram`, `cartesia`) are catalogued
but not written — each is one new backend implementing `TTSService`/`STTService`,
exactly like the local ones. Bias per the plan: **Sarvam first** (Indic-native,
fits Aero's code-switch identity).
