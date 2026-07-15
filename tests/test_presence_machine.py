"""Emotion mapping + animation state machine (AERO-PRES-102). Hermetic."""

from __future__ import annotations

from aero.presence.emotion import emotion_from_intent
from aero.presence.state import AnimationState, Emotion
from aero.presence.state_machine import AvatarStateMachine
from aero.voice.speech_intent import SpeechIntent


# -- emotion mapping -------------------------------------------------------
def test_emotion_none_is_neutral():
    assert emotion_from_intent(None) is Emotion.NEUTRAL


def test_emotion_from_named_tones():
    assert emotion_from_intent(SpeechIntent.from_tone("x", "teasing")) is Emotion.TEASING
    assert emotion_from_intent(SpeechIntent.from_tone("x", "concerned")) is Emotion.CONCERNED
    assert emotion_from_intent(SpeechIntent.from_tone("x", "excited")) is Emotion.EXCITED
    assert emotion_from_intent(SpeechIntent.from_tone("x", "low")) is Emotion.TIRED
    assert emotion_from_intent(SpeechIntent.from_tone("x", "amused")) is Emotion.HAPPY


def test_emotion_falls_back_to_numeric_fields():
    # neutral tone, but high concern -> concerned
    assert emotion_from_intent(SpeechIntent("x", concern=0.8)) is Emotion.CONCERNED
    # neutral tone, laughing -> happy
    assert emotion_from_intent(SpeechIntent("x", laugh_intensity=0.7)) is Emotion.HAPPY
    # neutral tone, high energy -> excited
    assert emotion_from_intent(SpeechIntent("x", energy=0.9)) is Emotion.EXCITED
    # neutral tone, low energy -> tired
    assert emotion_from_intent(SpeechIntent("x", energy=0.2)) is Emotion.TIRED
    # plain neutral -> neutral
    assert emotion_from_intent(SpeechIntent("x")) is Emotion.NEUTRAL


# -- state machine priority ------------------------------------------------
def test_default_state_is_idle():
    m = AvatarStateMachine()
    assert m.state.animation is AnimationState.IDLE
    assert m.state.clip == "idle_base"


def test_speaking_wins_over_everything():
    m = AvatarStateMachine()
    s = m.update(mic_hot=True, thinking=True, speaking=True,
                 intent=SpeechIntent.from_tone("yo", "excited"), mouth_open=0.5)
    assert s.animation is AnimationState.SPEAKING
    assert s.emotion is Emotion.EXCITED
    assert s.mouth_open == 0.5
    assert s.clip == "talk"                 # base speaking clip (no emotion override in default rig)


def test_thinking_over_listening():
    m = AvatarStateMachine()
    s = m.update(mic_hot=True, thinking=True)
    assert s.animation is AnimationState.THINKING
    assert s.clip == "think"


def test_listening():
    m = AvatarStateMachine()
    s = m.update(mic_hot=True)
    assert s.animation is AnimationState.LISTENING
    assert s.clip == "listen"


def test_mouth_open_only_while_speaking():
    m = AvatarStateMachine()
    # mouth_open passed but not speaking -> ignored
    s = m.update(thinking=True, mouth_open=0.9)
    assert s.mouth_open == 0.0


def test_mouth_open_clamped():
    m = AvatarStateMachine()
    s = m.update(speaking=True, intent=SpeechIntent("hi"), mouth_open=5.0)
    assert s.mouth_open == 1.0


def test_action_resolves_through_rig():
    m = AvatarStateMachine()
    s = m.update(action="wave")
    assert s.action == "act_wave"           # resolved clip name
    s2 = m.update(action="backflip")        # unknown -> None
    assert s2.action is None


def test_idle_clip_and_tags_injected():
    m = AvatarStateMachine()
    s = m.update(idle_clip="stretch", tags=["night", "gaming"])
    assert s.animation is AnimationState.IDLE
    assert s.clip == "stretch"
    assert s.tags == ["night", "gaming"]


def test_emotion_override_clip_used_when_authored():
    from aero.presence.rig import RigManifest
    rig = RigManifest.from_dict({
        "states": {"speaking": ["talk"], "idle": ["idle"], "listening": ["l"],
                   "thinking": ["t"]},
        "state_emotions": {"speaking": {"happy": "talk_happy"}},
    })
    m = AvatarStateMachine(rig)
    s = m.update(speaking=True, intent=SpeechIntent.from_tone("haha", "amused"))
    assert s.emotion is Emotion.HAPPY
    assert s.clip == "talk_happy"
