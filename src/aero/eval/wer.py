"""Word- and character-error-rate for STT evaluation.

Plain Levenshtein over tokens (WER) and characters (CER). For code-switched
romanised text, WER can look harsh because spelling varies ("nahi"/"nahin"), so
the S-3 harness reports CER alongside — it's the more forgiving, and arguably
more honest, signal for whether the transcript is usable downstream.
"""

from __future__ import annotations

import re
import unicodedata


def normalize_text(s: str) -> str:
    """Lowercase, strip punctuation, collapse whitespace, NFC-normalize.

    Keeps Devanagari and Latin letters; drops punctuation so scoring isn't
    dominated by comma/period disagreements."""
    s = unicodedata.normalize("NFC", s).lower()
    s = re.sub(r"[^\w\sऀ-ॿ]", " ", s)  # keep word chars + Devanagari
    s = re.sub(r"\s+", " ", s).strip()
    return s


def _levenshtein(a: list, b: list) -> int:
    if not a:
        return len(b)
    if not b:
        return len(a)
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cost = 0 if ca == cb else 1
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + cost))
        prev = cur
    return prev[-1]


def wer(reference: str, hypothesis: str) -> float:
    ref = normalize_text(reference).split()
    hyp = normalize_text(hypothesis).split()
    if not ref:
        return 0.0 if not hyp else 1.0
    return _levenshtein(ref, hyp) / len(ref)


def cer(reference: str, hypothesis: str) -> float:
    ref = list(normalize_text(reference).replace(" ", ""))
    hyp = list(normalize_text(hypothesis).replace(" ", ""))
    if not ref:
        return 0.0 if not hyp else 1.0
    return _levenshtein(ref, hyp) / len(ref)
