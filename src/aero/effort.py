"""Turn effort routing — Aero's two speeds (reflex vs reflection).

The same brain (gemma4:e4b) answers every turn; what changes is how much work a
turn earns. Basic banter ("sup", "haha", "open spotify") shouldn't drag Aero's
whole associative memory into the prompt or generate an essay — that's what made
casual talk feel slow on CPU. Deep or personal turns ("what should I do about the
Rohan thing", "remember when…") get the full memory-in-the-loop treatment.

CRITICAL: this is NOT "memory off for reflex". Core identity + relationship
(store.core_memories) is ALWAYS in the prompt (see working_set). Reflex only
skips the *expensive graph-spread retrieval*, still doing a cheap vector recall
(retrieval.LIGHT_CONFIG). Memory is the point of Aero — it's never absent, just
not re-excavated for a one-word exchange.

Bias is memory-first: when in doubt, go deep. Reflex must be *clearly* trivial.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# Words that mean "this turn reaches into the past / the relationship" -> always
# deep, no matter how short. Cheap substring/word checks, no model call.
_DEEP_MARKERS = (
    "remember", "remind", "recall", "forgot", "forget", "last time", "earlier",
    "yesterday", "the other day", "you said", "we talked", "we discussed",
    "did i", "have i", "what did", "when did", "why did", "who is", "who's",
    "tell me about", "what do you think", "should i", "what should", "advice",
    "opinion", "feel", "feeling", "worried", "stressed", "help me decide",
)

# Clearly-trivial openers/acks -> reflex candidates (still must pass length gate).
_REFLEX_MARKERS = (
    "hi", "hey", "yo", "sup", "hello", "hii", "heyy", "ok", "okay", "k",
    "haha", "lol", "lmao", "nice", "cool", "great", "thanks", "thx", "ty",
    "bye", "gn", "good night", "gm", "good morning", "sure", "yep", "yeah",
    "no", "nope", "wow", "damn", "bro", "bhai",
)

_WORD_RE = re.compile(r"[a-z0-9']+")

# Max words for a turn to still qualify as reflex (short = basic).
REFLEX_MAX_WORDS = 6


@dataclass(frozen=True)
class Effort:
    name: str            # "reflex" | "deep"
    use_deep_memory: bool
    max_tokens: int
    reason: str

    @property
    def is_reflex(self) -> bool:
        return self.name == "reflex"


DEEP = lambda reason: Effort("deep", True, 300, reason)          # noqa: E731
REFLEX = lambda reason: Effort("reflex", False, 120, reason)     # noqa: E731


def classify(user_text: str) -> Effort:
    """Route one user turn to reflex or deep. Memory-first: default deep."""
    text = user_text.strip().lower()
    if not text:
        return REFLEX("empty")

    # Any explicit reach into memory / anything personal -> full treatment.
    for marker in _DEEP_MARKERS:
        if marker in text:
            return DEEP(f"deep marker: {marker!r}")

    words = _WORD_RE.findall(text)

    # A real question of any substance deserves memory; a bare "you up?" doesn't.
    if "?" in text and len(words) > REFLEX_MAX_WORDS:
        return DEEP("substantive question")

    # Long turns carry content worth grounding in memory.
    if len(words) > REFLEX_MAX_WORDS:
        return DEEP(f"long turn ({len(words)} words)")

    # Short turn: reflex only if it *looks* like banter/an ack/command; otherwise
    # stay deep (memory-first — never starve a real turn to save a beat).
    first = words[0] if words else ""
    if first in _REFLEX_MARKERS or text in _REFLEX_MARKERS:
        return REFLEX(f"short banter ({first!r})")
    if first in ("open", "close", "play", "pause", "stop", "mute", "start"):
        return REFLEX(f"simple command ({first!r})")

    return DEEP("short but not clearly trivial")
