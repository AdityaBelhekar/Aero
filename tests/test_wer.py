"""WER/CER utility tests — hermetic, no audio or model."""

from __future__ import annotations

from aero.eval.wer import cer, normalize_text, wer


def test_perfect_match_is_zero():
    assert wer("bhai kaisa hai", "bhai kaisa hai") == 0.0
    assert cer("bhai kaisa hai", "bhai kaisa hai") == 0.0


def test_normalize_strips_punctuation_and_case():
    assert normalize_text("Bhai, kaisa HAI?") == "bhai kaisa hai"


def test_wer_counts_word_edits():
    # one substitution out of three words
    assert wer("open our thing", "open your thing") == 1 / 3


def test_wer_handles_empty_reference():
    assert wer("", "") == 0.0
    assert wer("", "something") == 1.0


def test_cer_is_more_forgiving_than_wer_on_spelling():
    # romanised spelling variant: whole word wrong for WER, few chars for CER
    ref, hyp = "nahi yaar", "nahin yaar"
    assert wer(ref, hyp) == 0.5          # 1 of 2 words differs
    assert cer(ref, hyp) < wer(ref, hyp)  # only one inserted char


def test_devanagari_preserved_in_normalize():
    assert "मला" in normalize_text("मला coffee havi!")
