"""Speech intent — the delivery layer between language and speech (PRD Section 30).

A ``SpeechIntent`` describes not just *what* Aero says but *how*: energy, pace,
volume, pauses, amusement, concern, certainty. The same text ("Aditya.") must be
performable as serious, amused, suspicious, annoyed, or concerned — that's what
this structure exists to control (AERO-VOX-004).

Phase-1 implements the minimal expressible subset (energy, pace, pauses) and maps
it to SSML for the current TTS backend. The richer fields (sarcasm, laugh
intensity, trailing) are carried anyway, even when the current backend can't
express them, so nothing is lost when Aero Voice arrives (forward-compatible).

Fields are 0..1 with 0.5 = neutral, unless noted.
"""

from __future__ import annotations

import html
from dataclasses import dataclass, field


@dataclass
class SpeechIntent:
    text: str

    # --- expressed today (mapped to SSML) ---
    energy: float = 0.5        # low->calm/tired, high->excited (pitch+volume)
    pace: float = 0.5          # slow->deliberate, fast->rushed (rate)
    volume: float = 0.5
    pause_before_ms: int = 0   # lead-in beat, e.g. the "...okay that was clean"
    emphasis_words: list[str] = field(default_factory=list)

    # --- carried now, expressed once Aero Voice lands (forward-compatible) ---
    emotional_tone: str = "neutral"   # amused | serious | concerned | annoyed | ...
    sarcasm: float = 0.0
    amusement: float = 0.0
    concern: float = 0.0
    hesitation: float = 0.0    # adds micro-pauses + trailing
    trailing: float = 0.0      # sentence trails off ("...")
    laugh_intensity: float = 0.0
    certainty: float = 0.5     # low -> hedged delivery

    @classmethod
    def neutral(cls, text: str) -> "SpeechIntent":
        return cls(text=text)

    @classmethod
    def from_tone(cls, text: str, tone: str) -> "SpeechIntent":
        """Convenience presets for Aero's common registers."""
        presets = {
            "amused":    dict(energy=0.65, pace=0.55, amusement=0.7, emotional_tone="amused"),
            "teasing":   dict(energy=0.7, pace=0.6, amusement=0.6, sarcasm=0.4,
                              emotional_tone="teasing"),
            "serious":   dict(energy=0.4, pace=0.45, certainty=0.8, emotional_tone="serious"),
            "concerned": dict(energy=0.4, pace=0.42, concern=0.7, emotional_tone="concerned"),
            "low":       dict(energy=0.3, pace=0.45, emotional_tone="low"),
            "excited":   dict(energy=0.85, pace=0.7, emotional_tone="excited"),
        }
        return cls(text=text, **presets.get(tone, {}))


def _clamp(x: float, lo=0.0, hi=1.0) -> float:
    return max(lo, min(hi, x))


def _rate_tier(pace: float) -> str:
    # SSML named tiers are the most portable across SAPI voices.
    pace = _clamp(pace)
    if pace < 0.2:
        return "x-slow"
    if pace < 0.4:
        return "slow"
    if pace < 0.6:
        return "medium"
    if pace < 0.8:
        return "fast"
    return "x-fast"


def _volume_tier(volume: float) -> str:
    volume = _clamp(volume)
    if volume < 0.2:
        return "x-soft"
    if volume < 0.4:
        return "soft"
    if volume < 0.6:
        return "medium"
    if volume < 0.8:
        return "loud"
    return "x-loud"


def _pitch_pct(energy: float) -> str:
    # Map energy 0..1 to roughly -20%..+20% pitch.
    pct = round((_clamp(energy) - 0.5) * 40)
    return f"{pct:+d}%"


def _emphasize(text: str, words: list[str]) -> str:
    out = html.escape(text)
    for w in words:
        if not w:
            continue
        ew = html.escape(w)
        out = out.replace(ew, f"<emphasis level=\"strong\">{ew}</emphasis>")
    return out


def render_ssml(intent: SpeechIntent, *, lang: str = "en-US") -> str:
    """Render a SpeechIntent to SSML the SAPI backend can speak.

    Only the expressible subset is rendered (rate/volume/pitch/pauses/emphasis);
    the affective fields nudge those knobs (amusement/energy raise pitch, concern
    lowers pace) so tone still shifts even before Aero Voice can voice them fully.
    """
    # Affective nudges into the expressible knobs.
    energy = _clamp(intent.energy + 0.15 * intent.amusement + 0.2 * intent.laugh_intensity)
    pace = _clamp(intent.pace - 0.1 * intent.concern - 0.1 * intent.hesitation)
    volume = _clamp(intent.volume + 0.1 * (intent.energy - 0.5))

    body = _emphasize(intent.text, intent.emphasis_words)

    # Hesitation/trailing add trailing dots + a soft break; low certainty too.
    if intent.trailing > 0.5 or intent.hesitation > 0.5:
        body = body.rstrip(".") + "<break time=\"250ms\"/>..."

    parts = []
    if intent.pause_before_ms > 0:
        parts.append(f"<break time=\"{int(intent.pause_before_ms)}ms\"/>")
    parts.append(
        f"<prosody rate=\"{_rate_tier(pace)}\" "
        f"volume=\"{_volume_tier(volume)}\" "
        f"pitch=\"{_pitch_pct(energy)}\">{body}</prosody>"
    )
    inner = "".join(parts)
    return (
        f"<speak version=\"1.0\" "
        f"xmlns=\"http://www.w3.org/2001/10/synthesis\" xml:lang=\"{lang}\">"
        f"{inner}</speak>"
    )
