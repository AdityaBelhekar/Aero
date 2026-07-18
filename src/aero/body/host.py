"""Host detection + per-platform perception/voice defaults (AERO-BODY-801).

The core is portable; the edges weren't. This resolves that: detect what we're
running on and hand back the right Tier-0 sampler and voice default, so the daemon
code is identical on every platform and just asks the Host what to use.

  Windows        -> ctypes window hooks (perception.tier0), SAPI voice
  Linux desktop  -> xdotool active-window (optional), Kokoro/Piper voice
  Linux ARM (Pi) -> same Linux perception, Piper voice, hardware I/O available
  headless       -> no window sensing (Tier0Sample ok=False), no display

Every path degrades safely: no xdotool / no $DISPLAY -> a headless sample, never a
crash. This is the concrete fix for tier0.py being Windows-only.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from enum import Enum

from aero.perception.tier0 import Tier0Sample


class HostKind(str, Enum):
    WINDOWS = "windows"
    MACOS = "macos"
    LINUX_DESKTOP = "linux-desktop"
    LINUX_ARM = "linux-arm"        # Raspberry Pi / Jetson-class
    HEADLESS = "headless"          # Linux with no display (server / SSH / CI)


@dataclass(frozen=True)
class Host:
    kind: HostKind
    os: str                 # "windows" | "macos" | "linux"
    arch: str               # machine arch, e.g. "x86_64", "aarch64"
    has_display: bool
    is_arm: bool

    @property
    def default_tts(self) -> str:
        if self.os == "windows":
            return "sapi"
        return "kokoro"     # CPU-friendly on Linux/Pi (Piper also fine)

    @property
    def can_sense_windows(self) -> bool:
        """Whether active-window/Tier-0 sensing is possible here."""
        return self.kind in (HostKind.WINDOWS, HostKind.LINUX_DESKTOP, HostKind.LINUX_ARM)

    @property
    def hardware_capable(self) -> bool:
        """ARM boards are where servos/LEDs/GPIO live."""
        return self.is_arm

    def to_dict(self) -> dict:
        return {"kind": self.kind.value, "os": self.os, "arch": self.arch,
                "has_display": self.has_display, "is_arm": self.is_arm,
                "default_tts": self.default_tts,
                "can_sense_windows": self.can_sense_windows,
                "hardware_capable": self.hardware_capable}


def _has_display(env: dict) -> bool:
    return bool(env.get("DISPLAY") or env.get("WAYLAND_DISPLAY"))


def detect_host(*, platform: str | None = None, machine: str | None = None,
                env: dict | None = None) -> Host:
    """Detect the host. Args are injectable so every branch is testable without
    actually being on that platform."""
    platform = platform or sys.platform
    machine = (machine or os.uname().machine if hasattr(os, "uname")
               else machine or "").lower() if machine is None else machine.lower()
    env = os.environ if env is None else env

    if platform.startswith("win"):
        return Host(HostKind.WINDOWS, "windows", machine or "x86_64",
                    has_display=True, is_arm=False)
    if platform == "darwin":
        return Host(HostKind.MACOS, "macos", machine or "arm64",
                    has_display=True, is_arm="arm" in (machine or ""))

    # linux (and anything else) ...
    is_arm = any(tag in (machine or "") for tag in ("arm", "aarch64"))
    display = _has_display(env)
    if not display:
        return Host(HostKind.HEADLESS, "linux", machine or "unknown",
                    has_display=False, is_arm=is_arm)
    kind = HostKind.LINUX_ARM if is_arm else HostKind.LINUX_DESKTOP
    return Host(kind, "linux", machine or "x86_64", has_display=True, is_arm=is_arm)


# -- Linux active-window sampler (xdotool; optional) -----------------------
def _xdotool_sample() -> Tier0Sample:
    """Active window title + process via xdotool/ps, or headless if unavailable.
    (X11; a Wayland portal-based sampler is a future backend behind this same
    function.)"""
    if not shutil.which("xdotool"):
        return Tier0Sample(ok=False)
    try:
        win = subprocess.run(["xdotool", "getactivewindow"],
                             capture_output=True, text=True, timeout=1.0)
        wid = win.stdout.strip()
        if not wid:
            return Tier0Sample(ok=False)
        title = subprocess.run(["xdotool", "getwindowname", wid],
                               capture_output=True, text=True, timeout=1.0).stdout.strip()
        proc = None
        pidr = subprocess.run(["xdotool", "getwindowpid", wid],
                              capture_output=True, text=True, timeout=1.0).stdout.strip()
        if pidr:
            comm = subprocess.run(["ps", "-p", pidr, "-o", "comm="],
                                  capture_output=True, text=True, timeout=1.0)
            proc = comm.stdout.strip() or None
        return Tier0Sample(window_title=title or None, process_name=proc,
                           idle_seconds=0.0)
    except (subprocess.SubprocessError, OSError):
        return Tier0Sample(ok=False)


def host_tier0_sample(host: Host | None = None) -> Tier0Sample:
    """Sample Tier-0 world state using the right backend for the host. This is the
    platform-portable replacement for calling tier0.sample_tier0() directly."""
    host = host or detect_host()
    if host.kind is HostKind.WINDOWS:
        from aero.perception.tier0 import sample_tier0
        return sample_tier0()
    if host.kind in (HostKind.LINUX_DESKTOP, HostKind.LINUX_ARM):
        return _xdotool_sample()
    return Tier0Sample(ok=False)   # headless / macos-unsupported
