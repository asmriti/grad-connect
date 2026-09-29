"""Database initialization: pgvector extension, tables, vector index.

The embedding dimension is taken from the active embedding model rather than
hard-coded, so switching models only requires re-running init + re-indexing.
"""

from sqlalchemy import text
from sqlalchemy.engine import Engine

from app.models.tables import Base


def init_db(engine: Engine, embedding_dim: int) -> None:
    with engine.begin() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))

    Base.metadata.create_all(engine)

    with engine.begin() as conn:
        # Pin the embedding column to the model's dimension (a bare `vector`
        # column would accept mixed dimensions, which we don't want).
        conn.execute(
            text(
                f"ALTER TABLE document_chunks "
                f"ALTER COLUMN embedding TYPE vector({embedding_dim})"
            )
        )
        # HNSW index for cosine distance. Tiny datasets don't need it, but it
        # keeps search fast as the corpus grows and is cheap to build.
        conn.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_document_chunks_embedding "
                "ON document_chunks USING hnsw (embedding vector_cosine_ops)"
            )
        )
