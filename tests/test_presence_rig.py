"""Avatar state + rig manifest (AERO-PRES-102/103). Hermetic, no assets needed."""

from __future__ import annotations

import json

from aero.presence.rig import RigManifest, default_manifest
from aero.presence.state import AnimationState, AvatarState, Emotion


# -- AvatarState -----------------------------------------------------------
def test_avatarstate_json_roundtrip():
    s = AvatarState(
        animation=AnimationState.SPEAKING, emotion=Emotion.HAPPY,
        clip="talk_happy", mouth_open=0.6, tags=["night"],
    )
    back = AvatarState.from_dict(json.loads(s.to_json()))
    assert back.animation is AnimationState.SPEAKING
    assert back.emotion is Emotion.HAPPY
    assert back.clip == "talk_happy"
    assert back.mouth_open == 0.6
    assert back.tags == ["night"]


def test_avatarstate_defaults_are_idle_neutral():
    s = AvatarState()
    assert s.animation is AnimationState.IDLE
    assert s.emotion is Emotion.NEUTRAL
    assert s.mouth_open == 0.0 and s.action is None


def test_avatarstate_json_is_compact():
    # goes over IPC on every audio frame — must stay small
    assert " " not in AvatarState().to_json()


# -- RigManifest -----------------------------------------------------------
def test_default_manifest_validates_clean():
    rig = default_manifest()
    assert rig.validate() == []          # fully authored placeholder
    assert rig.missing_states() == []


def test_clip_for_state_base():
    rig = default_manifest()
    assert rig.clip_for_state(AnimationState.THINKING) == "think"
    assert rig.clip_for_state(AnimationState.SPEAKING) == "talk"


def test_clip_for_state_emotion_override():
    rig = RigManifest.from_dict({
        "states": {"speaking": ["talk"]},
        "state_emotions": {"speaking": {"happy": "talk_happy"}},
    })
    assert rig.clip_for_state(AnimationState.SPEAKING, Emotion.HAPPY) == "talk_happy"
    # no override for tired -> base clip
    assert rig.clip_for_state(AnimationState.SPEAKING, Emotion.TIRED) == "talk"


def test_clip_for_state_missing_returns_empty():
    rig = RigManifest.from_dict({"states": {}})
    assert rig.clip_for_state(AnimationState.IDLE) == ""


def test_idle_variants_cycle_by_index():
    rig = RigManifest.from_dict({"states": {"idle": ["a", "b", "c"]}})
    assert rig.clip_for_state(AnimationState.IDLE, index=0) == "a"
    assert rig.clip_for_state(AnimationState.IDLE, index=4) == "b"  # 4 % 3


def test_string_clip_coerced_to_list():
    rig = RigManifest.from_dict({"states": {"idle": "just_one"}})
    assert rig.clips_for_state(AnimationState.IDLE) == ["just_one"]


def test_expression_and_action_lookups():
    rig = default_manifest()
    assert rig.expression_clip(Emotion.HAPPY) == "face_happy"
    assert rig.expression_clip(Emotion.NEUTRAL) is None   # no face for neutral
    assert rig.action_clip("wave") == "act_wave"
    assert rig.action_clip("backflip") is None


def test_validate_reports_missing_states():
    rig = RigManifest.from_dict({"model": "x.glb", "states": {"idle": ["i"]}})
    warns = rig.validate()
    assert any("listening" in w for w in warns)
    assert any("thinking" in w for w in warns)
    assert any("speaking" in w for w in warns)


def test_load_from_file(tmp_path):
    p = tmp_path / "rig.json"
    p.write_text(json.dumps({"model": "m.glb", "states": {"idle": ["i"]}}))
    rig = RigManifest.load(p)
    assert rig.model == "m.glb"
    assert rig.clips_for_state(AnimationState.IDLE) == ["i"]
