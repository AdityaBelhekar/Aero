"""Tier-0 perception: foreground window, process, and input-idle.

Windows-only sensing via ctypes (no third-party deps). On any other platform the
sampler degrades to an empty sample so the rest of Aero — and CI — runs fine.

Nothing here captures pixels or content; it reads window *titles* and process
*names* and an idle timer. That's the cheap, always-on signal the world state is
built from (AERO-WS-001). Screen content is a later, budgeted tier.
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field

_IS_WINDOWS = sys.platform == "win32"

if _IS_WINDOWS:
    import ctypes
    from ctypes import wintypes

    _user32 = ctypes.windll.user32
    _kernel32 = ctypes.windll.kernel32

    class _LASTINPUTINFO(ctypes.Structure):
        _fields_ = [("cbSize", wintypes.UINT), ("dwTime", wintypes.DWORD)]


@dataclass
class Tier0Sample:
    """One instantaneous read of the digital environment."""

    window_title: str | None = None
    process_name: str | None = None   # e.g. "chrome.exe"
    idle_seconds: float = 0.0
    ok: bool = True                   # False if sensing unavailable (non-Windows)

    @property
    def active(self) -> bool:
        """User considered active if they touched input in the last 60s."""
        return self.idle_seconds < 60.0

    @property
    def activity_level(self) -> str:
        if self.idle_seconds < 60:
            return "active"
        if self.idle_seconds < 300:
            return "idle"
        return "away"


def _foreground_title(hwnd) -> str | None:
    length = _user32.GetWindowTextLengthW(hwnd)
    if length <= 0:
        return None
    buf = ctypes.create_unicode_buffer(length + 1)
    _user32.GetWindowTextW(hwnd, buf, length + 1)
    return buf.value or None


def _process_name_for_hwnd(hwnd) -> str | None:
    pid = wintypes.DWORD()
    _user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    if not pid.value:
        return None
    PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
    handle = _kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid.value)
    if not handle:
        return None
    try:
        size = wintypes.DWORD(260)
        buf = ctypes.create_unicode_buffer(size.value)
        if _kernel32.QueryFullProcessImageNameW(handle, 0, buf, ctypes.byref(size)):
            return os.path.basename(buf.value)
    finally:
        _kernel32.CloseHandle(handle)
    return None


def _idle_seconds() -> float:
    info = _LASTINPUTINFO()
    info.cbSize = ctypes.sizeof(_LASTINPUTINFO)
    if not _user32.GetLastInputInfo(ctypes.byref(info)):
        return 0.0
    millis = _kernel32.GetTickCount() - info.dwTime
    return max(millis, 0) / 1000.0


def sample_tier0() -> Tier0Sample:
    """Read the current foreground window, its process, and idle time."""
    if not _IS_WINDOWS:
        return Tier0Sample(ok=False)
    try:
        hwnd = _user32.GetForegroundWindow()
        title = _foreground_title(hwnd) if hwnd else None
        proc = _process_name_for_hwnd(hwnd) if hwnd else None
        return Tier0Sample(
            window_title=title,
            process_name=proc,
            idle_seconds=_idle_seconds(),
        )
    except Exception:
        # Sensing must never crash the companion; degrade to unknown.
        return Tier0Sample(ok=False)


# -- app-switch detection + world-state feed --------------------------------
@dataclass
class WorldStateProvider:
    """Turns Tier-0 samples into world-state fields and notices app switches.

    The provider holds the last sample so callers can detect a *change* of active
    app (a significant world-state delta, AERO-RET-002) — the signal that later
    wakes proactive cognition. For Milestone 2 it just enriches the chat world
    state and can log switches as raw events for consolidation.
    """

    last: Tier0Sample | None = field(default=None)

    def poll(self) -> tuple[Tier0Sample, bool]:
        """Return (sample, app_switched)."""
        cur = sample_tier0()
        switched = False
        if cur.ok:
            prev_proc = self.last.process_name if self.last else None
            if self.last is not None and cur.process_name != prev_proc:
                switched = True
        self.last = cur
        return cur, switched
