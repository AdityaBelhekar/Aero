"""Brain router — two-speed cost/privacy policy (AERO-BRAIN-303). Hermetic."""

from __future__ import annotations

from aero.cognition.router import BrainRouter
from aero.cognition.service import (
    ChatMessage,
    CognitionService,
    CompletionResult,
    GenerationStats,
)
from aero.config import Config


class FakeBrain(CognitionService):
    """Records which calls it received; optionally raises on chat to simulate an
    offline/broke primary."""

    def __init__(self, name: str, *, healthy: bool = True, raise_on_chat: bool = False):
        self.model_name = name
        self._healthy = healthy
        self._raise = raise_on_chat
        self.chat_calls = 0
        self.json_calls = 0

    def _result(self) -> CompletionResult:
        return CompletionResult(self.model_name, GenerationStats(0, 0, 1e-9))

    def chat(self, messages, *, temperature=0.7, max_tokens=None):
        self.chat_calls += 1
        if self._raise:
            raise ConnectionError("primary down")
        return self._result()

    def complete_json(self, messages, *, temperature=0.2, max_tokens=None):
        self.json_calls += 1
        return {"from": self.model_name}, self._result()

    def health_check(self):
        return self._healthy


MSG = [ChatMessage("user", "hi")]


def test_chat_goes_to_primary():
    reflex, primary = FakeBrain("reflex"), FakeBrain("primary")
    r = BrainRouter(reflex, primary)
    res = r.chat(MSG)
    assert res.text == "primary"
    assert primary.chat_calls == 1 and reflex.chat_calls == 0
    assert not r.last_fallback


def test_json_always_goes_to_reflex():
    reflex, primary = FakeBrain("reflex"), FakeBrain("primary")
    r = BrainRouter(reflex, primary)
    parsed, _ = r.complete_json(MSG)
    assert parsed == {"from": "reflex"}
    assert reflex.json_calls == 1 and primary.json_calls == 0


def test_chat_falls_back_when_primary_errors():
    reflex = FakeBrain("reflex")
    primary = FakeBrain("primary", raise_on_chat=True)
    r = BrainRouter(reflex, primary)
    res = r.chat(MSG)
    assert res.text == "reflex"          # degraded to reflex
    assert r.last_fallback is True
    assert primary.chat_calls == 1 and reflex.chat_calls == 1


def test_single_brain_mode():
    reflex = FakeBrain("reflex")
    r = BrainRouter(reflex, None)
    assert r.chat(MSG).text == "reflex"
    assert r.complete_json(MSG)[0] == {"from": "reflex"}
    assert "router[reflex]" == r.model_name


def test_private_only_refuses_cloud_primary():
    reflex = FakeBrain("local")
    primary = FakeBrain("cloud")
    r = BrainRouter(reflex, primary, private_only=True, primary_is_private=False)
    assert r.primary is None                 # cloud primary dropped
    assert r.chat(MSG).text == "local"       # stays on device


def test_private_only_keeps_private_primary():
    reflex = FakeBrain("local-reflex")
    primary = FakeBrain("local-primary")
    r = BrainRouter(reflex, primary, private_only=True, primary_is_private=True)
    assert r.primary is primary
    assert r.chat(MSG).text == "local-primary"


def test_health_tracks_reflex():
    assert BrainRouter(FakeBrain("r", healthy=True), FakeBrain("p")).health_check()
    assert not BrainRouter(FakeBrain("r", healthy=False)).health_check()


# -- settings factory ------------------------------------------------------
def test_build_router_single_by_default(tmp_path):
    from aero import settings as st
    from aero.cognition.ollama_backend import OllamaCognition
    # No reflex/primary configured -> plain single brain (drop-in).
    assert isinstance(st.build_router(Config(home=tmp_path)), OllamaCognition)


def test_build_router_two_speed(tmp_path):
    from aero import settings as st
    cfg = Config(home=tmp_path)
    s = st.load(cfg)
    s.reflex_profile = "local"; s.primary_profile = "groq"
    st.save(s, cfg)
    r = st.build_router(cfg)
    assert isinstance(r, BrainRouter)
    assert r.primary is not None
    assert r.reflex.model_name == "gemma4:e4b"        # local reflex
    assert "groq" in r.primary.base_url               # cloud primary


def test_build_router_force_pins_primary(tmp_path):
    from aero import settings as st
    cfg = Config(home=tmp_path)
    s = st.load(cfg)
    s.reflex_profile = "local"  # tagging stays local
    st.save(s, cfg)
    r = st.build_router(cfg, force="gemini")
    assert isinstance(r, BrainRouter)
    assert r.primary.model_name == "gemini-2.0-flash"  # forced primary
    assert r.reflex.model_name == "gemma4:e4b"         # reflex unchanged


def test_build_router_private_only_drops_cloud(tmp_path):
    from aero import settings as st
    cfg = Config(home=tmp_path)
    s = st.load(cfg)
    s.reflex_profile = "local"; s.primary_profile = "groq"
    s.brain_private_only = True
    st.save(s, cfg)
    r = st.build_router(cfg)
    assert isinstance(r, BrainRouter)
    assert r.primary is None                          # cloud refused under privacy
