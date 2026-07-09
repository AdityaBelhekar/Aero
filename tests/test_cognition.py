"""Cognition-layer tests.

The stats math runs everywhere. The live-model tests skip automatically when
Ollama or gemma4:e4b isn't available, so CI without a GPU box stays green while
a dev machine still exercises the real path.
"""

from __future__ import annotations

import pytest

from aero.cognition.ollama_backend import OllamaCognition
from aero.cognition.service import ChatMessage, GenerationStats


def test_tokens_per_second_prefers_eval_window():
    # 100 tokens generated in a 5s eval window -> 20 tok/s, regardless of the
    # noisier total/load figures.
    s = GenerationStats(
        prompt_tokens=50,
        completion_tokens=100,
        total_seconds=12.0,
        load_seconds=2.0,
        eval_seconds=5.0,
    )
    assert s.tokens_per_second == pytest.approx(20.0)


def test_tokens_per_second_falls_back_without_eval_window():
    s = GenerationStats(
        prompt_tokens=50, completion_tokens=100, total_seconds=12.0, load_seconds=2.0
    )
    # (12 - 2) = 10s -> 10 tok/s
    assert s.tokens_per_second == pytest.approx(10.0)


def test_thinking_off_by_default():
    assert OllamaCognition().think is False


# -- live tests (skipped unless the model is actually available) -----------
_llm = OllamaCognition()
_have_model = _llm.health_check()
live = pytest.mark.skipif(not _have_model, reason="gemma4:e4b not available via Ollama")


@live
def test_live_chat_returns_content():
    res = _llm.chat([ChatMessage("user", "reply with exactly: ok")], max_tokens=20)
    assert res.text.strip() != ""
    assert res.stats.completion_tokens > 0


@live
def test_live_json_tagging():
    parsed, _ = _llm.complete_json(
        [
            ChatMessage("system", 'Respond ONLY with JSON {"ok": true}.'),
            ChatMessage("user", "go"),
        ],
        max_tokens=50,
    )
    assert isinstance(parsed, dict)
