"""Thought threads + relationship + self-memory (AERO-THT / AERO-REL / AERO-SELF)."""

from __future__ import annotations

from aero.memory.store import MemoryStore
from aero.proactive.relationship import DEFAULTS, MAX_STEP, RelationshipModel
from aero.proactive.selfmem import SelfMemoryLog
from aero.proactive.threads import ThoughtThreadStore


def _store(vault):
    return MemoryStore(vault, actor="proactive")


# -- thought threads -------------------------------------------------------
def test_open_and_list_active(vault):
    ts = ThoughtThreadStore(_store(vault))
    ts.open("train the impulse engine separately", ["impulse_engine.py", "training"])
    active = ts.active()
    assert len(active) == 1 and active[0].status == "active"


def test_trigger_matching_is_case_insensitive_substring(vault):
    ts = ThoughtThreadStore(_store(vault))
    ts.open("approached this backwards", ["impulse"])
    assert ts.matching("editing IMPULSE.py now")          # substring, any case
    assert not ts.matching("editing router.py")


def test_reactivation_touch_revives_dormant(vault):
    ts = ThoughtThreadStore(_store(vault))
    t = ts.open("idea", ["x"])
    ts.set_status(t.id, "dormant")
    assert not ts.active()
    ts.touch(t.id)
    assert len(ts.active()) == 1  # trigger match revived it


def test_resolve_removes_from_active(vault):
    ts = ThoughtThreadStore(_store(vault))
    t = ts.open("idea", ["x"])
    ts.resolve(t.id)
    assert not ts.active()
    assert ts.all(status="resolved")


def test_active_cap_demotes_oldest(vault):
    ts = ThoughtThreadStore(_store(vault), active_cap=3)
    for i in range(5):
        ts.open(f"idea {i}", [str(i)])
    active = ts.active()
    assert len(active) == 3  # cap enforced; oldest demoted to dormant
    assert len(ts.all(status="dormant")) == 2


# -- relationship model ----------------------------------------------------
def test_defaults_are_conservative(vault):
    rel = RelationshipModel(_store(vault))
    assert rel.get("familiarity") == DEFAULTS["familiarity"]
    assert rel.get("roast_tolerance") < 0.2  # humour is earned (AERO-COLD-003)


def test_nudge_is_bounded_per_call(vault):
    rel = RelationshipModel(_store(vault))
    before = rel.get("trust")
    # A huge single hit can't crater trust — clamped to one MAX_STEP (AERO-REL-003).
    after = rel.nudge("trust", -1.0)
    assert abs(before - after) <= MAX_STEP + 1e-9


def test_nudge_clamps_to_unit_interval(vault):
    rel = RelationshipModel(_store(vault))
    for _ in range(100):
        rel.nudge("familiarity", MAX_STEP)
    assert rel.get("familiarity") <= 1.0
    for _ in range(100):
        rel.nudge("familiarity", -MAX_STEP)
    assert rel.get("familiarity") >= 0.0


def test_seed_defaults_persists_rows(vault):
    rel = RelationshipModel(_store(vault))
    rel.seed_defaults()
    n = vault.conn.execute("SELECT COUNT(*) AS n FROM relationship_state").fetchone()["n"]
    assert n == len(DEFAULTS)


# -- self-memory -----------------------------------------------------------
def test_self_memory_records_and_reads(vault):
    log = SelfMemoryLog(_store(vault))
    log.record("stayed_silent", context="he was coding")
    log.record("spoke", context="reactivated thread", outcome="wait, backwards?")
    assert log.counts() == {"stayed_silent": 1, "spoke": 1}
    assert log.recent(limit=1)[0].action == "spoke"       # newest first
    assert log.recent(action="stayed_silent")[0].context == "he was coding"
