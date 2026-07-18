"""Voice + game + avatar fusion (AERO-PLAY-703) — the magic moment.

You're in the world, you say something, and Aero *answers and acts and his face
reacts*, all at once. This orchestrator ties the pieces built across the plan:

    GameSession (M14)  -> observe state, act in-game (gated)
    brain (M8)         -> what to say (and, when asked, does he act)
    SpeechIntent (M3)  -> delivery
    PresenceDriver (M9)-> the avatar speaks + emotes in sync
    TTS (M11, optional)-> the voice

Every in-game action still goes through ``GameSession`` (policy + ``games`` grant),
so fusion can't act where it shouldn't. Talking + emoting are always fine; acting
is gated.
"""

from __future__ import annotations

from dataclasses import dataclass

from aero.cognition.service import ChatMessage
from aero.play.connector import ActResult, GameAction, GameSession
from aero.presence.state import AvatarState
from aero.voice.speech_intent import SpeechIntent, intent_from_text


@dataclass
class FusionResult:
    text: str                       # what Aero said
    avatar: AvatarState             # the frame the overlay should render
    in_game_said: bool = False      # was it also posted to in-game chat?
    action: ActResult | None = None  # result of an in-game action, if any
    spoke: bool = False             # did TTS play it?

    def to_dict(self) -> dict:
        return {"text": self.text, "avatar": self.avatar.to_dict(),
                "in_game_said": self.in_game_said, "spoke": self.spoke,
                "action": self.action.to_dict() if self.action else None}


def _state_summary(state) -> str:
    bits = []
    if state.health is not None:
        bits.append(f"health {state.health}")
    if state.position:
        bits.append("at " + ",".join(str(round(c)) for c in state.position))
    if state.entities:
        bits.append(f"{len(state.entities)} entities near")
    if state.inventory:
        bits.append(f"{len(state.inventory)} item stacks")
    return "; ".join(bits) or "just chilling"


class PlayFusion:
    def __init__(self, session: GameSession, brain, presence_driver, *, tts=None,
                 say_in_game: bool = True):
        self.session = session
        self.brain = brain
        self.presence = presence_driver
        self.tts = tts
        self.say_in_game = say_in_game

    def react(self, user_said: str | None = None, *,
              action: GameAction | None = None,
              persona: str | None = None) -> FusionResult:
        state = self.session.observe()
        prompt = (persona or
                  f"You're playing {state.game} with Aditya as his friend Aero. "
                  "Keep replies short and casual.")
        content = f"[game: {_state_summary(state)}]"
        if user_said:
            content += f"\nAditya: {user_said}"
        content += "\nReact in one short line."

        reply = self.brain.chat([ChatMessage("system", prompt),
                                 ChatMessage("user", content)]).text.strip()

        intent = intent_from_text(reply) if reply else SpeechIntent.neutral("")
        avatar = self.presence.tick(speaking=bool(reply), intent=intent,
                                    mouth_open=0.5 if reply else 0.0)

        # optional in-game action — gated by GameSession (policy + 'games' grant)
        act_result = self.session.act(action) if action is not None else None

        # post to in-game chat only where acting is allowed (play games, granted)
        in_game_said = False
        if reply and self.say_in_game:
            said = self.session.act(GameAction("say", {"text": reply}))
            in_game_said = said.ok

        spoke = False
        if reply and self.tts is not None:
            try:
                self.tts.speak(intent)
                spoke = True
            except Exception:
                spoke = False

        return FusionResult(text=reply, avatar=avatar, in_game_said=in_game_said,
                            action=act_result, spoke=spoke)
