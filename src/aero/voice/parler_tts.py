"""Indic Parler-TTS backend — Aero's expressive Indic voice (PRD Section 29).

`ai4bharat/indic-parler-tts` is a 0.9B Parler-style TTS: you don't pick a fixed
voice profile, you *describe* the speaker in natural language ("A young male
Indian voice, warm and casual...") and the model performs it. That maps cleanly
onto Aero's `SpeechIntent` — energy, pace and emotional tone become words in the
description — so Aero's delivery control survives into the audio.

It runs on the `parler_tts` package (+ transformers + soundfile), an optional
heavy dependency: importing this module never requires it, only constructing and
using the backend does. On CPU generation is LLM-slow (seconds per sentence — the
model is 0.9B); the CPU-friendly fallback is AI4Bharat's VITS (`vits_rasa_13`).
Kept behind the same `TTSService` interface, so `settings.build_tts()` and
`aero voices --engine parler` swap it in with no other changes.
"""

from __future__ import annotations

import sys
import tempfile
import time
from pathlib import Path

from aero.voice.speech_intent import SpeechIntent
from aero.voice.tts import SpeechResult, TTSService

DEFAULT_MODEL = "ai4bharat/indic-parler-tts"

# Aero is a young Indian male: warm, casual, close-mic'd. The "very clear... no
# background noise" tail is Parler's lever for clean studio-quality output.
AERO_BASE_VOICE = (
    "A young Indian male speaker with a warm, casual and friendly voice. "
    "He speaks clearly and naturally, close to the microphone, "
    "with very high recording quality and no background noise."
)


def _intent_to_description(intent: SpeechIntent, base_voice: str = AERO_BASE_VOICE) -> str:
    """Turn a SpeechIntent's delivery fields into Parler's prose voice-description.

    Parler has no numeric knobs — it reads adjectives. So map the 0..1 fields to
    words: energy -> flat..animated, pace -> slow..fast, and let a strong
    emotional_tone name itself. Neutral fields add nothing (keeps prompts short).
    """
    bits: list[str] = []

    if intent.energy <= 0.35:
        bits.append("His delivery is calm and low-energy")
    elif intent.energy >= 0.7:
        bits.append("His delivery is animated and expressive")

    if intent.pace <= 0.4:
        bits.append("he speaks slowly and deliberately")
    elif intent.pace >= 0.65:
        bits.append("he speaks at a quick, lively pace")

    tone = (intent.emotional_tone or "").strip().lower()
    if tone and tone != "neutral":
        bits.append(f"his tone is {tone}")

    if not bits:
        return base_voice
    return f"{base_voice} {', '.join(bits)}."


class ParlerTTS(TTSService):
    def __init__(
        self,
        base_voice: str = AERO_BASE_VOICE,
        *,
        model_id: str = DEFAULT_MODEL,
        device: str = "cpu",
    ):
        self.voice_name = "aero-parler"
        self.base_voice = base_voice
        self.model_id = model_id
        self.device = device
        self._model = None
        self._tokenizer = None
        self._desc_tokenizer = None

    # -- model (lazy, heavy) ----------------------------------------------
    def _ensure_model(self):
        if self._model is None:
            from parler_tts import ParlerTTSForConditionalGeneration
            from transformers import AutoTokenizer

            model = ParlerTTSForConditionalGeneration.from_pretrained(
                self.model_id
            ).to(self.device)
            self._model = model
            self._tokenizer = AutoTokenizer.from_pretrained(self.model_id)
            self._desc_tokenizer = AutoTokenizer.from_pretrained(
                model.config.text_encoder._name_or_path
            )
        return self._model

    def _render(self, text: str, description: str, out_path: str) -> None:
        """Generate audio for `text` performed as `description`, write to WAV.

        Isolated so tests can mock the whole heavy path (model + soundfile) the
        way test_svara mocks the HTTP call."""
        import soundfile as sf

        model = self._ensure_model()
        desc_ids = self._desc_tokenizer(description, return_tensors="pt").to(self.device)
        prompt_ids = self._tokenizer(text, return_tensors="pt").to(self.device)
        generation = model.generate(
            input_ids=desc_ids.input_ids,
            attention_mask=desc_ids.attention_mask,
            prompt_input_ids=prompt_ids.input_ids,
            prompt_attention_mask=prompt_ids.attention_mask,
        )
        audio = generation.cpu().numpy().squeeze()
        sf.write(out_path, audio, model.config.sampling_rate)

    # -- TTSService --------------------------------------------------------
    def synthesize(self, intent: SpeechIntent, out_path: str) -> SpeechResult:
        description = _intent_to_description(intent, self.base_voice)
        t0 = time.perf_counter()
        try:
            self._render(intent.text, description, out_path)
        except Exception as e:  # model load / generation / write failure
            return SpeechResult(None, time.perf_counter() - t0, ok=False, error=str(e))
        return SpeechResult(out_path, time.perf_counter() - t0)

    def speak(self, intent: SpeechIntent) -> SpeechResult:
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            wav = f.name
        res = self.synthesize(intent, wav)
        if res.ok and sys.platform == "win32":
            try:
                import winsound
                winsound.PlaySound(wav, winsound.SND_FILENAME)
            except Exception as e:
                res = SpeechResult(wav, res.seconds_compute, ok=False, error=str(e))
        try:
            Path(wav).unlink()
        except OSError:
            pass
        return res

    def health_check(self) -> bool:
        try:
            import parler_tts  # noqa: F401
            import soundfile  # noqa: F401
            import transformers  # noqa: F401
            return True
        except Exception:
            return False
