"""Spectator commentary + voice/game/avatar fusion (AERO-PLAY-703/704). Hermetic."""

from __future__ import annotations

import random

from aero import settings as st
from aero.cognition.service import CompletionResult, GenerationStats
from aero.perception.vision import Frame
from aero.perception.vision_router import VisionAnswer
from aero.play import GameAction, GameSession, PlayVerdict
from aero.play.fusion import PlayFusion
from aero.play.spectator import Spectator
from aero.presence import PresenceDriver
from aero.presence.state import AnimationState
from tests.test_play_minecraft import FakeTransport
from aero.play.minecraft import MinecraftConnector


# -- spectator -------------------------------------------------------------
class FakeEyes:
    def __init__(self, ok=True, reason=""):
        self._ok = ok
        self._reason = reason

    def look(self, source="screen"):
        class R:
            ok = self._ok
            reason = self._reason
            frame = Frame(image=b"IMG", source="screen") if self._ok else None
        return R()


class FakeVision:
    def __init__(self, text="he's throwing again lol", ok=True):
        self._text = text
        self._ok = ok

    def see(self, frame, prompt):
        self.prompt = prompt
        return VisionAnswer(ok=self._ok, text=self._text, brain="fake")


def test_spectator_comments_on_screen():
    spec = Spectator(FakeEyes(ok=True), FakeVision("clutch or kick"), game="valorant")
    c = spec.watch()
    assert c.ok and c.text == "clutch or kick"


def test_spectator_blocked_when_no_screen_grant():
    spec = Spectator(FakeEyes(ok=False, reason="permission 'screen' not granted"),
                     FakeVision())
    c = spec.watch()
    assert not c.ok and "screen" in c.reason


def test_spectator_never_has_act_method():
    # structurally: a spectator can only look, there is no way to send input
    assert not hasattr(Spectator(FakeEyes(), FakeVision()), "act")


# -- fusion ----------------------------------------------------------------
class FakeBrain:
    def __init__(self, reply="gg bhai, clean build"):
        self.reply = reply
        self.prompts = []

    def chat(self, messages, **kw):
        self.prompts.append(messages)
        return CompletionResult(self.reply, GenerationStats(0, 0, 1e-9))


def _fusion(settings, *, brain=None, tts=None):
    sess = GameSession(MinecraftConnector(FakeTransport({"say": {"ok": True}})),
                       settings=settings)
    driver = PresenceDriver(clock=lambda: 0.0, rng=random.Random(0))
    return PlayFusion(sess, brain or FakeBrain(), driver, tts=tts), sess


def test_fusion_speaks_and_drives_avatar():
    fusion, _ = _fusion(st.VoiceSettings(permissions={"games": True}))
    r = fusion.react(user_said="check this base")
    assert r.text == "gg bhai, clean build"
    assert r.avatar.animation is AnimationState.SPEAKING
    assert r.avatar.mouth_open > 0
    assert r.in_game_said is True         # play game + granted -> posts to chat


def test_fusion_does_not_post_in_game_without_grant():
    fusion, _ = _fusion(st.VoiceSettings())   # games NOT granted
    r = fusion.react(user_said="hi")
    assert r.text                              # still talks + emotes
    assert r.in_game_said is False             # but nothing sent to the game


def test_fusion_action_gated():
    fusion, _ = _fusion(st.VoiceSettings(permissions={"games": True}))
    r = fusion.react(action=GameAction("mine", {"block": "diamond"}))
    assert r.action is not None and r.action.ok


def test_fusion_action_refused_without_grant():
    fusion, _ = _fusion(st.VoiceSettings())
    r = fusion.react(action=GameAction("mine"))
    assert r.action.verdict is PlayVerdict.REFUSED_UNGRANTED


def test_fusion_tts_spoken_flag():
    class FakeTTS:
        def __init__(self): self.spoke = False
        def speak(self, intent): self.spoke = True
    tts = FakeTTS()
    fusion, _ = _fusion(st.VoiceSettings(permissions={"games": True}), tts=tts)
    r = fusion.react(user_said="yo")
    assert r.spoke is True and tts.spoke is True


def test_fusion_passes_game_state_to_brain():
    brain = FakeBrain()
    fusion, _ = _fusion(st.VoiceSettings(permissions={"games": True}), brain=brain)
    fusion.react(user_said="where are you")
    # the user's line + a game-state summary reached the brain
    user_msg = brain.prompts[0][1].content
    assert "where are you" in user_msg and "game:" in user_msg
