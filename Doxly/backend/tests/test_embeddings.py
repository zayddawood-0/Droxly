import pytest

from app.ai.embeddings import FakeEmbeddingProvider, get_embedding_provider
from app.core.config import settings
from app.models.document import EMBEDDING_DIMENSIONS


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    norm_a = sum(x * x for x in a) ** 0.5
    norm_b = sum(y * y for y in b) ** 0.5
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


async def test_embed_batch_returns_one_vector_of_the_configured_dimension_per_input():
    provider = FakeEmbeddingProvider()
    vectors = await provider.embed_batch(
        ["cats and dogs", "quarterly financial report"]
    )

    assert len(vectors) == 2
    assert all(len(vector) == EMBEDDING_DIMENSIONS for vector in vectors)


async def test_same_text_always_produces_the_same_vector():
    """Determinism is the whole point (specs/testing.md §4 — "a deterministic fixed test embedding provider")."""
    provider = FakeEmbeddingProvider()
    [first] = await provider.embed_batch(["the quick brown fox"])
    [second] = await provider.embed_batch(["the quick brown fox"])
    assert first == second


async def test_texts_sharing_more_words_are_more_similar_than_unrelated_texts():
    """Proves the fake provider supports genuine, testable relevance ranking — not just random noise."""
    provider = FakeEmbeddingProvider()
    query, related, unrelated = await provider.embed_batch(
        [
            "quarterly financial report revenue growth",
            "annual financial report revenue growth summary",
            "a recipe for chocolate chip cookies",
        ]
    )

    assert _cosine_similarity(query, related) > _cosine_similarity(query, unrelated)


async def test_empty_text_yields_a_zero_vector_without_crashing():
    provider = FakeEmbeddingProvider()
    [vector] = await provider.embed_batch([""])
    assert len(vector) == EMBEDDING_DIMENSIONS
    assert all(v == 0.0 for v in vector)


def test_get_embedding_provider_defaults_to_fake(monkeypatch):
    monkeypatch.setattr(settings, "embedding_provider", "fake")
    provider = get_embedding_provider()
    assert isinstance(provider, FakeEmbeddingProvider)


def test_get_embedding_provider_requires_an_api_key_for_openai(monkeypatch):
    monkeypatch.setattr(settings, "embedding_provider", "openai")
    monkeypatch.setattr(settings, "openai_api_key", None)
    with pytest.raises(RuntimeError):
        get_embedding_provider()
