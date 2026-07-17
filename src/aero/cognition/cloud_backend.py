"""Cloud CognitionService — Aero's optional "online brain" (the boost tier).

Local gemma4:e4b is Aero's private default, but on a CPU box it's a ~5-11 s/turn
thinker. When you want real-time snap, this backend routes generation to a cloud
LLM over the OpenAI-compatible /chat/completions API — sub-second, streaming-class
latency. It's provider-agnostic: point ``base_url`` + ``api_key`` at any
OpenAI-compatible endpoint.

  provider     base_url                                           example model
  --------     --------------------------------------------------  ---------------------
  Groq (free)  https://api.groq.com/openai/v1                      llama-3.3-70b-versatile
  OpenAI       https://api.openai.com/v1                           gpt-4o-mini
  OpenRouter   https://openrouter.ai/api/v1                        many
  Gemini       https://generativelanguage.googleapis.com/v1beta/openai  gemini-2.0-flash

PRIVACY: going cloud means each turn's prompt — INCLUDING the assembled memory
context (who you are, what Aero recalls) — leaves the device to that provider.
Aero is local-first, so this is strictly opt-in (settings brain='cloud'); the
local brain stays the default. Stdlib-only (urllib) — no new dependency.
"""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from typing import Any

from aero.cognition.service import (
    ChatMessage,
    CognitionService,
    CompletionResult,
    GenerationStats,
)

# Named presets so callers can say "groq" instead of memorising URLs.
PROVIDERS = {
    "groq": "https://api.groq.com/openai/v1",
    "openai": "https://api.openai.com/v1",
    "openrouter": "https://openrouter.ai/api/v1",
    "gemini": "https://generativelanguage.googleapis.com/v1beta/openai",
}

# API key is read from the environment, never persisted to settings.json.
API_KEY_ENVS = ("AERO_BRAIN_API_KEY", "GROQ_API_KEY", "OPENAI_API_KEY",
                "OPENROUTER_API_KEY", "GEMINI_API_KEY")


def resolve_api_key(explicit: str | None = None) -> str | None:
    if explicit:
        return explicit
    for env in API_KEY_ENVS:
        val = os.environ.get(env)
        if val:
            return val
    return None


class CloudCognition(CognitionService):
    # Mechanically capable of the OpenAI image path; whether the *model* groks
    # images is the registry profile's supports_vision flag (routing decides).
    supports_vision = True

    def __init__(
        self,
        model_name: str = "llama-3.3-70b-versatile",
        *,
        base_url: str = PROVIDERS["groq"],
        api_key: str | None = None,
        timeout: float = 60.0,
    ):
        self.model_name = model_name
        # Accept a provider alias ("groq") or a full URL.
        self.base_url = PROVIDERS.get(base_url, base_url).rstrip("/")
        self.api_key = resolve_api_key(api_key)
        self.timeout = timeout

    # -- HTTP --------------------------------------------------------------
    def _post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        req = urllib.request.Request(
            f"{self.base_url}{path}",
            data=json.dumps(payload).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=self.timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))

    def _completion(
        self,
        messages: list[ChatMessage],
        *,
        temperature: float,
        max_tokens: int | None,
        json_mode: bool = False,
    ) -> CompletionResult:
        payload: dict[str, Any] = {
            "model": self.model_name,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "temperature": temperature,
        }
        if max_tokens is not None:
            payload["max_tokens"] = max_tokens
        if json_mode:
            payload["response_format"] = {"type": "json_object"}
        t0 = time.perf_counter()
        raw = self._post("/chat/completions", payload)
        elapsed = time.perf_counter() - t0
        text = raw.get("choices", [{}])[0].get("message", {}).get("content", "") or ""
        usage = raw.get("usage", {}) or {}
        stats = GenerationStats(
            prompt_tokens=usage.get("prompt_tokens", 0),
            completion_tokens=usage.get("completion_tokens", 0),
            total_seconds=elapsed or 1e-9,
            eval_seconds=elapsed,  # API gives no decode-only split; wall time is it
        )
        return CompletionResult(text=text.strip(), stats=stats, raw=raw)

    # -- CognitionService --------------------------------------------------
    def chat(
        self,
        messages: list[ChatMessage],
        *,
        temperature: float = 0.7,
        max_tokens: int | None = None,
    ) -> CompletionResult:
        return self._completion(messages, temperature=temperature, max_tokens=max_tokens)

    def complete_json(
        self,
        messages: list[ChatMessage],
        *,
        temperature: float = 0.2,
        max_tokens: int | None = None,
    ) -> tuple[dict[str, Any] | list[Any] | None, CompletionResult]:
        result = self._completion(
            messages, temperature=temperature, max_tokens=max_tokens, json_mode=True
        )
        try:
            parsed = json.loads(result.text)
        except (json.JSONDecodeError, TypeError):
            parsed = None
        return parsed, result

    def see(
        self,
        prompt: str,
        image: bytes,
        *,
        media_type: str = "image/png",
        temperature: float = 0.7,
        max_tokens: int | None = None,
    ) -> CompletionResult:
        """Vision via the OpenAI multimodal message shape: a user message whose
        content is [text, image_url(data-URI)]. Works on any OpenAI-compatible
        vision model (gpt-4o, gemini-*-flash, …)."""
        import base64
        b64 = base64.b64encode(image).decode("ascii")
        content = [
            {"type": "text", "text": prompt},
            {"type": "image_url",
             "image_url": {"url": f"data:{media_type};base64,{b64}"}},
        ]
        payload: dict[str, Any] = {
            "model": self.model_name,
            "messages": [{"role": "user", "content": content}],
            "temperature": temperature,
        }
        if max_tokens is not None:
            payload["max_tokens"] = max_tokens
        t0 = time.perf_counter()
        raw = self._post("/chat/completions", payload)
        elapsed = time.perf_counter() - t0
        text = raw.get("choices", [{}])[0].get("message", {}).get("content", "") or ""
        usage = raw.get("usage", {}) or {}
        stats = GenerationStats(
            prompt_tokens=usage.get("prompt_tokens", 0),
            completion_tokens=usage.get("completion_tokens", 0),
            total_seconds=elapsed or 1e-9, eval_seconds=elapsed,
        )
        return CompletionResult(text=text.strip(), stats=stats, raw=raw)

    def _is_local(self) -> bool:
        return any(h in self.base_url for h in ("localhost", "127.0.0.1", "0.0.0.0"))

    def health_check(self) -> bool:
        """True if the /models endpoint answers. A remote provider needs a key
        (keyless -> False without a network call, so tests stay hermetic); a
        local proxy (e.g. LiteLLM bridging a ChatGPT subscription) may be
        keyless, so we actually probe it."""
        if not self.api_key and not self._is_local():
            return False
        headers = {}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        try:
            req = urllib.request.Request(
                f"{self.base_url}/models", headers=headers, method="GET"
            )
            with urllib.request.urlopen(req, timeout=8.0):
                return True
        except (urllib.error.URLError, TimeoutError, OSError):
            return False
