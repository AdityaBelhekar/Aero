"""play.* control ops (AERO-PLAY-7xx). Hermetic."""

from __future__ import annotations

from aero import settings as st
from aero.config import Config
from aero.control import ControlService


def test_play_games_lists_policies(tmp_path):
    r = ControlService(Config(home=tmp_path)).dispatch("play.games")
    assert r["ok"]
    by = {g["game"]: g for g in r["result"]["games"]}
    assert by["minecraft"]["mode"] == "play"
    assert by["valorant"]["mode"] == "spectate"
    assert by["valorant"]["can_automate"] is False


def test_play_status_minecraft(tmp_path):
    r = ControlService(Config(home=tmp_path)).dispatch("play.status", {"game": "minecraft"})
    s = r["result"]
    assert s["mode"] == "play" and s["games_granted"] is False
    assert s["bridge_available"] is False        # no bridge running


def test_play_act_spectate_refused(tmp_path):
    cfg = Config(home=tmp_path)
    s = st.load(cfg); s.permissions = {"games": True}; st.save(s, cfg)
    r = ControlService(cfg).dispatch("play.act", {"game": "valorant", "kind": "aim"})
    assert r["result"]["verdict"] == "refused_spectate"


def test_play_act_minecraft_needs_grant(tmp_path):
    r = ControlService(Config(home=tmp_path)).dispatch(
        "play.act", {"game": "minecraft", "kind": "say", "args": {"text": "hi"}})
    assert r["result"]["verdict"] == "refused_ungranted"


def test_play_act_missing_kind_errors(tmp_path):
    cfg = Config(home=tmp_path)
    s = st.load(cfg); s.permissions = {"games": True}; st.save(s, cfg)
    r = ControlService(cfg).dispatch("play.act", {"game": "minecraft"})
    assert r["ok"] is False and "kind" in r["error"]
