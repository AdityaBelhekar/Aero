"""ImpulseGate — default silence, structurally (AERO-PRO-002/003/006).

The gate is the proactive counterpart of the consent gate: silence wins by
construction, the LLM runs only after cheap checks pass, and *every* decision
(incl. silences) is logged with its reasoning.
"""

from __future__ import annotations

from aero.memory.store import MemoryStore
from aero.proactive.gate import GateContext, GateVerdict, ImpulseGate
from aero.proactive.impulse import Impulse, ImpulseSource
from aero.proactive.selfmem import SelfMemoryLog


def _imp(strength=1.0, decay=60.0, created=0.0, source=ImpulseSource.CONCERN):
    return Impulse(source, strength, "subj", "detail",
                   created_at=created, decay_seconds=decay)


class SpeakLLM:
    """A brain that always wants to talk — to prove the gate still governs it."""

    def __init__(self, speak=True, utterance="oye, dekh le this", reason="worth it"):
        self.payload = {"speak": speak, "utterance": utterance, "reason": reason}
        self.calls = 0

    def complete_json(self, messages, *, temperature=0.2, max_tokens=None):
        self.calls += 1
        return self.payload, None


class BoomLLM:
    def complete_json(self, messages, *, temperature=0.2, max_tokens=None):
        raise RuntimeError("brain exploded")


# -- structural silence (no model call) ------------------------------------
def test_killswitch_forces_silence_even_above_threshold():
    llm = SpeakLLM()
    d = ImpulseGate().evaluate(_imp(1.0), threshold=0.1, now=0.0,
                               killswitch=True, llm=llm)
    assert d.verdict is GateVerdict.SILENT
    assert "kill switch" in d.reason
    assert llm.calls == 0  # never consulted a model


def test_quiet_hours_forces_silence():
    llm = SpeakLLM()
    d = ImpulseGate().evaluate(_imp(1.0), threshold=0.1, now=0.0,
                               quiet_hours=True, llm=llm)
    assert d.verdict is GateVerdict.SILENT and "quiet hours" in d.reason
    assert llm.calls == 0


def test_stale_impulse_discarded():
    llm = SpeakLLM()
    imp = _imp(1.0, decay=10.0, created=0.0)
    d = ImpulseGate().evaluate(imp, threshold=0.1, now=20.0, llm=llm)
    assert d.verdict is GateVerdict.SILENT and "moment passed" in d.reason
    assert llm.calls == 0


def test_below_threshold_is_silent_without_model():
    llm = SpeakLLM()
    d = ImpulseGate().evaluate(_imp(0.2), threshold=0.5, now=0.0, llm=llm)
    assert d.verdict is GateVerdict.SILENT and "below threshold" in d.reason
    assert llm.calls == 0  # the cheap ~90% path never spends a token


# -- the LLM social evaluation (only reached above threshold) --------------
def test_above_threshold_consults_model_and_can_speak():
    llm = SpeakLLM(speak=True, utterance="tu theek hai?")
    d = ImpulseGate().evaluate(_imp(0.9), threshold=0.5, now=0.0, llm=llm)
    assert llm.calls == 1
    assert d.verdict is GateVerdict.SPEAK and d.utterance == "tu theek hai?"
    assert d.llm_ran is True


def test_model_defaults_to_silence():
    llm = SpeakLLM(speak=False, utterance="", reason="he's busy")
    d = ImpulseGate().evaluate(_imp(0.9), threshold=0.5, now=0.0, llm=llm)
    assert d.verdict is GateVerdict.SILENT and "he's busy" in d.reason


def test_speak_without_utterance_stays_silent():
    llm = SpeakLLM(speak=True, utterance="   ")
    d = ImpulseGate().evaluate(_imp(0.9), threshold=0.5, now=0.0, llm=llm)
    assert d.verdict is GateVerdict.SILENT


def test_no_brain_is_silent():
    d = ImpulseGate().evaluate(_imp(0.9), threshold=0.5, now=0.0, llm=None)
    assert d.verdict is GateVerdict.SILENT and "no brain" in d.reason


def test_brain_error_degrades_to_silence():
    d = ImpulseGate().evaluate(_imp(0.9), threshold=0.5, now=0.0, llm=BoomLLM())
    assert d.verdict is GateVerdict.SILENT  # a broken brain never forces speech


# -- every decision is logged (AERO-PRO-006) -------------------------------
def test_silence_is_logged_with_reasoning(vault):
    log = SelfMemoryLog(MemoryStore(vault, actor="proactive"))
    gate = ImpulseGate(selfmem=log)
    gate.evaluate(_imp(0.2), threshold=0.5, now=0.0)  # below threshold
    entries = log.recent()
    assert len(entries) == 1
    assert entries[0].action == "stayed_silent"
    assert "below threshold" in entries[0].context


def test_speech_is_logged_with_utterance(vault):
    log = SelfMemoryLog(MemoryStore(vault, actor="proactive"))
    gate = ImpulseGate(selfmem=log)
    gate.evaluate(_imp(0.9), threshold=0.5, now=0.0, llm=SpeakLLM(utterance="hi"))
    e = log.recent()[0]
    assert e.action == "spoke" and e.outcome == "hi"
