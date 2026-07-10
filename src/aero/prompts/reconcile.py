"""Belief reconciliation prompt (AERO-EVO-001/002).

Given an existing belief about the user and a new candidate belief drawn from a
fresh observation, decide their relationship and produce the updated belief. This
is what lets Aero's understanding *evolve* — reinforcing, correcting, or leaving
beliefs alone — instead of accumulating contradictions.
"""

from __future__ import annotations

from aero.cognition.service import ChatMessage

RECONCILE_VERSION = "v0.1"

RECONCILE_PROMPT = """You maintain Aero's evolving beliefs about the user. You are given an \
EXISTING belief (with its confidence) and a NEW observation about the user. Decide how they relate \
and produce the updated belief. Respond with ONLY a JSON object:

{
  "relation": "reinforces" | "contradicts" | "unrelated",
  "statement": string,     // the belief to keep going forward
  "confidence": number,    // 0..1 for the kept belief
  "reason": string         // brief justification
}

Rules:
- "reinforces": the new observation supports the existing belief. Keep the statement \
(refine wording if helpful) and RAISE confidence.
- "contradicts": the new observation conflicts with the existing belief. The statement must be the \
CORRECTED belief that preserves useful history, e.g. "now prefers X, previously preferred Y". \
Set confidence to reflect the new evidence.
- "unrelated": they are about different things. Echo the existing statement and confidence unchanged.
- Never fabricate detail beyond the two inputs.
"""


def reconcile_messages(existing_summary: str, existing_confidence: float,
                       new_summary: str) -> list[ChatMessage]:
    return [
        ChatMessage("system", RECONCILE_PROMPT),
        ChatMessage(
            "user",
            f"EXISTING (confidence {existing_confidence:.2f}): {existing_summary}\n"
            f"NEW: {new_summary}",
        ),
    ]
