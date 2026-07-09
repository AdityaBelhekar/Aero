"""Working-set assembler (AERO-WM-001/002).

Builds the exact context handed to the model for one turn: persona + core
identity + world state + recalled memories + recent conversation. The full
archive never enters the window — only what this turn needs. A rough token
budget keeps us inside E4B's comfortable envelope (AERO-WM-002); when the budget
is tight, conversation history is trimmed before memories, and memories before
identity.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from aero.cognition.service import ChatMessage
from aero.memory.models import Retrieved
from aero.memory.store import MemoryStore
from aero.prompts.persona import AERO_PERSONA

# Rough chars-per-token for budget math (conservative for mixed scripts).
CHARS_PER_TOKEN = 3.5
DEFAULT_TOKEN_BUDGET = 6000


@dataclass
class Turn:
    role: str  # 'user' | 'assistant'
    content: str


@dataclass
class WorldState:
    """Minimal Phase-0 world state (AERO-WS-001). Tier-0 signals only for now."""

    time_str: str | None = None
    active_app: str | None = None
    window_title: str | None = None
    extra: dict = field(default_factory=dict)

    def render(self) -> str:
        bits = []
        if self.time_str:
            bits.append(f"time: {self.time_str}")
        if self.active_app:
            bits.append(f"active app: {self.active_app}")
        if self.window_title:
            bits.append(f"window: {self.window_title}")
        for k, v in self.extra.items():
            bits.append(f"{k}: {v}")
        return "; ".join(bits)


def _est_tokens(text: str) -> int:
    return int(len(text) / CHARS_PER_TOKEN) + 1


def _render_memories(recalled: list[Retrieved]) -> str:
    if not recalled:
        return ""
    lines = [f"- {r.memory.summary}" for r in recalled]
    return "Things you remember that may be relevant right now:\n" + "\n".join(lines)


def build_system_prompt(
    store: MemoryStore,
    recalled: list[Retrieved],
    world: WorldState | None,
) -> str:
    parts = [AERO_PERSONA]

    core = store.core_memories()
    if core:
        ident = "\n".join(f"- {m.summary}" for m in core[:20])
        parts.append(f"What you know about Aditya and your relationship:\n{ident}")

    boundaries = store.active_boundaries()
    if boundaries:
        bl = "\n".join(f"- {b['rule']}: {b['topic_or_memory']}" for b in boundaries)
        parts.append(f"Hard boundaries (never violate):\n{bl}")

    if world and world.render():
        parts.append(f"Right now: {world.render()}")

    mem_block = _render_memories(recalled)
    if mem_block:
        parts.append(mem_block)

    return "\n\n".join(parts)


def assemble(
    store: MemoryStore,
    recalled: list[Retrieved],
    conversation: list[Turn],
    *,
    world: WorldState | None = None,
    token_budget: int = DEFAULT_TOKEN_BUDGET,
) -> list[ChatMessage]:
    """Return the message list for one model call, within the token budget."""
    system = build_system_prompt(store, recalled, world)
    messages = [ChatMessage("system", system)]

    used = _est_tokens(system)
    # Add conversation turns most-recent-first until the budget is hit, then
    # restore chronological order.
    kept: list[Turn] = []
    for turn in reversed(conversation):
        cost = _est_tokens(turn.content)
        if used + cost > token_budget and kept:
            break
        used += cost
        kept.append(turn)
    for turn in reversed(kept):
        messages.append(ChatMessage(turn.role, turn.content))  # type: ignore[arg-type]

    return messages
