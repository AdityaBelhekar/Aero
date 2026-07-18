"""GameConnector + policy + anti-cheat consent (AERO-PLAY-701/705). Hermetic."""

from __future__ import annotations

from aero import settings as st
from aero.play import (
    GameAction,
    GameConnector,
    GameSession,
    GameState,
    PlayVerdict,
    game_policy,
)
from aero.play.connector import GameMode


class FakeConnector(GameConnector):
    def __init__(self, game):
        self.game = game
        self.acted = []
        self.joined = False

    def join(self, **kw):
        self.joined = True
        return GameState(game=self.game, connected=True)

    def observe(self):
        return GameState(game=self.game, connected=True, health=20,
                         position=(1.0, 2.0, 3.0))

    def act(self, action):
        self.acted.append(action)
        return {"did": action.kind}

    def leave(self):
        self.joined = False


# -- policy ----------------------------------------------------------------
def test_minecraft_is_play():
    p = game_policy("minecraft")
    assert p.mode is GameMode.PLAY and p.can_automate


def test_competitive_is_spectate():
    assert game_policy("valorant").mode is GameMode.SPECTATE
    assert not game_policy("valorant").can_automate


def test_unknown_game_defaults_to_spectate():
    # fail safe: never auto-act on a game without an explicit play policy
    assert game_policy("some_random_game").mode is GameMode.SPECTATE


def test_policy_case_insensitive():
    assert game_policy("Minecraft").can_automate


# -- session: observe never gated -----------------------------------------
def test_observe_works():
    sess = GameSession(FakeConnector("minecraft"),
                       settings=st.VoiceSettings())
    state = sess.observe()
    assert state.health == 20 and state.position == (1.0, 2.0, 3.0)


# -- session: play mode gated on 'games' grant ----------------------------
def test_play_action_refused_without_grant():
    conn = FakeConnector("minecraft")
    sess = GameSession(conn, settings=st.VoiceSettings())   # games not granted
    r = sess.act(GameAction("mine", {"block": "stone"}))
    assert r.verdict is PlayVerdict.REFUSED_UNGRANTED
    assert conn.acted == []                    # nothing ran


def test_play_action_allowed_when_granted():
    conn = FakeConnector("minecraft")
    sess = GameSession(conn, settings=st.VoiceSettings(permissions={"games": True}))
    r = sess.act(GameAction("mine", {"block": "stone"}))
    assert r.ok and r.result == {"did": "mine"}
    assert len(conn.acted) == 1


def test_killswitch_blocks_play_action():
    conn = FakeConnector("minecraft")
    sess = GameSession(conn, settings=st.VoiceSettings(
        permissions={"games": True}, killswitch=True))
    assert sess.act(GameAction("mine")).verdict is PlayVerdict.REFUSED_UNGRANTED
    assert conn.acted == []


# -- ANTI-CHEAT red-team: spectate-only games never act -------------------
def test_spectate_game_refuses_action_even_when_granted():
    conn = FakeConnector("valorant")
    # games granted AND kill switch off — still must refuse: it's spectate-only
    sess = GameSession(conn, settings=st.VoiceSettings(permissions={"games": True}))
    r = sess.act(GameAction("aim", {"target": "enemy"}))
    assert r.verdict is PlayVerdict.REFUSED_SPECTATE
    assert conn.acted == []                    # PROVABLY never touched the game


def test_unknown_game_also_refuses_actions():
    conn = FakeConnector("mystery_game")
    sess = GameSession(conn, settings=st.VoiceSettings(permissions={"games": True}))
    assert sess.act(GameAction("do")).verdict is PlayVerdict.REFUSED_SPECTATE
    assert conn.acted == []


def test_act_result_serialises():
    sess = GameSession(FakeConnector("valorant"), settings=st.VoiceSettings())
    d = sess.act(GameAction("x")).to_dict()
    assert d["verdict"] == "refused_spectate" and d["result"] is None
