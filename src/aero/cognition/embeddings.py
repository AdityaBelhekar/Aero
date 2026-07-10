"""Embedding service — turns text into vectors for the retrieval anchor step.

The retrieval pipeline's first stage (AERO-RET-001) embeds the current moment
and finds semantically similar memories. That embedding model must survive
romanised Hindi/Marathi and code-switched text (risk R-4), which is exactly what
spike S-2 checks.

Ollama serves embedding models via ``/api/embed``, so we reuse the local daemon
and add no Python dependencies. Default model: ``embeddinggemma`` (Google's
on-device, multilingual embedder).
"""

from __future__ import annotations

import json
import math
import urllib.error
import urllib.request
from abc import ABC, abstractmethod

DEFAULT_HOST = "http://localhost:11434"
DEFAULT_EMBED_MODEL = "embeddinggemma"

Vector = list[float]


def cosine(a: Vector, b: Vector) -> float:
    """Cosine similarity. Returns 0.0 for a zero vector rather than dividing by 0."""
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0.0 or nb == 0.0:
        return 0.0
    return dot / (na * nb)


class EmbeddingService(ABC):
    model_name: str
    dim: int

    @abstractmethod
    def embed(self, text: str) -> Vector:
        ...

    @abstractmethod
    def embed_batch(self, texts: list[str]) -> list[Vector]:
        ...

    @abstractmethod
    def health_check(self) -> bool:
        ...


class OllamaEmbedder(EmbeddingService):
    def __init__(
        self,
        model_name: str = DEFAULT_EMBED_MODEL,
        *,
        host: str = DEFAULT_HOST,
        timeout: float = 60.0,
    ):
        self.model_name = model_name
        self.host = host.rstrip("/")
        self.timeout = timeout
        self.dim = 0  # discovered on first embed

    def _embed_raw(self, texts: list[str]) -> list[Vector]:
        payload = {"model": self.model_name, "input": texts}
        req = urllib.request.Request(
            f"{self.host}/api/embed",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=self.timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        vecs = data.get("embeddings") or []
        if vecs and not self.dim:
            self.dim = len(vecs[0])
        return vecs

    def embed(self, text: str) -> Vector:
        vecs = self._embed_raw([text])
        if not vecs:
            raise RuntimeError("embedding backend returned no vectors")
        return vecs[0]

    def embed_batch(self, texts: list[str]) -> list[Vector]:
        if not texts:
            return []
        return self._embed_raw(texts)

    def ensure_loaded(self, keep_alive: str = "30m") -> bool:
        """Keep the embedder resident (daemon keep-warm). A tiny embed with
        keep_alive loads the model and refreshes its unload timer."""
        payload = {"model": self.model_name, "input": " ", "keep_alive": keep_alive}
        try:
            req = urllib.request.Request(
                f"{self.host}/api/embed",
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=self.timeout):
                return True
        except (urllib.error.URLError, TimeoutError, OSError):
            return False

    def health_check(self) -> bool:
        try:
            req = urllib.request.Request(f"{self.host}/api/tags", method="GET")
            with urllib.request.urlopen(req, timeout=5.0) as resp:
                tags = json.loads(resp.read().decode("utf-8"))
        except (urllib.error.URLError, TimeoutError, OSError):
            return False
        names = {m.get("name", "") for m in tags.get("models", [])}
        return any(n == self.model_name or n.startswith(self.model_name) for n in names)


# -- vector (de)serialization for the vault's embeddings.vector BLOB --------
import struct  # noqa: E402


def pack_vector(vec: Vector) -> bytes:
    """Little-endian float32 blob — compact and index-friendly."""
    return struct.pack(f"<{len(vec)}f", *vec)


def unpack_vector(blob: bytes) -> Vector:
    n = len(blob) // 4
    return list(struct.unpack(f"<{n}f", blob))
