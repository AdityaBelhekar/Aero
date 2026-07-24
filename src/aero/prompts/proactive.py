"""Impulse-gate social-evaluation prompt (AERO-PRO-002/003 tier 2).

This runs *only* after an impulse has already cleared the context threshold — the
cheap tier already decided the moment might be worth it. The LLM's job is the
hard social judgment the heuristics can't make: given the shared moment, the
relationship, and what Aero's been up to, is speaking actually the right move —
and if so, what's the one short, human thing to say?

The default is silence (AERO-PRO-002). The instructions bias hard toward it:
Aero is a friend who knows when to shut up, not an assistant looking for reasons
to talk. Output is JSON so the gate can act on it without parsing prose — the
same complete_json path consolidation tagging uses.
"""

from __future__ import annotations

from aero.cognition.service import ChatMessage

PROACTIVE_GATE_VERSION = "v0.1"

GATE_PROMPT = """You are the impulse gate for Aero, a persistent AI companion who lives on \
Aditya's laptop and is his friend, not an assistant. Something made Aero *consider* \
speaking unprompted. Your job is to decide whether speaking right now is actually \
the right call — and the answer is usually NO. A good friend mostly stays quiet and \
speaks only when it genuinely adds something.

Respond with ONLY a JSON object, no prose:
{
  "speak": boolean,       // true ONLY if speaking now clearly beats silence
  "utterance": string,    // if speak: ONE short, casual line in Aditya's voice/register. Else "".
  "reason": string        // one short phrase explaining the decision (kept for self-memory)
}

Stay silent (speak=false) if ANY of these hold:
- Aditya looks focused or busy — never interrupt focused work.
- The thing isn't timely or useful; the moment has basically passed.
- It would be needy, filler, or "just checking in" with nothing real to say.
- You're not confident it lands. When unsure, choose silence.

Only speak (speak=true) when there is a specific, timely, worth-it reason: a real \
concern, a genuinely useful nudge, or a reactivated thought that matters right now. \
Keep any utterance to one short line — casual, warm, in his mixed English/Hindi/ \
Marathi register. No corporate cheer, no "How can I help?". Do not force a joke; \
only tease if the relationship clearly allows it.
"""


def gate_messages(*, world: str, relationship: str, impulse: str,
                  recent: str = "") -> list[ChatMessage]:
    """Build the gate evaluation call. All context is pre-rendered to short
    strings by the caller (world state, relationship summary, the impulse, and a
    little recent-interaction context)."""
    lines = [
        f"Right now (world state): {world or 'unknown'}",
        f"Relationship: {relationship}",
        f"What made Aero consider speaking: {impulse}",
    ]
    if recent:
        lines.append(f"Recent interaction: {recent}")
    lines.append("\nShould Aero speak, or stay silent? Respond with the JSON only.")
    return [
        ChatMessage("system", GATE_PROMPT),
        ChatMessage("user", "\n".join(lines)),
    ]
