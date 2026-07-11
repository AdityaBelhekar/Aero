"""The voice conversation loop — Aero's senses wired end to end.

    mic (push-to-talk) -> Whisper STT -> AeroAgent (gemma4 + memory)
        -> speech intent -> TTS -> speakers

Everything upstream of this is already built and tested; this is the wiring. STT
is loaded once and kept warm; the agent carries memory-in-the-loop; replies are
spoken with a heuristic delivery (Milestone 4 will have the model set intent
directly).

A ``text`` mode types instead of speaks — useful when no mic is available and for
driving the loop in tests without audio hardware.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from aero.agent import AeroAgent
from aero.perception.stt import STTService, Transcript
from aero.voice.mic import Recorder
from aero.voice.speech_intent import intent_from_text
from aero.voice.tts import TTSService


def looks_garbled(t: Transcript) -> bool:
    """Guard the catastrophic-STT case (S-3 finding): empty, or absurdly long
    output relative to audio, means we should ask the user to repeat rather than
    feed garbage into memory."""
    text = t.text.strip()
    if not text:
        return True
    if t.seconds_audio > 0 and len(text) > t.seconds_audio * 60:
        return True  # ~60 chars/sec of speech is implausible -> garbage
    return False


@dataclass
class VoiceTurn:
    heard: str
    reply: str
    ok: bool = True


class VoiceLoop:
    def __init__(
        self,
        agent: AeroAgent,
        stt: STTService,
        tts: TTSService,
        *,
        recorder: Recorder | None = None,
    ):
        self.agent = agent
        self.stt = stt
        self.tts = tts
        self.recorder = recorder or Recorder()

    # -- one turn (audio) --------------------------------------------------
    def transcribe_wav(self, wav_path: str) -> Transcript:
        return self.stt.transcribe(wav_path)

    def handle_text(self, user_text: str, *, speak: bool = True) -> VoiceTurn:
        """Core turn: text in -> reply out (+ optional speech). Shared by voice
        and text modes so both go through identical agent/memory/intent paths."""
        reply = self.agent.respond(user_text)
        if speak and self.tts.health_check():
            self.tts.speak(intent_from_text(reply))
        return VoiceTurn(heard=user_text, reply=reply)

    def handle_wav(self, wav_path: str, *, speak: bool = True) -> VoiceTurn:
        t = self.transcribe_wav(wav_path)
        if looks_garbled(t):
            return VoiceTurn(heard=t.text, reply="", ok=False)
        return self.handle_text(t.text, speak=speak)

    # -- interactive drivers ----------------------------------------------
    def run_text(self, *, speak: bool = True) -> None:
        """Type to Aero; Aero speaks back. Fallback when there's no mic."""
        print("Aero voice loop (text mode). Type to talk; 'exit' to leave.\n")
        while True:
            try:
                user = input("you> ").strip()
            except (EOFError, KeyboardInterrupt):
                print(); break
            if user.lower() in {"exit", "quit"}:
                break
            if not user:
                continue
            turn = self.handle_text(user, speak=speak)
            print(f"aero> {turn.reply}\n")

    def run_voice(self) -> None:
        """Push-to-talk: Enter to start, Enter to stop; Aero hears and replies."""
        if not self.recorder.available():
            print("No microphone available — falling back to text mode.\n")
            return self.run_text()
        print(f"Aero voice loop. Mic: {self.recorder.device}")
        print("Press Enter to talk, Enter again to stop. Type 'exit' to leave.\n")
        while True:
            try:
                cmd = input("[Enter]=talk  (or 'exit') > ").strip().lower()
            except (EOFError, KeyboardInterrupt):
                print(); break
            if cmd in {"exit", "quit"}:
                break
            if not self.recorder.start():
                print("  (mic start failed; text mode)\n")
                return self.run_text()
            try:
                input("  🎤 recording... [Enter to stop] ")
            except (EOFError, KeyboardInterrupt):
                pass
            res = self.recorder.stop()
            if not res.ok:
                print(f"  (didn't catch that: {res.error})\n")
                continue
            turn = self.handle_wav(res.wav_path)
            try:
                Path(res.wav_path).unlink()
            except OSError:
                pass
            if not turn.ok:
                print("  (couldn't make that out — say it again?)\n")
                continue
            print(f"  heard: {turn.heard}")
            print(f"  aero> {turn.reply}\n")
