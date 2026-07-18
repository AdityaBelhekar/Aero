"""Play — Aero games *with* you (v0.3 Pillar 7).

The friend who actually joins in. Two modes, decided per game and enforced
structurally:

  * **play** — where automation is allowed (your own Minecraft LAN world), Aero
    is a game-scoped *actuator*: he sees state, reasons, and acts (mine/build/
    follow/say) under the same consent model as Little Hands (M12).
  * **spectate** — where automating would be cheating (competitive games like
    Valorant), Aero *never touches the game*. He watches through Eyes (M13) and
    reacts/roasts — vision-only commentary, zero input.

The anti-cheat rule is not a suggestion: a spectate-only game refuses every
action at the ``GameSession`` layer, in code, no matter what's granted
(AERO-PLAY-705). Minecraft is first; the ``GameConnector`` interface means it's
not last.
"""

from aero.play.connector import (
    GameAction,
    GameConnector,
    GamePolicy,
    GameSession,
    GameState,
    PlayVerdict,
    game_policy,
)

__all__ = [
    "GameAction",
    "GameConnector",
    "GamePolicy",
    "GameSession",
    "GameState",
    "PlayVerdict",
    "game_policy",
]
