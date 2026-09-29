"""Embedding providers.

`EmbeddingProvider` is the swap point: the search and indexing layers only
depend on this protocol, so a hosted embedding API could be added later
without touching them. The default provider runs Sentence Transformers
locally — no external API calls, no generative LLM anywhere.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Protocol

from app.config import get_settings


class EmbeddingProvider(Protocol):
    @property
    def dimension(self) -> int: ...

    def embed_text(self, text: str) -> list[float]: ...

    def embed_texts(self, texts: list[str]) -> list[list[float]]: ...

    def embed_query(self, text: str) -> list[float]: ...

    def embed_queries(self, texts: list[str]) -> list[list[float]]: ...


class SentenceTransformerEmbedding:
    """Local Sentence Transformers embedding (default: BAAI/bge-small-en-v1.5).

    bge models expect an instruction prefix on queries (not on passages);
    embeddings are L2-normalized so cosine distance behaves well in pgvector.
    """

    def __init__(
        self,
        model_name: str,
        query_prefix: str = "",
        batch_size: int = 32,
    ) -> None:
        from sentence_transformers import SentenceTransformer  # heavy import, keep local

        self.model_name = model_name
        self.query_prefix = query_prefix
        self.batch_size = batch_size
        self._model = SentenceTransformer(model_name)

    @property
    def dimension(self) -> int:
        return self._model.get_sentence_embedding_dimension()

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        vectors = self._model.encode(
            texts,
            batch_size=self.batch_size,
            normalize_embeddings=True,
            show_progress_bar=False,
        )
        return [v.tolist() for v in vectors]

    def embed_text(self, text: str) -> list[float]:
        return self.embed_texts([text])[0]

    def embed_query(self, text: str) -> list[float]:
        return self.embed_text(self.query_prefix + text)

    def embed_queries(self, texts: list[str]) -> list[list[float]]:
        """Batch variant of embed_query (one model call for many queries)."""
        return self.embed_texts([self.query_prefix + text for text in texts])


@lru_cache
def get_embedding_service() -> SentenceTransformerEmbedding:
    settings = get_settings()
    return SentenceTransformerEmbedding(
        model_name=settings.embedding_model,
        query_prefix=settings.embedding_query_prefix,
        batch_size=settings.embedding_batch_size,
    )
