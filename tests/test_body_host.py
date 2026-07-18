"""Host detection + platform Tier-0 (AERO-BODY-801). Hermetic — platform injected."""

from __future__ import annotations

from aero.body.host import HostKind, detect_host, host_tier0_sample


def test_detect_windows():
    h = detect_host(platform="win32", machine="AMD64", env={})
    assert h.kind is HostKind.WINDOWS and h.os == "windows"
    assert h.default_tts == "sapi" and not h.is_arm
    assert h.can_sense_windows


def test_detect_linux_desktop():
    h = detect_host(platform="linux", machine="x86_64", env={"DISPLAY": ":0"})
    assert h.kind is HostKind.LINUX_DESKTOP
    assert h.default_tts == "kokoro" and h.has_display
    assert not h.hardware_capable


def test_detect_linux_arm_pi():
    h = detect_host(platform="linux", machine="aarch64", env={"DISPLAY": ":0"})
    assert h.kind is HostKind.LINUX_ARM
    assert h.is_arm and h.hardware_capable
    assert h.default_tts == "kokoro"


def test_detect_headless():
    h = detect_host(platform="linux", machine="x86_64", env={})   # no DISPLAY
    assert h.kind is HostKind.HEADLESS
    assert not h.has_display and not h.can_sense_windows


def test_detect_arm_headless_still_arm():
    h = detect_host(platform="linux", machine="aarch64", env={})
    assert h.kind is HostKind.HEADLESS and h.is_arm  # a Pi over SSH


def test_wayland_counts_as_display():
    h = detect_host(platform="linux", machine="x86_64", env={"WAYLAND_DISPLAY": "wayland-0"})
    assert h.has_display and h.kind is HostKind.LINUX_DESKTOP


def test_macos():
    h = detect_host(platform="darwin", machine="arm64", env={})
    assert h.kind is HostKind.MACOS and h.is_arm


def test_host_serialises():
    d = detect_host(platform="linux", machine="aarch64", env={"DISPLAY": ":0"}).to_dict()
    assert d["kind"] == "linux-arm" and d["hardware_capable"] is True


# -- platform Tier-0 dispatch ----------------------------------------------
def test_headless_tier0_is_unavailable():
    h = detect_host(platform="linux", machine="x86_64", env={})
    sample = host_tier0_sample(h)
    assert sample.ok is False           # no window sensing headless, no crash


def test_linux_tier0_degrades_without_xdotool(monkeypatch):
    monkeypatch.setattr("aero.body.host.shutil.which", lambda x: None)  # no xdotool
    h = detect_host(platform="linux", machine="x86_64", env={"DISPLAY": ":0"})
    assert host_tier0_sample(h).ok is False


def test_linux_tier0_reads_xdotool(monkeypatch):
    monkeypatch.setattr("aero.body.host.shutil.which", lambda x: "/usr/bin/xdotool")

    class R:
        def __init__(self, out): self.stdout = out
    outputs = {"getactivewindow": "12345", "getwindowname": "main.py - VSCode",
               "getwindowpid": "999", "comm=": "code"}

    def fake_run(cmd, **kw):
        if cmd[0] == "ps":
            return R("code\n")
        return R(outputs.get(cmd[1], "") + "\n")

    monkeypatch.setattr("aero.body.host.subprocess.run", fake_run)
    h = detect_host(platform="linux", machine="x86_64", env={"DISPLAY": ":0"})
    sample = host_tier0_sample(h)
    assert sample.ok and sample.window_title == "main.py - VSCode"
    assert sample.process_name == "code"
