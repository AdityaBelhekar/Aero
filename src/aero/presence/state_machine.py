"""AvatarStateMachine — turn Aero's live signals into an AvatarState (AERO-PRES-102).

The overlay is dumb; this is where "what is Aero doing right now" is decided, each
tick, from the same signals the voice loop already produces:

    speaking (TTS audio playing)  -> SPEAKING  + emotion(from intent) + lip-sync
    thinking (brain generating)   -> THINKING
    mic hot  (PTT held / wake)    -> LISTENING
    otherwise                     -> IDLE   (ambient.py fills in fidgets/mood)

Priority is top-down: he can't listen while he's talking. The resolved clip name
comes from the RigManifest so the overlay needs zero mapping knowledge. One-shot
actions (wave/facepalm/point) ride along on any state and fire once.
"""

from __future__ import annotations

from aero.presence.emotion import emotion_from_intent
from aero.presence.rig import RigManifest, default_manifest
from aero.presence.state import AnimationState, AvatarState, Emotion
from aero.voice.speech_intent import SpeechIntent


class AvatarStateMachine:
    def __init__(self, rig: RigManifest | None = None):
        self.rig = rig or default_manifest()
        #: last emitted state, so callers/overlay can diff and only push changes
        self.state = AvatarState(clip=self.rig.clip_for_state(AnimationState.IDLE))
        self._idle_index = 0

    def update(
        self,
        *,
        mic_hot: bool = False,
        thinking: bool = False,
        speaking: bool = False,
        intent: SpeechIntent | None = None,
        mouth_open: float = 0.0,
        action: str | None = None,
        idle_clip: str | None = None,
        tags: list[str] | None = None,
    ) -> AvatarState:
        """Compute the current AvatarState from live signals and store it.

        ``idle_clip``/``tags`` let the ambient scheduler (M9.3) inject a chosen
        fidget + world-state tags for the IDLE state without this machine needing
        to know about time-of-day or mood."""
        if speaking:
            emotion = emotion_from_intent(intent)
            anim = AnimationState.SPEAKING
            clip = self.rig.clip_for_state(anim, emotion)
            mouth = max(0.0, min(1.0, mouth_open))
        elif thinking:
            emotion, anim, mouth = Emotion.NEUTRAL, AnimationState.THINKING, 0.0
            clip = self.rig.clip_for_state(anim)
        elif mic_hot:
            emotion, anim, mouth = Emotion.NEUTRAL, AnimationState.LISTENING, 0.0
            clip = self.rig.clip_for_state(anim)
        else:
            emotion, anim, mouth = Emotion.NEUTRAL, AnimationState.IDLE, 0.0
            clip = idle_clip or self.rig.clip_for_state(anim)

        resolved_action = self.rig.action_clip(action) if action else None

        self.state = AvatarState(
            animation=anim,
            emotion=emotion,
            clip=clip,
            action=resolved_action,
            mouth_open=mouth,
            tags=list(tags or []),
        )
        return self.state
