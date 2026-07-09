"""Consolidation tagging prompt (AERO-WRT-001).

Turns a raw event into structured memory tags. Conservative-by-default is baked
into the instructions: humour off unless clearly earned, sensitivity elevated for
personal topics (AERO-WRT-003). S-1 showed gemma4:e4b produces good tags from
this shape with thinking off.
"""

from __future__ import annotations

from aero.cognition.service import ChatMessage

TAGGING_VERSION = "v0.1"

TAGGING_PROMPT = """You extract structured memory tags for Aero, a personal AI companion, \
from one observed event about the user. Respond with ONLY a JSON object, no prose.

Schema:
{
  "summary": string,            // one neutral sentence capturing the event
  "kind": "episodic" | "semantic",  // episodic = a specific moment; semantic = a durable trait/preference
  "topics": [string],           // salient topics/entities
  "people": [string],           // named people involved (empty if none)
  "emotion": string,            // dominant emotion, or "neutral"
  "is_failure": boolean,
  "importance": number,         // 0..1, how much this matters long-term
  "emotional_weight": number,   // 0..1
  "sensitivity": number,        // 0..1. Elevate for health, family, money, relationships, academic failure, emotion
  "roast_value": number,        // 0..1, comic potential IF joking were allowed
  "roast_allowed": boolean,     // ONLY true if the user clearly treats this lightly / self-deprecates. Default false.
  "associations": [string]      // affective/social links: e.g. "denial", "procrastination", "roast_material"
}

Rules:
- Default roast_allowed to false unless the event itself shows the user joking about it.
- Sensitive personal topics get higher sensitivity and roast_allowed=false.
- Keep summary factual and neutral; do not invent details not present.
"""


def tagging_messages(event_text: str) -> list[ChatMessage]:
    return [
        ChatMessage("system", TAGGING_PROMPT),
        ChatMessage("user", event_text),
    ]
