"""Embedding Provider Abstraction and Fallback Architecture for Denver Memory."""

from __future__ import annotations

import abc
import asyncio
import hashlib
import json
import math
import re
import urllib.error
import urllib.request
from typing import Any

from denver.logging.logger import get_logger

logger = get_logger("memory.embeddings")


def _l2_normalize(vec: list[float]) -> list[float]:
    """Normalize vector to unit length (Euclidean norm)."""
    norm = math.sqrt(sum(x * x for x in vec))
    if norm == 0.0:
        return vec
    return [x / norm for x in vec]


def cosine_similarity(v1: list[float], v2: list[float]) -> float:
    """Calculate cosine similarity between two float vectors bounded in [-1.0, 1.0]."""
    if not v1 or not v2 or len(v1) != len(v2):
        return 0.0
    dot = sum(a * b for a, b in zip(v1, v2))
    norm_a = math.sqrt(sum(a * a for a in v1))
    norm_b = math.sqrt(sum(b * b for b in v2))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return max(-1.0, min(1.0, dot / (norm_a * norm_b)))


class EmbeddingProvider(abc.ABC):
    """Abstract Base Class for Denver Embedding Providers."""

    @property
    @abc.abstractmethod
    def name(self) -> str:
        """Provider identifier."""

    @property
    @abc.abstractmethod
    def model_name(self) -> str:
        """Model name used for embeddings."""

    @property
    @abc.abstractmethod
    def dimension(self) -> int:
        """Dimension size of output vectors."""

    @abc.abstractmethod
    async def embed_text(self, text: str) -> list[float]:
        """Generate embedding vector for a single text string."""

    @abc.abstractmethod
    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Generate embedding vectors for a batch of text strings."""

    @abc.abstractmethod
    async def check_health(self) -> dict[str, Any]:
        """Report availability and operational health."""


class DeterministicLexicalEmbedder(EmbeddingProvider):
    """Pure-Python Deterministic Character-Ngram & Token Hashing Embedder.

    Guarantees 100% Python 3.14.7 compatibility without requiring external native C++ wheels.
    Acts as a reliable deterministic lexical/vector fallback.
    """

    def __init__(self, dimension: int = 128) -> None:
        self._dimension = dimension
        self._model_name = "denver-lexical-v1"

    @property
    def name(self) -> str:
        return "deterministic_lexical"

    @property
    def model_name(self) -> str:
        return self._model_name

    @property
    def dimension(self) -> int:
        return self._dimension

    def _hash_token(self, token: str) -> int:
        """Compute stable hash index for a token."""
        h = hashlib.sha256(token.encode("utf-8")).digest()
        val = int.from_bytes(h[:4], "big")
        return val % self._dimension

    def _compute_vector(self, text: str) -> list[float]:
        """Convert text to a normalized dense vector using word tokens and character 3-grams."""
        if not text or not text.strip():
            return [0.0] * self._dimension

        vec = [0.0] * self._dimension
        clean = text.lower().strip()
        tokens = re.findall(r"\b\w+\b", clean)

        # 1. Word token hashing with frequency weighting
        for token in tokens:
            idx = self._hash_token(token)
            vec[idx] += 1.5

        # 2. Character 3-grams for subword / morphological overlap
        for i in range(len(clean) - 2):
            trigram = clean[i : i + 3]
            idx = self._hash_token(trigram)
            vec[idx] += 0.5

        return _l2_normalize(vec)

    async def embed_text(self, text: str) -> list[float]:
        return self._compute_vector(text)

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        return [self._compute_vector(t) for t in texts]

    async def check_health(self) -> dict[str, Any]:
        return {
            "status": "READY",
            "provider": self.name,
            "model": self.model_name,
            "dimension": self._dimension,
            "fallback": True,
        }


class OllamaEmbeddingProvider(EmbeddingProvider):
    """Embedding provider connecting asynchronously to an Ollama server."""

    def __init__(
        self,
        base_url: str = "http://localhost:11434",
        model: str = "nomic-embed-text",
        timeout: float = 5.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self._model = model
        self.timeout = timeout
        self._dimension = 768  # default estimate, adjusted dynamically

    @property
    def name(self) -> str:
        return "ollama"

    @property
    def model_name(self) -> str:
        return self._model

    @property
    def dimension(self) -> int:
        return self._dimension

    def _sync_request(self, endpoint: str, payload: dict[str, Any]) -> dict[str, Any]:
        url = f"{self.base_url}{endpoint}"
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=data,
            headers={"Content-Type": "application/json", "User-Agent": "Denver/0.1.0"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=self.timeout) as resp:
            body = resp.read().decode("utf-8")
            return json.loads(body)

    async def embed_text(self, text: str) -> list[float]:
        """Fetch embedding via /api/embeddings or /api/embed."""
        payload = {"model": self._model, "prompt": text}
        try:
            res = await asyncio.to_thread(self._sync_request, "/api/embeddings", payload)
            embedding = res.get("embedding")
            if embedding and isinstance(embedding, list):
                self._dimension = len(embedding)
                return _l2_normalize(embedding)
            raise ValueError(f"Ollama returned invalid embedding format: {res}")
        except Exception as exc:
            logger.warning("Ollama embedding failed for model '%s': %s", self._model, exc)
            raise

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        results = []
        for t in texts:
            results.append(await self.embed_text(t))
        return results

    async def check_health(self) -> dict[str, Any]:
        try:
            # Check server availability
            url = f"{self.base_url}/api/tags"
            req = urllib.request.Request(url, headers={"User-Agent": "Denver/0.1.0"}, method="GET")
            resp = await asyncio.to_thread(lambda: urllib.request.urlopen(req, timeout=self.timeout))
            if resp.status == 200:
                return {
                    "status": "READY",
                    "provider": self.name,
                    "model": self.model_name,
                    "dimension": self._dimension,
                    "base_url": self.base_url,
                }
            return {"status": "DEGRADED", "provider": self.name, "error": f"HTTP {resp.status}"}
        except Exception as exc:
            return {"status": "UNAVAILABLE", "provider": self.name, "error": str(exc)}


class EmbeddingManager:
    """Orchestrates embedding generation with local-first priority and automatic fallback."""

    def __init__(
        self,
        primary_provider: EmbeddingProvider | None = None,
        fallback_provider: EmbeddingProvider | None = None,
        enabled: bool = True,
    ) -> None:
        self.fallback = fallback_provider or DeterministicLexicalEmbedder()
        self.primary = primary_provider
        self.enabled = enabled

    async def embed(self, text: str) -> tuple[list[float], str]:
        """Generate embedding vector with fallback. Returns (vector, model_name)."""
        if not self.enabled:
            return [0.0] * self.fallback.dimension, "none"

        if self.primary:
            try:
                vec = await self.primary.embed_text(text)
                return vec, self.primary.model_name
            except Exception as exc:
                logger.debug("Primary embedder failed, falling back to lexical embedder: %s", exc)

        vec = await self.fallback.embed_text(text)
        return vec, self.fallback.model_name

    async def embed_batch(self, texts: list[str]) -> tuple[list[list[float]], str]:
        """Generate batch embeddings with fallback."""
        if not self.enabled:
            return [[0.0] * self.fallback.dimension for _ in texts], "none"

        if self.primary:
            try:
                vecs = await self.primary.embed_batch(texts)
                return vecs, self.primary.model_name
            except Exception as exc:
                logger.debug("Primary batch embedder failed, falling back: %s", exc)

        vecs = await self.fallback.embed_batch(texts)
        return vecs, self.fallback.model_name

    async def get_health_status(self) -> dict[str, Any]:
        """Report status of primary and fallback embedding engines."""
        status = {
            "enabled": self.enabled,
            "fallback": await self.fallback.check_health(),
            "active_provider": self.primary.name if self.primary else self.fallback.name,
        }
        if self.primary:
            status["primary"] = await self.primary.check_health()
        return status
