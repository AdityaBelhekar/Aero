"""Spectator — watch & react, never touch the game (AERO-PLAY-704).

For games where automating would be cheating (competitive titles), Aero is a
spectator: he *sees* the screen through Eyes (M13) and reacts like a friend on the
couch — hype, a roast, a quiet "...okay that was clean" — but sends zero input to
the game. There is no ``act`` here at all; the only capability is looking, and that
already needs the ``screen`` grant. This is the safe way to be present in a game
Aero must not play.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Commentary:
    ok: bool
    text: str = ""
    reason: str = ""

    def to_dict(self) -> dict:
        return {"ok": self.ok, "text": self.text, "reason": self.reason}


class Spectator:
    def __init__(self, eyes, vision_router, *, game: str = "the game"):
        self.eyes = eyes
        self.vision = vision_router
        self.game = game

    def _prompt(self, extra: str | None) -> str:
        base = (f"You're watching {self.game} with Aditya, like a friend on the "
                "couch. React in ONE short line — hype him up, roast a bad play, "
                "or a dry comment. Casual, code-switch Hindi/Marathi/English is "
                "fine. Never coach in a try-hard way.")
        return f"{base} {extra}" if extra else base

    def watch(self, extra_prompt: str | None = None) -> Commentary:
        """Capture the game screen and comment. Never sends input to the game."""
        look = self.eyes.look("screen")
        if not look.ok:
            return Commentary(ok=False,
                              reason=f"can't see the screen: {look.reason}")
        answer = self.vision.see(look.frame, self._prompt(extra_prompt))
        if not answer.ok:
            return Commentary(ok=False, reason=answer.reason)
        return Commentary(ok=True, text=answer.text)
