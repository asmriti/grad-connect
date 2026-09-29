"""Embedding service tests with a stubbed SentenceTransformer (no downloads)."""

import sys
import types

import pytest


class _FakeModel:
    """Deterministic stand-in for sentence_transformers.SentenceTransformer."""

    def __init__(self, name):
        self.name = name
        self.encoded: list[list[str]] = []

    def get_sentence_embedding_dimension(self):
        return 4

    def encode(self, texts, batch_size=32, normalize_embeddings=True, show_progress_bar=False):
        self.encoded.append(list(texts))
        import math

        vectors = []
        for text in texts:
            raw = [float(len(text)), float(text.count(" ")), 1.0, 0.5]
            norm = math.sqrt(sum(x * x for x in raw))
            vectors.append(_FakeVector([x / norm for x in raw]))
        return vectors


class _FakeVector(list):
    def tolist(self):
        return list(self)


@pytest.fixture
def embedder(monkeypatch):
    fake_module = types.ModuleType("sentence_transformers")
    fake_module.SentenceTransformer = _FakeModel
    monkeypatch.setitem(sys.modules, "sentence_transformers", fake_module)

    from app.services.embeddings import SentenceTransformerEmbedding

    return SentenceTransformerEmbedding(
        model_name="fake/model", query_prefix="QUERY: ", batch_size=8
    )


def test_dimension_comes_from_model(embedder):
    assert embedder.dimension == 4


def test_embed_texts_batches_and_returns_lists(embedder):
    vectors = embedder.embed_texts(["alpha beta", "gamma"])
    assert len(vectors) == 2
    assert all(isinstance(v, list) and len(v) == 4 for v in vectors)


def test_embed_texts_empty_input(embedder):
    assert embedder.embed_texts([]) == []


def test_embed_query_applies_prefix_passages_do_not(embedder):
    embedder.embed_query("robotics")
    embedder.embed_text("robotics")
    calls = embedder._model.encoded
    assert calls[0] == ["QUERY: robotics"]
    assert calls[1] == ["robotics"]


def test_embeddings_are_normalized(embedder):
    vector = embedder.embed_text("some passage text")
    assert abs(sum(x * x for x in vector) - 1.0) < 1e-6
