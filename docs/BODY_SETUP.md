# Body — the same Aero, on a platform or a robot (M15 / AERO-BODY-8xx)

Pillar 8 of v0.3. Aero's core is portable Python; Body is the abstraction that
lets the *same* Aero — same persona, memory, voice, and face — run as a desktop
overlay today and on a Raspberry Pi robot tomorrow. Platform-specific bits sit
behind ports; the core never touches them.

```
aero body status            # what am I running on? robot? hardware?
aero body pi-preset         # configure the brain for a constrained board
aero body install-service   # a systemd unit so Aero autostarts headless
```

## Platform ports (AERO-BODY-801)

`detect_host()` classifies the machine — **windows / linux-desktop / linux-arm
(Pi) / headless** — from `sys.platform`, CPU arch, and `$DISPLAY`/`$WAYLAND_DISPLAY`.
The daemon then asks the Host what to use, so the code is identical everywhere:

- **perception**: `host_tier0_sample()` dispatches active-window sensing — Windows
  ctypes, Linux xdotool (optional), headless → nothing. This is the fix for
  `tier0.py` having been Windows-only.
- **voice default**: SAPI on Windows, Kokoro/Piper on Linux/Pi.
- Every path degrades safely — no xdotool, no display, no crash.

## Hardware I/O (AERO-BODY-803)

`HardwareIO` is one interface for servos (head turn), LEDs (mood), and a
display-face. **Absent hardware just no-ops** — the same code runs a full robot, a
face-on-a-screen, or a bare desktop:

- `NullHardware` — desktop/headless default (no-op).
- `GpioHardware` — real Pi via gpiozero (import-guarded; off-Pi → unavailable).
- `build_hardware(host)` picks GPIO only on a capable ARM board.

`apply_avatar_state()` maps the M9 avatar onto the body: emotion → mood LED colour,
listening/speaking → head faces you, and the display-face mirrors the overlay.

Install on a Pi: `pip install -e ".[camera]"` (Pillow/OpenCV) plus `gpiozero`, then
wire `GpioHardware`'s pins for your specific robot.

## One puppet, two faces (AERO-BODY-805)

The desktop overlay and the robot's display are the *same* rig, fed the same
`AvatarState` stream. `FaceOutput` is the last inch:

- `OverlayFace` → forwards the state JSON to the desktop overlay (Pillar 1).
- `DisplayFace` → mirrors the frame on a Pi screen + expresses it on hardware.

`build_face()` picks the display-face when the hardware has a screen. Swapping face
changes nothing upstream — same state machine, same lip-sync, same manifest.

## The Pi brain (AERO-BODY-802/804)

A constrained board runs a **small local reflex model + a LAN/cloud brain for the
hard stuff** — and that's just the M8 two-speed router, not a fork:

```
aero body pi-preset     # reflex=local, primary=litellm
# then point the litellm profile at your brain host (a LAN desktop / cloud)
```

`RobotProfile` (from `settings.robot`) records whether Aero is a robot, the
platform, and which hardware is present.

## Autostart (headless)

"Aero lives here" means he's always on. Generate a systemd user unit:

```bash
mkdir -p ~/.config/systemd/user
aero body install-service > ~/.config/systemd/user/aero.service
systemctl --user enable --now aero
```

## Status

The whole software side of Body is built and tested: host detection (verified
classifying this Ubuntu box as linux-desktop), hardware interface + backends, the
shared face rig, robot profile, Pi brain preset, and the autostart unit. The
remaining piece is **on-device latency** — spike S-8 (`spikes/S8_NOTES.md`) — which
needs a real Pi to run; the preset already encodes the expected answer
(local reflex + LAN/cloud chat).
