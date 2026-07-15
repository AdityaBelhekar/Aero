"""The brain router — two-speed cost/privacy/capability policy (AERO-BRAIN-303).

v0.2's "two-speed brain" (cheap-local for reflex, strong-cloud on demand) survives
v0.3 as a *router* that is itself a ``CognitionService`` — so the rest of Aero keeps
programming against the one interface and never knows two brains are in play.

Policy:

  * ``chat``          -> the **primary** brain (the strong one you talk to).
  * ``complete_json`` -> the **reflex** brain (the cheapest reliable one). The
    consolidation tagging pass (AERO-WRT-001) runs constantly in the background;
    sending it to a paid frontier model would burn money for a structured-output
    job a small local model does fine. Cheapest-reliable-by-default controls cost.
  * **privacy** — with ``private_only`` set, a non-private primary is refused and
    everything routes to the (local) reflex brain. Personal talk never leaves the
    device unless the user explicitly picked a cloud primary without this guard.
  * **degrade, never die** (Rule 9) — if the primary brain errors mid-call
    (offline, out of credits), ``chat`` transparently falls back to the reflex
    brain rather than failing the turn.

Single-brain mode: ``primary=None`` makes the reflex brain handle everything —
i.e. exactly today's behaviour, so the router is a safe drop-in default.
"""

from __future__ import annotations

from typing import Any

from aero.cognition.service import (
    ChatMessage,
    CognitionService,
    CompletionResult,
)


class BrainRouter(CognitionService):
    def __init__(
        self,
        reflex: CognitionService,
        primary: CognitionService | None = None,
        *,
        private_only: bool = False,
        primary_is_private: bool = True,
    ):
        """``reflex`` is the cheap/private always-available brain (never None).
        ``primary`` is the strong brain for conversation; None -> single-brain.
        ``primary_is_private`` records whether the primary keeps data on-device;
        combined with ``private_only`` it decides whether the primary is allowed."""
        self.reflex = reflex
        # Privacy guard: a non-private primary is disallowed under private_only.
        if primary is not None and private_only and not primary_is_private:
            primary = None
        self.primary = primary
        self.private_only = private_only
        #: Set True whenever the last chat() had to fall back off the primary.
        #: Lets the UI say "cloud brain was down — used local" (PRD §27 honesty).
        self.last_fallback = False

    @property
    def model_name(self) -> str:  # type: ignore[override]
        if self.primary is None:
            return f"router[{self.reflex.model_name}]"
        return f"router[chat={self.primary.model_name} tag={self.reflex.model_name}]"

    # -- CognitionService --------------------------------------------------
    def chat(
        self,
        messages: list[ChatMessage],
        *,
        temperature: float = 0.7,
        max_tokens: int | None = None,
    ) -> CompletionResult:
        self.last_fallback = False
        if self.primary is None:
            return self.reflex.chat(messages, temperature=temperature, max_tokens=max_tokens)
        try:
            return self.primary.chat(
                messages, temperature=temperature, max_tokens=max_tokens
            )
        except Exception:
            # Primary brain unreachable/broke — degrade to the reflex brain
            # instead of failing the turn (Rule 9). The caller can read
            # last_fallback to tell the user.
            self.last_fallback = True
            return self.reflex.chat(
                messages, temperature=temperature, max_tokens=max_tokens
            )

    def complete_json(
        self,
        messages: list[ChatMessage],
        *,
        temperature: float = 0.2,
        max_tokens: int | None = None,
    ) -> tuple[dict[str, Any] | list[Any] | None, CompletionResult]:
        # Structured tagging always goes to the cheapest reliable brain, whatever
        # the conversational primary is. This is the cost-control lever.
        return self.reflex.complete_json(
            messages, temperature=temperature, max_tokens=max_tokens
        )

    def health_check(self) -> bool:
        # The router is usable as long as the reflex brain (the fallback for
        # everything) is reachable. A dead primary just means degraded chat.
        return self.reflex.health_check()
