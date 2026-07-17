"""VisionRouter — send a frame to a vision-capable brain (AERO-VIS-602).

Vision is a *brain capability*, not a separate stack: a frame goes to whichever
registry profile is flagged ``supports_vision`` (M8), via that brain's ``see()``.
This is Tier-2 — reached only on a trigger ("Aero look at this"), a high-salience
event, or when cheap OCR (Tier-1) wasn't enough — so it stays within the
event-driven budget.

Selection order:
  1. an explicit ``settings.vision_profile`` (if it supports vision),
  2. the active brain, if it supports vision,
  3. the first vision-capable profile that has a key (or is local).

No vision brain available -> a clean "can't see" answer, never a crash.
"""

from __future__ import annotations

from dataclasses import dataclass

from aero import settings as st
from aero.cognition.keys import resolve_key
from aero.cognition.registry import BrainProfile, build_from_profile, registry
from aero.cognition.service import CognitionService, VisionUnsupported
from aero.config import Config
from aero.perception.vision import Frame


@dataclass
class VisionAnswer:
    ok: bool
    text: str = ""
    brain: str = ""
    reason: str = ""

    def to_dict(self) -> dict:
        return {"ok": self.ok, "text": self.text, "brain": self.brain,
                "reason": self.reason}


_MEDIA = {"png": "image/png", "jpeg": "image/jpeg", "jpg": "image/jpeg"}


class VisionRouter:
    def __init__(self, cfg: Config | None = None, *, settings=None, brain_builder=None):
        self.cfg = cfg or Config.load()
        self._settings = settings
        # Injectable so tests don't hit the network; defaults to the real build.
        self._build = brain_builder or self._default_build

    def _load(self):
        return self._settings if self._settings is not None else st.load(self.cfg)

    @staticmethod
    def _default_build(profile: BrainProfile) -> CognitionService:
        return build_from_profile(profile, api_key=resolve_key(profile))

    def pick_profile(self, s) -> BrainProfile | None:
        reg = registry(s.brains)
        if s.vision_profile:
            p = reg.get(s.vision_profile)
            if p and p.supports_vision:
                return p
        active = st.resolve_brain_profile(s)
        if active.supports_vision:
            return active
        for p in reg.values():
            if p.supports_vision and (p.is_local or resolve_key(p) is not None):
                return p
        return None

    def see(self, frame: Frame, prompt: str = "What's on the screen?") -> VisionAnswer:
        s = self._load()
        profile = self.pick_profile(s)
        if profile is None:
            return VisionAnswer(ok=False, reason="no vision-capable brain configured "
                                "(set one with a key, e.g. openai/gemini)")
        brain = self._build(profile)
        media_type = _MEDIA.get(frame.fmt, "image/png")
        try:
            result = brain.see(prompt, frame.image, media_type=media_type)
        except VisionUnsupported as e:
            return VisionAnswer(ok=False, brain=profile.id, reason=str(e))
        except Exception as e:
            return VisionAnswer(ok=False, brain=profile.id,
                                reason=f"{type(e).__name__}: {e}")
        return VisionAnswer(ok=True, text=result.text, brain=profile.id)
