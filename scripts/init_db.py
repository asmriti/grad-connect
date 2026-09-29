"""Initialize the database: pgvector extension, tables, vector index.

Usage:
    python scripts/init_db.py
"""

import _bootstrap  # noqa: F401

from app.db.init import init_db
from app.db.session import get_engine
from app.services.embeddings import get_embedding_service


def main() -> None:
    embedder = get_embedding_service()
    print(f"Embedding model: {embedder.model_name} (dim={embedder.dimension})")
    init_db(get_engine(), embedder.dimension)
    print("Database initialized: extension, tables, and vector index ready.")


if __name__ == "__main__":
    main()
