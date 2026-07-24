"""Daemon tests — hermetic (fake models + fake perception, no Ollama/Win32).

Exercises the tick logic that matters: consolidate when idle, don't when active,
log app switches, keep models warm.
"""

from __future__ import annotations

import uuid
import warnings
from pathlib import Path

from aero.config import Config
from aero.daemon import AeroDaemon, DaemonConfig
from aero.perception.tier0 import Tier0Sample
from aero.vault.connection import now_iso

from tests.test_memory import FakeEmbedder, FakeLLM  # reuse hermetic fakes


class FakeProvider:
    def __init__(self, samples):
        self._samples = list(samples)
        self.last = None

    def poll(self):
        s = self._samples.pop(0) if self._samples else (self.last or Tier0Sample(ok=False))
        switched = self.last is not None and self.last.ok and s.ok and \
            s.process_name != self.last.process_name
        self.last = s
        return s, switched


class WarmSpyLLM(FakeLLM):
    def __init__(self, tags):
        super().__init__(tags)
        self.warmed = 0

    def ensure_loaded(self, keep_alive="30m"):
        self.warmed += 1
        return True

    def health_check(self):
        return True


class WarmSpyEmb(FakeEmbedder):
    def __init__(self):
        super().__init__()
        self.warmed = 0

    def ensure_loaded(self, keep_alive="30m"):
        self.warmed += 1
        return True


def _daemon(tmp_path: Path, provider, llm=None, emb=None, idle=120.0):
    import os
    os.environ["AERO_HOME"] = str(tmp_path)
    cfg = Config(home=tmp_path)
    dcfg = DaemonConfig(idle_consolidate_seconds=idle)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return AeroDaemon(cfg, dcfg, llm=llm or WarmSpyLLM({}),
                          emb=emb or WarmSpyEmb(), provider=provider)


def _seed(daemon, text):
    daemon.vault.conn.execute(
        "INSERT INTO raw_events(id, ts, channel, payload) VALUES(?,?,?,?)",
        (uuid.uuid4().hex, now_iso(), "chat", text),
    )
    daemon.vault.conn.commit()


def test_consolidates_when_idle(tmp_path):
    llm = WarmSpyLLM({"coffee": {
        "summary": "Aditya likes coffee", "kind": "semantic", "topics": ["coffee"],
        "people": [], "emotion": "neutral", "is_failure": False, "importance": 0.4,
        "emotional_weight": 0.0, "sensitivity": 0.2, "roast_value": 0.0,
        "roast_allowed": False, "associations": [],
    }})
    # idle sample, repeated so the interruptible loop keeps going then finds no work
    idle_sample = Tier0Sample(process_name="code.exe", idle_seconds=300, ok=True)
    prov = FakeProvider([idle_sample] * 10)
    d = _daemon(tmp_path, prov, llm=llm, idle=120.0)
    d._running = True  # the interruptible consolidation loop is gated on this
    _seed(d, "Aditya drinks coffee every morning")
    d._maybe_consolidate(idle_sample)
    n = d.vault.conn.execute(
        "SELECT COUNT(*) AS n FROM memories WHERE summary NOT LIKE 'concept:%'"
    ).fetchone()["n"]
    assert n == 1
    d.shutdown()


def test_does_not_consolidate_when_active(tmp_path):
    active = Tier0Sample(process_name="code.exe", idle_seconds=5, ok=True)
    prov = FakeProvider([active] * 5)
    d = _daemon(tmp_path, prov, idle=120.0)
    _seed(d, "Aditya drinks coffee")
    d._maybe_consolidate(active)
    n = d.vault.conn.execute("SELECT COUNT(*) AS n FROM raw_events "
                             "WHERE consolidated_into IS NOT NULL").fetchone()["n"]
    assert n == 0  # nothing consolidated while active
    d.shutdown()


class ProactiveSpeakLLM(WarmSpyLLM):
    """Wants to speak whenever the impulse gate asks — everything else defers."""

    def complete_json(self, messages, *, temperature=0.2, max_tokens=None):
        from aero.cognition.service import CompletionResult, GenerationStats
        if "impulse gate" in messages[0].content.lower():
            payload = {"speak": True, "utterance": "wait, backwards?", "reason": "thread"}
            return payload, CompletionResult("{}", GenerationStats(1, 1, 0.01))
        return super().complete_json(messages, temperature=temperature, max_tokens=max_tokens)


def test_tick_surfaces_proactive_utterance(tmp_path):
    from aero import settings as st
    from aero.config import Config

    # Chatty + quiet-hours disabled so a strong impulse can clear the gate.
    cfg = Config(home=tmp_path)
    cfg.ensure_dirs()
    s = st.load(cfg)
    s.persona = {"chattiness": 0.9, "quiet_hours": [0, 0]}
    st.save(s, cfg)

    # A window that matches a waiting thought thread's trigger, user present-idle.
    sample = Tier0Sample(process_name="editor", window_title="impulse.py",
                         idle_seconds=90, ok=True)
    prov = FakeProvider([sample, sample])
    d = _daemon(tmp_path, prov, llm=ProactiveSpeakLLM({}), idle=1e9)
    d.proactive.threads.open("we approached this backwards", ["impulse"])
    d.tick()
    row = d.vault.conn.execute(
        "SELECT payload FROM raw_events WHERE channel='proactive'"
    ).fetchone()
    assert row is not None and "wait, backwards?" in row["payload"]
    d.shutdown()


def test_tick_logs_app_switch_and_warms(tmp_path):
    llm = WarmSpyLLM({})
    emb = WarmSpyEmb()
    samples = [
        Tier0Sample(process_name="code.exe", window_title="a", idle_seconds=5, ok=True),
        Tier0Sample(process_name="chrome.exe", window_title="b", idle_seconds=5, ok=True),
    ]
    prov = FakeProvider(samples)
    d = _daemon(tmp_path, prov, llm=llm, emb=emb, idle=120.0)
    d._last_warm = -9999  # force a warm this tick
    d.tick()  # first sample, no prior -> no switch
    d.tick()  # code -> chrome -> switch logged
    switches = d.vault.conn.execute(
        "SELECT COUNT(*) AS n FROM raw_events WHERE channel='world'"
    ).fetchone()["n"]
    assert switches == 1
    assert llm.warmed >= 1 and emb.warmed >= 1
    d.shutdown()
