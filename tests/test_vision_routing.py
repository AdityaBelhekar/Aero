"""Multimodal vision routing (AERO-VIS-602). Hermetic — HTTP mocked."""

from __future__ import annotations

from aero import settings as st
from aero.cognition.cloud_backend import CloudCognition
from aero.cognition.service import (
    CognitionService,
    CompletionResult,
    GenerationStats,
    VisionUnsupported,
)
from aero.perception.vision import Frame
from aero.perception.vision_router import VisionRouter

FRAME = Frame(image=b"\x89PNG-bytes", source="screen", fmt="png")


# -- CloudCognition.see request shaping ------------------------------------
def test_cloud_see_builds_openai_vision_message(monkeypatch):
    c = CloudCognition("gpt-4o", base_url="openai", api_key="k")
    seen = {}

    def fake_post(path, payload):
        seen["path"] = path
        seen["payload"] = payload
        return {"choices": [{"message": {"content": "a valorant scoreboard"}}],
                "usage": {"prompt_tokens": 20, "completion_tokens": 5}}

    monkeypatch.setattr(c, "_post", fake_post)
    res = c.see("what is this?", b"IMGDATA", media_type="image/png")
    assert res.text == "a valorant scoreboard"
    content = seen["payload"]["messages"][0]["content"]
    assert content[0] == {"type": "text", "text": "what is this?"}
    assert content[1]["type"] == "image_url"
    assert content[1]["image_url"]["url"].startswith("data:image/png;base64,")


def test_base_service_see_unsupported():
    from aero.cognition.ollama_backend import OllamaCognition
    try:
        OllamaCognition().see("x", b"y")
    except VisionUnsupported:
        pass
    else:
        raise AssertionError("expected VisionUnsupported")


# -- profile selection -----------------------------------------------------
def test_pick_explicit_vision_profile():
    s = st.VoiceSettings(vision_profile="gemini")
    assert VisionRouter(settings=s).pick_profile(s).id == "gemini"


def test_pick_active_brain_if_it_sees():
    s = st.VoiceSettings(brain_profile="openai")   # openai supports vision
    assert VisionRouter(settings=s).pick_profile(s).id == "openai"


def test_pick_falls_back_to_keyed_vision_brain(monkeypatch):
    # active is local (no vision); pick first vision-capable with a key
    monkeypatch.setenv("OPENAI_API_KEY", "sk-x")
    monkeypatch.setattr("aero.cognition.keys._keyring", lambda: None)
    s = st.VoiceSettings(brain_profile="local")
    picked = VisionRouter(settings=s).pick_profile(s)
    assert picked is not None and picked.supports_vision


def test_pick_none_when_no_vision_brain(monkeypatch):
    monkeypatch.setattr("aero.cognition.keys._keyring", lambda: None)
    for e in ("OPENAI_API_KEY", "GEMINI_API_KEY", "AERO_BRAIN_API_KEY",
              "GROQ_API_KEY", "OPENROUTER_API_KEY"):
        monkeypatch.delenv(e, raising=False)
    s = st.VoiceSettings(brain_profile="local")   # local can't see; no keys
    assert VisionRouter(settings=s).pick_profile(s) is None


# -- end-to-end routing with a fake brain ----------------------------------
class FakeVisionBrain(CognitionService):
    model_name = "fake-vision"
    supports_vision = True

    def __init__(self):
        self.saw = None

    def chat(self, *a, **k): ...
    def complete_json(self, *a, **k): ...
    def health_check(self): return True

    def see(self, prompt, image, *, media_type="image/png", **k):
        self.saw = (prompt, image, media_type)
        return CompletionResult("he's bottom-fragging again", GenerationStats(0, 0, 1e-9))


def test_router_routes_frame_to_vision_brain():
    s = st.VoiceSettings(vision_profile="openai")
    fake = FakeVisionBrain()
    router = VisionRouter(settings=s, brain_builder=lambda p: fake)
    ans = router.see(FRAME, prompt="roast the scoreboard")
    assert ans.ok and ans.brain == "openai"
    assert ans.text == "he's bottom-fragging again"
    assert fake.saw[0] == "roast the scoreboard"
    assert fake.saw[2] == "image/png"


def test_router_no_vision_brain_is_clean():
    import os
    keys = ("OPENAI_API_KEY", "GEMINI_API_KEY", "AERO_BRAIN_API_KEY",
            "GROQ_API_KEY", "OPENROUTER_API_KEY")
    saved = {k: os.environ.pop(k, None) for k in keys}
    try:
        s = st.VoiceSettings(brain_profile="local")
        ans = VisionRouter(settings=s).see(FRAME)
        assert not ans.ok and "no vision-capable brain" in ans.reason
    finally:
        for k, v in saved.items():
            if v is not None:
                os.environ[k] = v


def test_router_handles_unsupported_gracefully():
    class NoSee(FakeVisionBrain):
        def see(self, *a, **k):
            raise VisionUnsupported("nope")
    s = st.VoiceSettings(vision_profile="openai")
    ans = VisionRouter(settings=s, brain_builder=lambda p: NoSee()).see(FRAME)
    assert not ans.ok and "nope" in ans.reason
