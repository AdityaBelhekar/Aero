"""RigManifest — the clip↔meaning map the user authors with their model (AERO-PRES-103).

The 3D model and its animation clips are *content* Aditya makes in Blender/Godot.
The manifest is the thin JSON bridge that tells Aero what each clip *means*:

    {
      "model": "aero.glb",
      "states":   { "idle": ["idle_base", "idle_relaxed"],
                    "listening": ["listen"],
                    "thinking":  ["think"],
                    "speaking":  ["talk"] },
      "state_emotions": { "speaking": { "happy": "talk_happy",
                                        "tired": "talk_tired" } },
      "emotions": { "happy": "face_happy", "teasing": "face_smirk",
                    "concerned": "face_concern" },
      "fidgets":  ["look_around", "stretch", "glance_at_screen", "bored_sigh"],
      "actions":  { "wave": "act_wave", "facepalm": "act_facepalm",
                    "point_at_screen": "act_point", "dance": "act_dance" },
      "lipsync":  { "blendshape": "mouthOpen" }
    }

Adding a new behaviour = author a clip + add one manifest line. **No code change**
(v0.3 Rule 11). Everything is optional with safe fallbacks, so a half-authored rig
still runs — and a placeholder rig (``default_manifest``) lets the whole presence
stack run and be tested before the real model exists.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from aero.presence.state import AnimationState, Emotion

# Every rig must at least name a clip for these four states, or the overlay has
# nothing to play. validate() reports any that are missing.
REQUIRED_STATES = tuple(s.value for s in AnimationState)


@dataclass
class RigManifest:
    model: str = ""
    states: dict[str, list[str]] = field(default_factory=dict)
    state_emotions: dict[str, dict[str, str]] = field(default_factory=dict)
    emotions: dict[str, str] = field(default_factory=dict)
    fidgets: list[str] = field(default_factory=list)
    actions: dict[str, str] = field(default_factory=dict)
    lipsync_blendshape: str = "mouthOpen"

    # -- loading -----------------------------------------------------------
    @classmethod
    def from_dict(cls, d: dict) -> "RigManifest":
        # Coerce state clip values to lists so ["clip"] and "clip" both work.
        states = {k: (v if isinstance(v, list) else [v])
                  for k, v in (d.get("states") or {}).items()}
        return cls(
            model=d.get("model", ""),
            states=states,
            state_emotions=dict(d.get("state_emotions") or {}),
            emotions=dict(d.get("emotions") or {}),
            fidgets=list(d.get("fidgets") or []),
            actions=dict(d.get("actions") or {}),
            lipsync_blendshape=(d.get("lipsync") or {}).get("blendshape", "mouthOpen"),
        )

    @classmethod
    def load(cls, path: str | Path) -> "RigManifest":
        return cls.from_dict(json.loads(Path(path).read_text(encoding="utf-8")))

    # -- lookups (safe fallbacks, never raise) -----------------------------
    def clips_for_state(self, state: AnimationState) -> list[str]:
        """All base clips authored for a state (idle may have several variants)."""
        return list(self.states.get(state.value, []))

    def clip_for_state(
        self, state: AnimationState, emotion: Emotion = Emotion.NEUTRAL, *, index: int = 0
    ) -> str:
        """The clip to play for a state, preferring an emotion-specific override
        (e.g. ``talk_happy``) when the rig authored one. Falls back to the base
        state clip, then to any state clip, then empty string."""
        em_override = self.state_emotions.get(state.value, {}).get(emotion.value)
        if em_override:
            return em_override
        clips = self.clips_for_state(state)
        if not clips:
            return ""
        return clips[index % len(clips)]

    def expression_clip(self, emotion: Emotion) -> str | None:
        """The facial/pose clip for an emotion (an overlay the renderer blends on
        top of the body animation), or None if the rig has no expression for it."""
        return self.emotions.get(emotion.value)

    def action_clip(self, action: str) -> str | None:
        """The clip for a named one-shot action (wave/facepalm/...), or None."""
        return self.actions.get(action)

    # -- validation --------------------------------------------------------
    def missing_states(self) -> list[str]:
        return [s for s in REQUIRED_STATES if not self.states.get(s)]

    def validate(self) -> list[str]:
        """Return human-readable warnings (empty = fully authored). Never raises —
        a partial rig still runs, this just surfaces the gaps."""
        warnings: list[str] = []
        for s in self.missing_states():
            warnings.append(f"no clip for required state '{s}'")
        if not self.model:
            warnings.append("no model file named")
        return warnings


def default_manifest() -> RigManifest:
    """A placeholder rig so the presence stack runs before Aditya's real model
    exists. Clip names are conventional guesses; the overlay treats unknown clips
    as no-ops, so this drives the state machine and tests without any assets."""
    return RigManifest.from_dict({
        "model": "placeholder.glb",
        "states": {
            "idle": ["idle_base"],
            "listening": ["listen"],
            "thinking": ["think"],
            "speaking": ["talk"],
        },
        "state_emotions": {},
        "emotions": {
            "happy": "face_happy",
            "teasing": "face_smirk",
            "excited": "face_excited",
            "tired": "face_tired",
            "concerned": "face_concern",
            "annoyed": "face_annoyed",
        },
        "fidgets": ["look_around", "stretch", "glance_at_screen", "bored_sigh"],
        "actions": {
            "wave": "act_wave",
            "facepalm": "act_facepalm",
            "point_at_screen": "act_point",
            "dance": "act_dance",
        },
        "lipsync": {"blendshape": "mouthOpen"},
    })
