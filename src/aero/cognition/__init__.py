"""Aero's cognition layer — the interface between Aero and whatever language
model currently powers it.

The model is *not* Aero (PRD Section 2). Everything here sits behind the
``CognitionService`` interface so the underlying model can be swapped — Ollama
today, something else tomorrow — without the rest of Aero noticing. This is the
AERO-ID-002 invariant made concrete: nothing load-bearing lives in the model.
"""

from aero.cognition.service import (
    ChatMessage,
    CognitionService,
    CompletionResult,
    GenerationStats,
)

__all__ = [
    "ChatMessage",
    "CognitionService",
    "CompletionResult",
    "GenerationStats",
]
