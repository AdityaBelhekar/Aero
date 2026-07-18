"""Robot profile + ARM daemon autostart (AERO-BODY-802/804).

A ``RobotProfile`` is the typed view over ``settings.robot`` — is Aero a robot,
on what platform, with what hardware. Plus the two things a Pi build needs beyond
the desktop: a **brain routing preset** (a compute-constrained board runs a small
local reflex model + a LAN/cloud brain — a settings choice, not a fork, thanks to
the M8 router) and **autostart** (a systemd unit so Aero comes up at boot, headless).
"""

from __future__ import annotations

from dataclasses import dataclass

from aero import settings as st
from aero.body.hardware import HardwareCaps
from aero.config import Config


@dataclass(frozen=True)
class RobotProfile:
    enabled: bool
    platform: str          # "auto" | "pi" | ...
    hardware: HardwareCaps

    @classmethod
    def from_settings(cls, s: st.VoiceSettings) -> "RobotProfile":
        r = s.robot or {}
        hw = r.get("hardware") or {}
        return cls(
            enabled=bool(r.get("enabled", False)),
            platform=r.get("platform", "auto"),
            hardware=HardwareCaps(
                leds=bool(hw.get("leds", False)),
                servos=bool(hw.get("servos", False)),
                display_face=bool(hw.get("display_face", False)),
            ),
        )

    def to_dict(self) -> dict:
        return {"enabled": self.enabled, "platform": self.platform,
                "hardware": {"leds": self.hardware.leds,
                             "servos": self.hardware.servos,
                             "display_face": self.hardware.display_face}}


def apply_pi_brain_preset(s: st.VoiceSettings) -> st.VoiceSettings:
    """A Pi runs a small local reflex brain + a bigger LAN/cloud brain for the
    hard stuff (AERO-BODY / R-13). This is just the M8 two-speed router configured
    for constrained hardware — reflex/tagging stays local, chat routes out."""
    s.reflex_profile = "local"
    s.primary_profile = "litellm"      # point the LiteLLM proxy at a LAN/cloud brain
    return s


# -- systemd autostart (Linux/ARM) -----------------------------------------
def systemd_unit(*, exec_start: str = "aero daemon",
                 aero_home: str | None = None,
                 description: str = "Aero companion daemon") -> str:
    """Generate a systemd user-service unit so the daemon autostarts at login/boot
    — the 'Aero lives here' requirement, headless on a Pi. Install with:
        mkdir -p ~/.config/systemd/user
        aero body install-service > ~/.config/systemd/user/aero.service
        systemctl --user enable --now aero
    """
    env = f"Environment=AERO_HOME={aero_home}\n" if aero_home else ""
    return (
        "[Unit]\n"
        f"Description={description}\n"
        "After=network-online.target\n"
        "Wants=network-online.target\n\n"
        "[Service]\n"
        "Type=simple\n"
        f"{env}"
        f"ExecStart={exec_start}\n"
        "Restart=on-failure\n"
        "RestartSec=5\n\n"
        "[Install]\n"
        "WantedBy=default.target\n"
    )


def robot_status(cfg: Config | None = None) -> dict:
    """Combined body status: host + robot profile + effective hardware."""
    from aero.body.hardware import build_hardware
    from aero.body.host import detect_host
    host = detect_host()
    profile = RobotProfile.from_settings(st.load(cfg))
    hw = build_hardware(host)
    return {"host": host.to_dict(), "robot": profile.to_dict(),
            "hardware_available": hw.available(),
            "hardware_caps": {"leds": hw.caps().leds, "servos": hw.caps().servos,
                              "display_face": hw.caps().display_face}}
