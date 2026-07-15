"""ControlService — the Control-App backend (AERO-APP-203..207). Hermetic."""

from __future__ import annotations

import pytest

from aero.config import Config
from aero.control import ControlService
from aero.memory.models import Memory, SocialMeta
from aero.memory.store import MemoryStore


@pytest.fixture()
def svc(tmp_path, vault):
    # Share the tmp vault + a control service pointed at the same home.
    cfg = Config(home=tmp_path)
    store = MemoryStore(vault, actor="test")
    return ControlService(cfg, store=store), store, cfg


# -- dispatch plumbing -----------------------------------------------------
def test_unknown_op():
    r = ControlService(Config(home=".")).dispatch("does.not.exist")
    assert r["ok"] is False and "unknown op" in r["error"]


def test_dispatch_catches_missing_param(tmp_path):
    r = ControlService(Config(home=tmp_path)).dispatch("brain.set", {})
    assert r["ok"] is False and "profile" in r["error"]


def test_ops_list_stable(tmp_path):
    ops = ControlService(Config(home=tmp_path)).ops()
    for expected in ("status", "brain.list", "voice.get", "persona.set",
                     "perms.grant", "memory.list"):
        assert expected in ops


# -- status ----------------------------------------------------------------
def test_status_no_network(svc):
    s, store, cfg = svc
    store.add_memory(Memory(summary="likes coffee", kind="semantic"))
    r = s.dispatch("status")
    assert r["ok"]
    assert r["result"]["brain"]["active"] == "local"
    assert r["result"]["killswitch"] is False
    assert r["result"]["memory_counts"]["semantic"] == 1


# -- brain manager ---------------------------------------------------------
def test_brain_list_and_set(svc):
    s, _, _ = svc
    lst = s.dispatch("brain.list")["result"]
    ids = {p["id"] for p in lst["profiles"]}
    assert {"local", "groq", "litellm"} <= ids
    assert lst["active"] == "local"

    s.dispatch("brain.set", {"profile": "groq"})
    assert s.dispatch("brain.get")["result"]["active"] == "groq"


def test_brain_router_config(svc):
    s, _, _ = svc
    r = s.dispatch("brain.router", {"reflex": "local", "primary": "groq",
                                    "private_only": True})["result"]
    assert r["reflex"] == "local" and r["primary"] == "groq"
    assert r["private_only"] is True


def test_brain_set_key_no_backend(svc, monkeypatch):
    from aero.cognition import keys
    monkeypatch.setattr(keys, "_keyring", lambda: None)
    r = s = svc[0].dispatch("brain.set_key", {"profile": "groq", "key": "x"})
    assert r["ok"] is False and "keyring" in r["error"]


# -- voice manager ---------------------------------------------------------
def test_voice_get_set(svc):
    s, _, _ = svc
    s.dispatch("voice.set", {"engine": "kokoro", "kokoro_voice": "am_adam"})
    g = s.dispatch("voice.get")["result"]
    assert g["engine"] == "kokoro" and g["kokoro_voice"] == "am_adam"
    assert "kokoro" in s.dispatch("voice.list")["result"]["engines"]


# -- personality dials -----------------------------------------------------
def test_persona_get_defaults(svc):
    r = svc[0].dispatch("persona.get")["result"]
    assert r["dials"]["chattiness"] == 0.5


def test_persona_set_valid(svc):
    s, _, _ = svc
    r = s.dispatch("persona.set", {"dials": {"roast_level": 0.8,
                                             "language_mix": "hinglish",
                                             "quiet_hours": [0, 7]}})
    assert r["ok"]
    d = s.dispatch("persona.get")["result"]["dials"]
    assert d["roast_level"] == 0.8 and d["language_mix"] == "hinglish"
    assert d["quiet_hours"] == [0, 7]
    assert d["chattiness"] == 0.5  # untouched default preserved


def test_persona_set_rejects_bad_values(svc):
    s, _, _ = svc
    assert s.dispatch("persona.set", {"dials": {"roast_level": 5}})["ok"] is False
    assert s.dispatch("persona.set", {"dials": {"nope": 1}})["ok"] is False
    assert s.dispatch("persona.set", {"dials": {"language_mix": "klingon"}})["ok"] is False
    assert s.dispatch("persona.set", {"dials": {"quiet_hours": [1]}})["ok"] is False


# -- permissions + kill switch ---------------------------------------------
def test_perms_default_deny(svc):
    r = svc[0].dispatch("perms.get")["result"]
    assert all(v is False for v in r["scopes"].values())
    assert r["killswitch"] is False


def test_perms_grant_and_killswitch(svc):
    s, _, _ = svc
    s.dispatch("perms.grant", {"scope": "apps", "on": True})
    assert s.dispatch("perms.get")["result"]["scopes"]["apps"] is True
    # kill switch forces everything off
    s.dispatch("perms.killswitch", {"on": True})
    assert s.dispatch("perms.get")["result"]["scopes"]["apps"] is False


def test_perms_grant_unknown_scope(svc):
    assert svc[0].dispatch("perms.grant", {"scope": "nukes"})["ok"] is False


# -- memory browser --------------------------------------------------------
def test_memory_list_and_search(svc):
    s, store, _ = svc
    store.add_memory(Memory(summary="likes medium roast coffee", kind="semantic"))
    store.add_memory(Memory(summary="plays valorant at night", kind="episodic"))
    store.add_memory(Memory(summary="concept: coffee", kind="semantic"))  # excluded

    allm = s.dispatch("memory.list")["result"]
    assert allm["count"] == 2  # concept:% filtered out
    hits = s.dispatch("memory.list", {"query": "coffee"})["result"]
    assert hits["count"] == 1 and "coffee" in hits["memories"][0]["summary"]


def test_memory_get_with_social_and_neighbors(svc):
    s, store, _ = svc
    a = store.add_memory(Memory(summary="A", kind="episodic",
                                social=SocialMeta(roast_allowed=True)))
    b = store.add_memory(Memory(summary="B", kind="episodic"))
    store.link(a, b, "topic", 0.5)
    r = s.dispatch("memory.get", {"id": a})["result"]
    assert r["memory"]["summary"] == "A"
    assert r["social"]["roast_allowed"] is True
    assert r["neighbors"][0]["dst"] == b


def test_memory_edit(svc):
    s, store, _ = svc
    mid = store.add_memory(Memory(summary="old", kind="semantic", importance=0.2))
    s.dispatch("memory.edit", {"id": mid, "fields": {"summary": "new", "importance": 0.9}})
    m = store.get(mid)
    assert m.summary == "new" and m.importance == 0.9


def test_memory_edit_rejects_structural_field(svc):
    s, store, _ = svc
    mid = store.add_memory(Memory(summary="x", kind="semantic"))
    r = s.dispatch("memory.edit", {"id": mid, "fields": {"kind": "core"}})
    assert r["ok"] is False and "not editable" in r["error"]


def test_memory_delete_soft(svc):
    s, store, _ = svc
    mid = store.add_memory(Memory(summary="forget me", kind="episodic"))
    r = s.dispatch("memory.delete", {"id": mid})
    assert r["ok"] and r["result"]["status"] == "tombstoned"
    assert store.get(mid).status == "tombstoned"   # soft delete, provenance survives


def test_memory_get_missing(svc):
    assert svc[0].dispatch("memory.get", {"id": "nope"})["ok"] is False
