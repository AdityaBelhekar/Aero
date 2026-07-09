"""Ollama-backed CognitionService.

Talks to a local Ollama daemon over its HTTP API (default http://localhost:11434)
using only the standard library, so the base install stays dependency-free.

Ollama is a llama.cpp server under the hood, which keeps us aligned with the
implementation plan's stack while giving us a clean API and model management for
free. The default model is ``gemma4:e4b`` — Aero's core model direction.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any

from aero.cognition.service import (
    ChatMessage,
    CognitionService,
    CompletionResult,
    GenerationStats,
)

DEFAULT_HOST = "http://localhost:11434"
DEFAULT_MODEL = "gemma4:e4b"


class OllamaCognition(CognitionService):
    def __init__(
        self,
        model_name: str = DEFAULT_MODEL,
        *,
        host: str = DEFAULT_HOST,
        timeout: float = 120.0,
        think: bool = False,
    ):
        self.model_name = model_name
        self.host = host.rstrip("/")
        self.timeout = timeout
        # Gemma 4 E4B is a reasoning model: left on, it spends the whole token
        # budget on a hidden chain-of-thought and returns empty content. Aero
        # wants fast, in-character replies, so thinking is OFF by default
        # (latency budgets, PRD Section 24). Flip per-call where deep reasoning
        # genuinely helps (e.g. the impulse gate).
        self.think = think

    # -- HTTP plumbing -----------------------------------------------------
    def _post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            f"{self.host}{path}",
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=self.timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))

    def _chat_raw(
        self,
        messages: list[ChatMessage],
        *,
        temperature: float,
        max_tokens: int | None,
        fmt: str | dict | None = None,
    ) -> dict[str, Any]:
        options: dict[str, Any] = {"temperature": temperature}
        if max_tokens is not None:
            options["num_predict"] = max_tokens
        payload: dict[str, Any] = {
            "model": self.model_name,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "stream": False,
            "think": self.think,  # top-level toggle for reasoning models
            "options": options,
        }
        if fmt is not None:
            payload["format"] = fmt  # "json" or a JSON schema — Ollama-constrained decode
        return self._post("/api/chat", payload)

    @staticmethod
    def _stats(raw: dict[str, Any]) -> GenerationStats:
        # Ollama returns nanosecond counters.
        ns = 1e9
        total = raw.get("total_duration", 0) / ns
        load = raw.get("load_duration", 0) / ns
        eval_s = raw.get("eval_duration", 0) / ns  # generation-only window
        return GenerationStats(
            prompt_tokens=raw.get("prompt_eval_count", 0),
            completion_tokens=raw.get("eval_count", 0),
            total_seconds=total or 1e-9,
            load_seconds=load,
            eval_seconds=eval_s,
        )

    # -- CognitionService --------------------------------------------------
    def chat(
        self,
        messages: list[ChatMessage],
        *,
        temperature: float = 0.7,
        max_tokens: int | None = None,
    ) -> CompletionResult:
        raw = self._chat_raw(messages, temperature=temperature, max_tokens=max_tokens)
        text = raw.get("message", {}).get("content", "")
        return CompletionResult(text=text, stats=self._stats(raw), raw=raw)

    def complete_json(
        self,
        messages: list[ChatMessage],
        *,
        temperature: float = 0.2,
        max_tokens: int | None = None,
    ) -> tuple[dict[str, Any] | list[Any] | None, CompletionResult]:
        raw = self._chat_raw(
            messages, temperature=temperature, max_tokens=max_tokens, fmt="json"
        )
        text = raw.get("message", {}).get("content", "")
        result = CompletionResult(text=text, stats=self._stats(raw), raw=raw)
        try:
            parsed = json.loads(text)
        except (json.JSONDecodeError, TypeError):
            parsed = None
        return parsed, result

    def health_check(self) -> bool:
        try:
            req = urllib.request.Request(f"{self.host}/api/tags", method="GET")
            with urllib.request.urlopen(req, timeout=5.0) as resp:
                tags = json.loads(resp.read().decode("utf-8"))
        except (urllib.error.URLError, TimeoutError, OSError):
            return False
        names = {m.get("name", "") for m in tags.get("models", [])}
        # Match with or without an explicit :latest / tag suffix.
        return any(n == self.model_name or n.startswith(self.model_name) for n in names)
