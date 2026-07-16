"""ConsentGate — the structural safety boundary for actions (AERO-ACT-502/503/507).

This is the milestone's whole point: no tool runs unless this gate says so, and
the rules are *code*, not prompt guidance a clever context could talk around.

Decision order (most restrictive first):

  1. **kill switch on**  -> REFUSE everything (the panic-off, AERO-ACT-507).
  2. **scope not granted** -> REFUSE + explain (default-deny, AERO-ACT-502).
  3. **hard-gate or irreversible** -> CONFIRM: needs explicit user confirmation
     even with the scope granted (delete/send/buy/post never go silent —
     AERO-AUTH-002/503). Confirmed -> ALLOW.
  4. **reversible + granted** -> ALLOW (a friend you lent your car still asks
     before selling it, but can move it in the driveway).

Grants + kill switch live in settings (M10) and are read live each evaluation, so
revoking a scope or hitting the kill switch takes effect immediately.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from aero import settings as st
from aero.config import Config
from aero.hands.tool import Tool


class Verdict(str, Enum):
    ALLOW = "allow"        # go ahead
    CONFIRM = "confirm"    # ask the user first (hard-gate / irreversible)
    REFUSE = "refuse"      # not permitted (kill switch / ungranted scope)


@dataclass
class ConsentDecision:
    verdict: Verdict
    reason: str
    tool: str
    scope: str
    #: True when a CONFIRM needs an explicit confirmation to proceed.
    requires_confirmation: bool = False

    @property
    def allowed(self) -> bool:
        return self.verdict is Verdict.ALLOW

    def to_dict(self) -> dict:
        return {"verdict": self.verdict.value, "reason": self.reason,
                "tool": self.tool, "scope": self.scope,
                "requires_confirmation": self.requires_confirmation}


class ConsentGate:
    def __init__(self, cfg: Config | None = None, *, settings=None):
        self.cfg = cfg or Config.load()
        # settings can be injected (tests); else loaded live each evaluate().
        self._settings = settings

    def _load(self):
        return self._settings if self._settings is not None else st.load(self.cfg)

    def evaluate(self, tool: Tool, params: dict | None = None, *,
                 confirmed: bool = False) -> ConsentDecision:
        s = self._load()

        def decide(verdict, reason, need_confirm=False):
            return ConsentDecision(verdict, reason, tool.name, tool.scope,
                                   requires_confirmation=need_confirm)

        # 1. kill switch — nothing acts.
        if s.killswitch:
            return decide(Verdict.REFUSE, "kill switch is on — all actions disabled")

        # 2. default-deny: the scope must be explicitly granted.
        if not st.permission_granted(s, tool.scope):
            return decide(Verdict.REFUSE,
                          f"permission '{tool.scope}' is not granted — grant it in "
                          f"the Control App to allow this")

        # 3. hard-gate / irreversible -> must be confirmed, every time.
        if tool.hard_gate or not tool.reversible:
            kind = "irreversible, high-consequence" if tool.hard_gate else "irreversible"
            if not confirmed:
                return decide(Verdict.CONFIRM,
                              f"'{tool.name}' is {kind}; confirm before it runs",
                              need_confirm=True)
            return decide(Verdict.ALLOW, f"confirmed {kind} action")

        # 4. reversible + granted -> just do it.
        return decide(Verdict.ALLOW, "reversible action within a granted scope")
