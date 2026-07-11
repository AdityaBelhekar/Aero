"""Effort routing (reflex vs deep) — the two-speed brain, memory-first.

Verifies casual turns go reflex (fast, light retrieval) while anything reaching
into memory or of substance goes deep. Bias is memory-first: uncertain -> deep.
"""

from __future__ import annotations

import pytest

from aero.effort import REFLEX_MAX_WORDS, classify


@pytest.mark.parametrize("text", [
    "sup", "hey", "yo bhai", "haha", "lol", "ok", "thanks", "gn", "cool",
    "open spotify", "play music", "nice one",
])
def test_basic_banter_is_reflex(text):
    e = classify(text)
    assert e.is_reflex, f"{text!r} -> {e.reason}"
    assert e.use_deep_memory is False
    assert e.max_tokens < 300


@pytest.mark.parametrize("text", [
    "remember what I told you about the assignment?",
    "what do you think I should do about Rohan",
    "you said you'd remind me about the deadline",
    "I'm kind of stressed about this, help me decide",
    "did I mention the coffee thing earlier",
    "tell me about my project",
])
def test_memory_reaching_turns_go_deep(text):
    e = classify(text)
    assert e.name == "deep", f"{text!r} -> {e.reason}"
    assert e.use_deep_memory is True


def test_deep_markers_win_even_when_short():
    # "remember?" is short but reaches into memory -> must be deep.
    assert classify("remember?").name == "deep"


def test_long_casual_turn_still_deep():
    # Long turns carry content worth grounding, even without a keyword.
    text = "so today was pretty wild the whole squad showed up and we grinded ranked"
    e = classify(text)
    assert len(text.split()) > REFLEX_MAX_WORDS
    assert e.name == "deep"


def test_short_unknown_turn_defaults_deep():
    # Memory-first: an ambiguous short turn is NOT starved of memory.
    assert classify("the plan").name == "deep"


def test_empty_is_reflex():
    assert classify("   ").is_reflex


def test_effort_shape():
    e = classify("sup")
    assert e.name == "reflex" and isinstance(e.reason, str) and e.reason
