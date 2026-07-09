"""The CognitionService interface.

Deliberately small: chat completion, and JSON-constrained completion (which
consolidation's tagging pass depends on — AERO-WRT-001). Backends implement this;
the rest of Aero programs against the interface only.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Literal

Role = Literal["system", "user", "assistant"]


@dataclass(frozen=True)
class ChatMessage:
    role: Role
    content: str


@dataclass(frozen=True)
class GenerationStats:
    """Timing/throughput for one generation. Feeds the budget checks in W-2."""

    prompt_tokens: int
    completion_tokens: int
    total_seconds: float
    load_seconds: float = 0.0

    @property
    def tokens_per_second(self) -> float:
        # Throughput on the *generated* tokens, excluding model load time.
        gen_seconds = max(self.total_seconds - self.load_seconds, 1e-9)
        return self.completion_tokens / gen_seconds


@dataclass(frozen=True)
class CompletionResult:
    text: str
    stats: GenerationStats
    raw: dict[str, Any] | None = None


class CognitionService(ABC):
    """What Aero needs from a language model, and nothing more."""

    #: Human-readable identifier of the active model (for provenance/logs).
    model_name: str

    @abstractmethod
    def chat(
        self,
        messages: list[ChatMessage],
        *,
        temperature: float = 0.7,
        max_tokens: int | None = None,
    ) -> CompletionResult:
        """Standard multi-turn completion."""

    @abstractmethod
    def complete_json(
        self,
        messages: list[ChatMessage],
        *,
        temperature: float = 0.2,
        max_tokens: int | None = None,
    ) -> tuple[dict[str, Any] | list[Any] | None, CompletionResult]:
        """Completion constrained to emit valid JSON.

        Returns the parsed object (or ``None`` if the model failed to produce
        valid JSON) alongside the raw result. Consolidation tagging lives or
        dies on this working reliably — hence it's a first-class method.
        """

    @abstractmethod
    def health_check(self) -> bool:
        """True if the backend is reachable and the model is available."""
