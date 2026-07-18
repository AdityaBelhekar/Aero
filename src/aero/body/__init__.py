"""Body — the same Aero, now with a platform and (optionally) a physical form
(v0.3 Pillar 8).

Aero's core is portable Python; what wasn't portable were the OS-specific edges —
Windows ctypes window hooks, SAPI voice — and the assumption of a screen. This
package is the abstraction that lets the *same* Aero run as a desktop overlay
today and on a Raspberry Pi robot tomorrow:

  * ``host``     — detect the host (Windows / Linux desktop / Linux ARM / headless)
                   and pick the right perception + voice defaults per platform.
  * ``hardware`` — an optional hardware I/O layer (servos, LEDs, display-face);
                   absent hardware simply no-ops.
  * ``face``     — render the M9 avatar rig to a face output: a desktop overlay or
                   a Pi display. The screen character and the robot are one puppet.
  * ``robot``    — a robot profile + ARM daemon autostart (systemd).

Platform-specific bits sit behind these ports; the core never imports them
directly. "Presence is portable" (Rule 10).
"""

from aero.body.host import Host, HostKind, detect_host, host_tier0_sample

__all__ = ["Host", "HostKind", "detect_host", "host_tier0_sample"]
