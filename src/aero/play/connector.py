"""GameConnector interface + per-game consent/anti-cheat policy (AERO-PLAY-701/705).

``GameConnector`` is the swappable seam (Minecraft first, others later): join a
game, observe its state, act on it, leave. ``GamePolicy`` decides whether Aero may
*act* in a given game at all — the anti-cheat boundary. ``GameSession`` ties a
connector to its policy and the consent model, and is the only place actions are
allowed through, so the play/spectate rule and the ``games`` grant can't be
sidestepped.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum

from aero import settings as st
from aero.config import Config


class GameMode(str, Enum):
    PLAY = "play"          # automation allowed (your own world)
    SPECTATE = "spectate"  # vision-only; automating would be cheating


@dataclass
class GameState:
    """A snapshot of the shared game situation Aero reasons over."""

    game: str
    connected: bool = False
    position: tuple[float, float, float] | None = None
    health: float | None = None
    inventory: list[dict] = field(default_factory=list)
    entities: list[dict] = field(default_factory=list)
    chat: list[str] = field(default_factory=list)
    raw: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {"game": self.game, "connected": self.connected,
                "position": list(self.position) if self.position else None,
                "health": self.health, "inventory": self.inventory,
                "entities": self.entities, "chat": self.chat}


@dataclass
class GameAction:
    """One thing Aero wants to do in-game (mine/build/follow/say/...)."""

    kind: str
    args: dict = field(default_factory=dict)


@dataclass
class GamePolicy:
    """Per-game rules. ``mode`` is the anti-cheat boundary; competitive games are
    spectate-only and can never be flipped to play by a grant."""

    game: str
    mode: GameMode
    note: str = ""

    @property
    def can_automate(self) -> bool:
        return self.mode is GameMode.PLAY


# Built-in policies. Minecraft (your own world) = play; competitive titles =
# spectate-only. Unknown games default to SPECTATE (fail safe — never auto-act on
# a game we don't have an explicit play policy for).
_POLICIES: dict[str, GamePolicy] = {
    "minecraft": GamePolicy("minecraft", GameMode.PLAY,
                            "your own LAN world — automation is fine"),
    "valorant": GamePolicy("valorant", GameMode.SPECTATE,
                           "competitive — watch & roast only, never automate"),
    "csgo": GamePolicy("csgo", GameMode.SPECTATE, "competitive — spectate only"),
    "cs2": GamePolicy("cs2", GameMode.SPECTATE, "competitive — spectate only"),
}


def game_policy(game: str) -> GamePolicy:
    """The policy for a game — defaulting to SPECTATE (fail safe) if unknown."""
    return _POLICIES.get(game.lower(),
                         GamePolicy(game.lower(), GameMode.SPECTATE,
                                    "unknown game — spectate-only by default"))


def known_games() -> list[GamePolicy]:
    """All games with an explicit policy (for the Control App / `aero play`)."""
    return list(_POLICIES.values())


class GameConnector(ABC):
    game: str

    @abstractmethod
    def join(self, **kwargs) -> GameState:
        ...

    @abstractmethod
    def observe(self) -> GameState:
        ...

    @abstractmethod
    def act(self, action: GameAction) -> dict:
        """Perform an action. NEVER call directly — go through GameSession so the
        policy + consent apply."""

    @abstractmethod
    def leave(self) -> None:
        ...


class PlayVerdict(str, Enum):
    OK = "ok"
    REFUSED_SPECTATE = "refused_spectate"   # game is spectate-only (anti-cheat)
    REFUSED_UNGRANTED = "refused_ungranted"  # 'games' scope not granted / kill switch


@dataclass
class ActResult:
    verdict: PlayVerdict
    reason: str
    result: dict | None = None

    @property
    def ok(self) -> bool:
        return self.verdict is PlayVerdict.OK

    def to_dict(self) -> dict:
        return {"verdict": self.verdict.value, "reason": self.reason,
                "result": self.result}


class GameSession:
    """A connector + its policy + the consent model. The only path an in-game
    action runs — so play/spectate and the ``games`` grant always apply."""

    def __init__(self, connector: GameConnector, *, cfg: Config | None = None,
                 settings=None):
        self.connector = connector
        self.policy = game_policy(connector.game)
        self.cfg = cfg or Config.load()
        self._settings = settings

    def _load(self):
        return self._settings if self._settings is not None else st.load(self.cfg)

    def observe(self) -> GameState:
        return self.connector.observe()

    def act(self, action: GameAction) -> ActResult:
        # 1. anti-cheat: spectate-only games never act, whatever is granted.
        if not self.policy.can_automate:
            return ActResult(PlayVerdict.REFUSED_SPECTATE,
                             f"{self.connector.game} is spectate-only "
                             f"({self.policy.note}); Aero watches, never plays it")
        # 2. consent: the 'games' scope must be granted (kill switch forces off).
        if not st.permission_granted(self._load(), "games"):
            return ActResult(PlayVerdict.REFUSED_UNGRANTED,
                             "permission 'games' is not granted")
        # 3. approved.
        return ActResult(PlayVerdict.OK, "action performed",
                         result=self.connector.act(action))
