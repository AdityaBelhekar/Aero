"""Hardware I/O — servos, LEDs, a display-face (AERO-BODY-803).

On a Pi robot Aero can turn his head (servos), glow a mood (LEDs), and show his
face on a small display. All of it is optional and behind one interface, so a
build with "no servos" simply no-ops — the same code drives a fully-kitted robot,
a face-on-a-screen, or a desktop with no hardware at all.

The avatar's live state (M9) maps straight onto the body: the emotion becomes an
LED colour, the animation state nudges the head (face you when listening). The
screen character and the robot are one puppet, expressed through whatever hardware
is present.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

from aero.presence.state import AnimationState, AvatarState, Emotion


@dataclass(frozen=True)
class HardwareCaps:
    leds: bool = False
    servos: bool = False
    display_face: bool = False


class HardwareIO(ABC):
    @abstractmethod
    def caps(self) -> HardwareCaps:
        ...

    @abstractmethod
    def available(self) -> bool:
        ...

    def set_led(self, rgb: tuple[int, int, int]) -> None:
        """Set the mood LED colour. No-op if no LEDs."""

    def set_head(self, pan: float, tilt: float = 0.0) -> None:
        """Aim the head. pan/tilt in -1..1. No-op if no servos."""

    def show_face(self, state: AvatarState) -> None:
        """Push an avatar frame to the display-face. No-op if none."""


class NullHardware(HardwareIO):
    """No hardware — every method a safe no-op. The desktop/headless default."""

    def caps(self) -> HardwareCaps:
        return HardwareCaps()

    def available(self) -> bool:
        return False


class MockHardware(HardwareIO):
    """Records what it was told to do — for tests and for a robot without the
    real GPIO wired yet. Capabilities are configurable."""

    def __init__(self, *, leds=True, servos=True, display_face=True):
        self._caps = HardwareCaps(leds=leds, servos=servos, display_face=display_face)
        self.led: tuple[int, int, int] | None = None
        self.head: tuple[float, float] | None = None
        self.face: AvatarState | None = None

    def caps(self) -> HardwareCaps:
        return self._caps

    def available(self) -> bool:
        return True

    def set_led(self, rgb):
        if self._caps.leds:
            self.led = rgb

    def set_head(self, pan, tilt=0.0):
        if self._caps.servos:
            self.head = (max(-1.0, min(1.0, pan)), max(-1.0, min(1.0, tilt)))

    def show_face(self, state):
        if self._caps.display_face:
            self.face = state


class GpioHardware(HardwareIO):
    """Real Pi hardware via gpiozero/RPi.GPIO (import-guarded). Off a Pi, or
    without the libs, available() is False and callers fall back to NullHardware.
    The actual pin wiring is a per-robot detail; this is the seam for it."""

    def __init__(self):
        self._ok = self._probe()

    @staticmethod
    def _probe() -> bool:
        try:
            import gpiozero  # noqa: F401
            return True
        except Exception:
            return False

    def caps(self) -> HardwareCaps:
        return HardwareCaps(leds=self._ok, servos=self._ok, display_face=self._ok)

    def available(self) -> bool:
        return self._ok

    # set_led/set_head/show_face would drive real pins here; left as no-ops until
    # a specific robot's wiring is defined (kept off the default path).


def build_hardware(host=None) -> HardwareIO:
    """Best hardware backend for the host: real GPIO on a capable ARM board,
    else NullHardware (no-op) on desktop/headless."""
    from aero.body.host import detect_host
    host = host or detect_host()
    if host.hardware_capable:
        gpio = GpioHardware()
        if gpio.available():
            return gpio
    return NullHardware()


# -- avatar -> body mapping ------------------------------------------------
# Mood LED colour per emotion (RGB 0..255).
_EMOTION_RGB: dict[Emotion, tuple[int, int, int]] = {
    Emotion.NEUTRAL: (40, 40, 50),
    Emotion.HAPPY: (30, 200, 90),
    Emotion.EXCITED: (240, 170, 20),
    Emotion.TEASING: (170, 60, 210),
    Emotion.TIRED: (30, 60, 140),
    Emotion.CONCERNED: (230, 140, 20),
    Emotion.ANNOYED: (210, 40, 40),
}


def emotion_rgb(emotion: Emotion) -> tuple[int, int, int]:
    return _EMOTION_RGB.get(emotion, _EMOTION_RGB[Emotion.NEUTRAL])


def apply_avatar_state(hw: HardwareIO, state: AvatarState) -> None:
    """Express one AvatarState on whatever hardware exists (M9 -> M15). LEDs show
    mood; when listening the head faces you; the display-face mirrors the overlay.
    Missing capabilities silently no-op."""
    hw.set_led(emotion_rgb(state.emotion))
    # Head: face forward when listening/speaking to the user; neutral otherwise.
    if state.animation in (AnimationState.LISTENING, AnimationState.SPEAKING):
        hw.set_head(0.0, 0.0)          # look at the user
    hw.show_face(state)
