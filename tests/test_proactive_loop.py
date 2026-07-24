"""ProactiveLoop — one full tick + feedback learning (PRD §7, M4).

End-to-end: generator -> threshold -> gate -> self-memory, with injected settings
and a fixed clock so it's fully deterministic (no hardware, no real brain).
"""

from __future__ import annotations

from aero import settings as st
from aero.memory.store import MemoryStore
from aero.proactive.gate import GateVerdict
from aero.proactive.loop import ProactiveLoop
from aero.working_set import WorldState


class SpeakLLM:
    def __init__(self, speak=True):
        self.payload = {"speak": speak, "utterance": "oye sab theek?", "reason": "concern"}
        self.calls = 0

    def complete_json(self, messages, *, temperature=0.2, max_tokens=None):
        self.calls += 1
        return self.payload, None


def _w(app=None, title=None, activity="idle", **extra):
    return WorldState(active_app=app, window_title=title,
                      activity_level=activity, extra=extra)


def _loop(vault, llm=None, settings=None, hour=14):
    s = settings or st.VoiceSettings()
    loop = ProactiveLoop(MemoryStore(vault, actor="proactive"), llm=llm,
                         settings=s, clock=lambda: 1000.0)
    return loop


# -- the quiet common case -------------------------------------------------
def test_no_impulse_returns_none(vault):
    loop = _loop(vault)
    w = _w("code.exe", activity="idle")
    assert loop.tick(w, prev=w, hour=14) is None   # still world -> nothing to decide


def test_weak_impulse_is_silent_no_model(vault):
    llm = SpeakLLM()
    loop = _loop(vault, llm=llm)
    # An app switch (novelty 0.25) can't clear the default threshold.
    d = loop.tick(_w("chrome.exe", activity="active"), prev=_w("code.exe"), hour=14)
    assert d is not None and d.verdict is GateVerdict.SILENT
    assert llm.calls == 0


# -- a strong, well-timed reason can reach speech --------------------------
def test_reactivated_thread_can_speak(vault):
    llm = SpeakLLM(speak=True)
    # chatty + not cold so the bar is low enough for a 0.7 thread impulse.
    s = st.VoiceSettings(persona={"chattiness": 0.9})
    loop = _loop(vault, llm=llm, settings=s)
    loop.threads.open("we approached this backwards", ["impulse"])
    d = loop.tick(_w("editor", title="impulse.py", activity="idle"),
                  prev=_w("editor"), hour=14)
    assert llm.calls == 1
    assert d.verdict is GateVerdict.SPEAK and d.utterance
    # a good initiation warms familiarity a touch
    assert loop.relationship.get("familiarity") > 0.05


def test_killswitch_silences_the_loop(vault):
    llm = SpeakLLM()
    s = st.VoiceSettings(persona={"chattiness": 0.9}, killswitch=True)
    loop = _loop(vault, llm=llm, settings=s)
    loop.threads.open("backwards", ["impulse"])
    d = loop.tick(_w("editor", title="impulse.py"), prev=_w("editor"), hour=14)
    assert d.verdict is GateVerdict.SILENT and llm.calls == 0


def test_quiet_hours_silences_the_loop(vault):
    llm = SpeakLLM()
    s = st.VoiceSettings(persona={"chattiness": 0.9, "quiet_hours": [1, 8]})
    loop = _loop(vault, llm=llm, settings=s)
    loop.threads.open("backwards", ["impulse"])
    d = loop.tick(_w("editor", title="impulse.py"), prev=_w("editor"), hour=3)
    assert d.verdict is GateVerdict.SILENT and "quiet hours" in d.reason
    assert llm.calls == 0


def test_disabled_loop_returns_none(vault):
    s = st.VoiceSettings(proactive={"enabled": False})
    loop = _loop(vault, llm=SpeakLLM(), settings=s)
    loop.threads.open("backwards", ["impulse"])
    assert loop.tick(_w("editor", title="impulse.py"), prev=_w("editor")) is None


def test_decisions_are_logged(vault):
    loop = _loop(vault, llm=SpeakLLM())
    loop.tick(_w("chrome.exe", activity="active"), prev=_w("code.exe"), hour=14)
    assert loop.selfmem.counts().get("stayed_silent", 0) >= 1


# -- feedback learning routes to the right store (AERO-FBK-003) ------------
def test_dont_interrupt_raises_app_offset(vault):
    s = st.VoiceSettings()
    loop = _loop(vault, settings=s)
    loop.record_feedback("dont_interrupt", app="code.exe")
    assert st.proactive_threshold_offset(s, "code.exe") > 0     # quieter in code
    assert st.proactive_threshold_offset(s, "chrome.exe") == 0  # scoped, not global


def test_talk_more_lowers_offset(vault):
    s = st.VoiceSettings()
    loop = _loop(vault, settings=s)
    loop.record_feedback("talk_more")
    assert st.proactive_threshold_offset(s) < 0


def test_good_call_builds_trust(vault):
    s = st.VoiceSettings()
    loop = _loop(vault, settings=s)
    before = loop.relationship.get("trust")
    loop.record_feedback("good_call")
    assert loop.relationship.get("trust") > before


def test_passive_ignore_moves_slowly(vault):
    s = st.VoiceSettings()
    loop = _loop(vault, settings=s)
    loop.record_feedback("ignored")
    # passive nudge is small vs the explicit dont_interrupt bump
    assert 0 < st.proactive_threshold_offset(s) < 0.1


def test_unknown_feedback_rejected(vault):
    loop = _loop(vault)
    try:
        loop.record_feedback("nonsense")
        assert False, "should have raised"
    except ValueError:
        pass
