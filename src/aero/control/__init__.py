"""Control plane — the management API behind the Control App (v0.3 Pillar 2).

The Control App (a Tauri window) and the avatar overlay are both *thin clients
over one headless daemon* (v0.3 §Pillar 2). This package is the daemon-side API
they call: brain manager, voice manager, personality dials, permissions + kill
switch, and the memory browser. It is deliberately transport-agnostic — a single
``ControlService.dispatch(op, params)`` entry point returning JSON-able dicts — so
the same operations work over the local IPC socket (control/ipc.py), the
``aero control`` CLI, or an in-process call from a test. The UI holds no logic;
all of it lives here.
"""

from aero.control.service import ControlError, ControlService

__all__ = ["ControlError", "ControlService"]
