import hashlib
from abc import ABC, abstractmethod

import httpx

from app.core.config import settings
from app.models.document import EMBEDDING_DIMENSIONS


class EmbeddingProvider(ABC):
    """
    decisions.md ADR-012 — the mandatory abstraction every embedding call
    goes through. Service code depends on this interface only; it never
    imports a concrete provider directly (skills/backend.md §7's DI pattern),
    so swapping providers is a change to get_embedding_provider() alone.
    """

    model_name: str
    # R3 remediation (tasks/R3-document-processing.md, NFR-OBS-001) —
    # mirrors LLMProvider.provider_name (app/ai/llm.py) exactly, so
    # DocumentProcessingService can log an `ai_requests` row for every
    # embedding call the same way chat_service.py already does for LLM
    # calls, without inventing a second way to name a provider.
    provider_name: str

    @abstractmethod
    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """One EMBEDDING_DIMENSIONS-length vector per input text, same order, same length as `texts`."""


class FakeEmbeddingProvider(EmbeddingProvider):
    """
    Deterministic, offline, zero-cost — the active default (OQ-03, resolved
    for local/dev: proving the chunking/storage/search mechanics this phase
    delivers doesn't require real semantic quality or an API key/cost).

    Uses the classic feature-hashing trick (as in scikit-learn's
    HashingVectorizer), not raw random noise: each word deterministically
    hashes to a dimension + sign, accumulated and L2-normalized. This means
    two texts sharing more words produce vectors with genuinely higher
    cosine similarity than two texts sharing none — the fake provider still
    supports real, testable relevance-ranking behavior, per
    specs/testing.md's "a deterministic fixed test embedding provider" (§4).
    """

    model_name = "fake-hashing-v1"
    provider_name = "fake"

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        return [self._embed_one(text) for text in texts]

    @staticmethod
    def _embed_one(text: str) -> list[float]:
        vector = [0.0] * EMBEDDING_DIMENSIONS
        words = text.lower().split()
        for word in words:
            digest = hashlib.sha256(word.encode("utf-8")).digest()
            index = int.from_bytes(digest[:4], "big") % EMBEDDING_DIMENSIONS
            sign = 1.0 if digest[4] % 2 == 0 else -1.0
            vector[index] += sign
        norm = sum(v * v for v in vector) ** 0.5
        if norm == 0:
            return vector
        return [v / norm for v in vector]


class OpenAIEmbeddingProvider(EmbeddingProvider):
    """Real embeddings via OpenAI's REST API (ADR-012 default: text-embedding-3-small, 1536 dims)."""

    model_name = "text-embedding-3-small"
    provider_name = "openai"

    def __init__(self, api_key: str) -> None:
        self._api_key = api_key

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                "https://api.openai.com/v1/embeddings",
                headers={"Authorization": f"Bearer {self._api_key}"},
                json={"model": self.model_name, "input": texts},
            )
            response.raise_for_status()
            payload = response.json()
        # The API may return results out of input order; `index` maps back.
        ordered = sorted(payload["data"], key=lambda item: item["index"])
        return [item["embedding"] for item in ordered]


def get_embedding_provider() -> EmbeddingProvider:
    """Single construction point — the only place `settings.embedding_provider` is read."""
    if settings.embedding_provider == "openai":
        if not settings.openai_api_key:
            raise RuntimeError(
                "EMBEDDING_PROVIDER=openai requires OPENAI_API_KEY to be set."
            )
        return OpenAIEmbeddingProvider(settings.openai_api_key)
    return FakeEmbeddingProvider()
