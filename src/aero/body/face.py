"""FaceOutput — render the one avatar rig to a face, wherever it lives (AERO-BODY-805).

The desktop overlay and the robot's display are the *same puppet*: both consume
the M9 ``AvatarState`` stream from the daemon. This port is the last inch —
``render(state)`` — with two backends:

  * ``OverlayFace``  — forwards the state JSON to the desktop overlay (Pillar 1).
  * ``DisplayFace``  — a Pi's attached display + body: mirrors the frame to the
                       screen-face and expresses it on the hardware (LED/head).

Same state machine, same lip-sync, same rig manifest — only the last output
changes. Swapping face has no effect on anything upstream.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable

from aero.body.hardware import HardwareIO, NullHardware, apply_avatar_state
from aero.presence.state import AvatarState


class FaceOutput(ABC):
    kind: str

    @abstractmethod
    def render(self, state: AvatarState) -> None:
        ...


class OverlayFace(FaceOutput):
    """Sends the avatar frame to the desktop overlay. ``sink`` is the transport
    (the daemon's IPC push); defaults to a no-op collector for tests."""

    kind = "overlay"

    def __init__(self, sink: Callable[[str], None] | None = None):
        self._sink = sink or (lambda _s: None)
        self.last: AvatarState | None = None

    def render(self, state: AvatarState) -> None:
        self.last = state
        self._sink(state.to_json())


class DisplayFace(FaceOutput):
    """A Pi's screen-face + body. Mirrors the frame and expresses it on hardware."""

    kind = "display-face"

    def __init__(self, hardware: HardwareIO | None = None):
        self.hw = hardware or NullHardware()
        self.last: AvatarState | None = None

    def render(self, state: AvatarState) -> None:
        self.last = state
        apply_avatar_state(self.hw, state)   # display_face + LED + head


def build_face(host=None, *, hardware: HardwareIO | None = None,
               sink: Callable[[str], None] | None = None) -> FaceOutput:
    """Pick the face for the host: a display-face when the hardware has a screen,
    else the desktop overlay. Same AvatarState feeds either."""
    if hardware is not None and hardware.caps().display_face:
        return DisplayFace(hardware)
    return OverlayFace(sink)
