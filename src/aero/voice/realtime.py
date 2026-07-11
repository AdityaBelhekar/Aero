"""Real-time voice loop — hands-free, streaming, barge-in. The reason Aero exists.

No push-to-talk. Aero listens continuously; a VAD decides when you've finished a
thought (``VADSegmenter``); the utterance is transcribed (Moonshine/Whisper),
answered by the memory-in-the-loop agent (two-speed brain), and spoken back
(Kokoro) — and if you start talking while Aero is speaking, it **stops and
listens** (barge-in). That last part is what makes it feel like a conversation
rather than a walkie-talkie.

  mic frames -> VAD endpointing -> STT -> agent(+memory) -> TTS -> speakers
                     ^-------------- barge-in monitors the mic while speaking

``handle_utterance`` (transcribe -> respond) is separated from the hardware
``run`` loop so the core is unit-testable with fakes; ``run`` wires the live mic
and interruptible playback (Windows).
"""

from __future__ import annotations

import sys
import tempfile
import threading
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path

from aero.agent import AeroAgent
from aero.perception.stt import STTService
from aero.voice.loop import looks_garbled
from aero.voice.mic_stream import MicStream, pcm16_to_wav
from aero.voice.speech_intent import intent_from_text
from aero.voice.tts import TTSService
from aero.voice.vad import VAD, EnergyVAD, SegmenterConfig, VADSegmenter


@dataclass
class RealtimeTurn:
    heard: str
    reply: str
    ok: bool = True


class _Player:
    """Async, interruptible playback (Windows winsound). stop() cuts it off."""

    def __init__(self):
        self._thread: threading.Thread | None = None
        self.playing = False

    def play(self, wav_path: str) -> None:
        if sys.platform != "win32":
            return
        import winsound
        self.playing = True

        def _run():
            try:
                winsound.PlaySound(wav_path, winsound.SND_FILENAME)
            finally:
                self.playing = False

        self._thread = threading.Thread(target=_run, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        if sys.platform == "win32":
            import winsound
            with suppress(Exception):
                winsound.PlaySound(None, winsound.SND_PURGE)  # interrupts playback
        self.playing = False


class RealtimeLoop:
    def __init__(
        self,
        agent: AeroAgent,
        stt: STTService,
        tts: TTSService,
        *,
        vad: VAD | None = None,
        mic: MicStream | None = None,
        segmenter: VADSegmenter | None = None,
        barge_in_ms: int = 300,
    ):
        self.agent = agent
        self.stt = stt
        self.tts = tts
        self.vad = vad or EnergyVAD()
        self.mic = mic or MicStream()
        self.segmenter = segmenter or VADSegmenter(
            self.vad, SegmenterConfig(sample_rate=self.mic.sample_rate,
                                      frame_ms=self.mic.frame_ms)
        )
        self.barge_in_ms = barge_in_ms
        self._player = _Player()

    # -- testable core -----------------------------------------------------
    def handle_utterance(self, pcm: bytes) -> RealtimeTurn:
        """Transcribe one captured utterance and get Aero's reply. No audio I/O
        beyond writing a temp WAV for the STT backend — fully unit-testable."""
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            wav = f.name
        try:
            pcm16_to_wav(pcm, wav, self.mic.sample_rate)
            t = self.stt.transcribe(wav)
        finally:
            with suppress(OSError):
                Path(wav).unlink()
        if looks_garbled(t):
            return RealtimeTurn(heard=t.text, reply="", ok=False)
        reply = self.agent.respond(t.text)
        return RealtimeTurn(heard=t.text, reply=reply, ok=True)

    def _speak(self, reply: str) -> None:
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            wav = f.name
        res = self.tts.synthesize(intent_from_text(reply), wav)
        if res.ok:
            self._player.play(wav)
        # temp wav is left for the async player; cleaned on next OS temp sweep.

    # -- live loop (hardware) ---------------------------------------------
    def run(self) -> None:
        if not self.mic.available():
            print("sounddevice not installed — real-time needs a live mic.\n"
                  "  pip install -e \".[realtime]\"  (or use `aero voice` for push-to-talk)")
            return
        speak = self.tts.health_check()
        self.mic.start()
        print("Aero is listening — just talk. Barge in any time. (Ctrl-C to stop)\n")
        barge = 0
        try:
            for frame in self.mic.frames():
                # While Aero is speaking, watch for barge-in and ignore endpointing.
                if self._player.playing:
                    barge = barge + self.mic.frame_ms if \
                        self.vad.is_speech(frame, self.mic.sample_rate) else 0
                    if barge >= self.barge_in_ms:
                        self._player.stop()
                        barge = 0
                        self.segmenter._reset()
                    continue

                utt = self.segmenter.push(frame)
                if utt is None:
                    continue
                turn = self.handle_utterance(utt)
                if not turn.ok:
                    continue
                print(f"  you : {turn.heard}")
                print(f"  aero> {turn.reply}\n")
                if speak and turn.reply:
                    self._speak(turn.reply)
        except KeyboardInterrupt:
            print()
        finally:
            self.mic.stop()
            self._player.stop()
        print("(session logged. run `aero consolidate` to form memory.)")
