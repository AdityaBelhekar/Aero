# Aero Real-Time Voice — hands-free, no push-to-talk

The real-time loop is what makes Aero feel like a conversation instead of a
walkie-talkie: it listens continuously, decides on its own when you've finished a
thought (VAD), transcribes, thinks (memory-in-the-loop, two-speed brain), speaks
back (Kokoro), and **stops to listen the moment you talk over it** (barge-in).

```
mic frames -> VAD endpointing -> STT -> agent(+memory) -> TTS -> speakers
                   ^--------------- barge-in watches the mic while speaking
```

## Install

```powershell
python -m pip install -e ".[realtime]"      # sounddevice (live mic)
python -m pip install -e ".[moonshine]"     # fast English ears
python -m pip install -e ".[kokoro]"        # natural voice (see KOKORO_SETUP.md)
# optional, better VAD in noise:
python -m pip install -e ".[realtime_silero]"
```

The default VAD (`EnergyVAD`) is **dependency-free** — the loop runs with just
`sounddevice`. Silero is an optional quality upgrade for noisy rooms.

## Run

```powershell
# recommended English real-time stack:
python -m aero.cli voices --set am_michael          # Kokoro voice
python -m aero.cli voice --realtime --model moonshine
# with the online brain for sub-second replies (see CLOUD_BRAIN_SETUP.md):
python -m aero.cli voice --realtime --model moonshine --brain cloud
```

Just talk. Aero detects when you start and stop, replies, and you can **barge in**
any time — start speaking and it stops to listen.

## Tuning (src/aero/voice/vad.py)

`SegmenterConfig` controls turn-taking feel:
- `start_ms` (150) — how much speech opens a turn (raise to ignore blips).
- `end_silence_ms` (700) — pause length that ends your turn (lower = snappier
  hand-off, higher = more patient / lets you pause mid-thought).
- `preroll_ms` (240) — audio kept from just before you started (avoids clipped
  first words).

`EnergyVAD(threshold=…)` — raise in a noisy room, or call `calibrate()` on a
second of ambient audio. Barge-in sensitivity is `RealtimeLoop(barge_in_ms=…)`.

## Reality on your CPU

Ears (Moonshine) and mouth (Kokoro) are ~realtime on CPU; the pacing limit is the
**brain**. Local gemma4:e4b is ~5–11 s/turn (a thoughtful beat). For instant
back-and-forth use `--brain cloud`. Everything streams, so Aero starts speaking as
soon as the first reply is ready.

## Notes
- Windows: playback + barge-in use `winsound` (async, interruptible).
- No live mic (sounddevice missing)? The loop says so and you can use
  `aero voice` (push-to-talk) instead — nothing crashes.
- Proven (2026-07-11): capture -> VAD endpointing -> Moonshine transcribed a
  synthesized English line verbatim, hands-free.
