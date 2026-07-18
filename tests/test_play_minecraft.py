"""Minecraft bridge connector (AERO-PLAY-702). Hermetic — fake transport."""

from __future__ import annotations

from aero import settings as st
from aero.play import GameAction, GameSession, PlayVerdict
from aero.play.minecraft import BotTransport, MinecraftConnector


class FakeTransport(BotTransport):
    def __init__(self, responses=None):
        self.calls = []
        self.responses = responses or {}

    def available(self):
        return True

    def request(self, op, params=None):
        self.calls.append((op, params or {}))
        return self.responses.get(op, {"ok": True, "op": op})


def test_join_parses_state():
    t = FakeTransport({"join": {"connected": True,
                                "position": {"x": 10, "y": 64, "z": -3},
                                "health": 20}})
    conn = MinecraftConnector(t)
    state = conn.join(username="Aero")
    assert state.connected and state.position == (10, 64, -3) and state.health == 20
    assert t.calls[0][0] == "join"


def test_observe_parses_inventory_and_entities():
    t = FakeTransport({"observe": {
        "position": [1, 2, 3], "health": 18,
        "inventory": [{"name": "dirt", "count": 12}],
        "entities": [{"name": "zombie", "dist": 5}],
        "chat": ["<Aditya> build a base"]}})
    state = MinecraftConnector(t).observe()
    assert state.position == (1, 2, 3)
    assert state.inventory[0]["name"] == "dirt"
    assert state.entities[0]["name"] == "zombie"
    assert state.chat == ["<Aditya> build a base"]


def test_act_sends_known_action():
    t = FakeTransport()
    conn = MinecraftConnector(t)
    conn.act(GameAction("mine", {"block": "stone"}))
    assert t.calls[-1] == ("mine", {"block": "stone"})


def test_act_rejects_unknown_action():
    t = FakeTransport()
    r = MinecraftConnector(t).act(GameAction("hack_the_server"))
    assert r["ok"] is False and "unknown" in r["error"]
    assert t.calls == []           # never sent to the bot


def test_leave_is_safe():
    t = FakeTransport()
    MinecraftConnector(t).leave()
    assert t.calls[-1][0] == "leave"


# -- through GameSession: consent + play policy apply ----------------------
def test_minecraft_action_via_session_needs_grant():
    t = FakeTransport()
    sess = GameSession(MinecraftConnector(t), settings=st.VoiceSettings())
    r = sess.act(GameAction("say", {"text": "hi"}))
    assert r.verdict is PlayVerdict.REFUSED_UNGRANTED
    assert t.calls == []           # gate stopped it before the transport


def test_minecraft_action_via_session_when_granted():
    t = FakeTransport({"say": {"ok": True}})
    sess = GameSession(MinecraftConnector(t),
                       settings=st.VoiceSettings(permissions={"games": True}))
    r = sess.act(GameAction("say", {"text": "chal bhai"}))
    assert r.ok and t.calls[-1] == ("say", {"text": "chal bhai"})
