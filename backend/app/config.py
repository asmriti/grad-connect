"""Application configuration.

All values can be overridden via environment variables or a `.env` file at the
repository root (see `.env.example`).
"""

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# Repository root (two levels up from this file: backend/app/config.py)
REPO_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(REPO_ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    database_url: str = "postgresql+psycopg://localhost/grad_connect"

    # Embedding
    embedding_model: str = "BAAI/bge-small-en-v1.5"
    # bge models are trained with an instruction prefix on the *query* side only.
    embedding_query_prefix: str = (
        "Represent this sentence for searching relevant passages: "
    )
    embedding_batch_size: int = 32

    # Crawler
    max_pages_per_professor: int = 10
    crawl_timeout_seconds: float = 15.0
    crawl_user_agent: str = (
        "grad-connect-bot/0.1 (+academic research discovery MVP)"
    )

    # Chunking (approximate tokens; 1 token ~= 4 characters of English text)
    chunk_size: int = 600
    chunk_overlap: int = 100

    # Search: minimum cosine similarity for a chunk to count as a match.
    # Vector search always returns the nearest neighbours regardless of
    # distance, so without a floor an off-topic query ("xyz") still returns
    # its least-bad matches. Measured on the full 21k-chunk corpus: nonsense
    # queries top out at ~0.62, genuine topic matches never drop below ~0.70,
    # so the threshold lives in that gap. Re-measure if you change the model.
    min_similarity: float = 0.65

    # Ingestion
    professors_csv: str = str(REPO_ROOT / "data" / "data.csv")


@lru_cache
def get_settings() -> Settings:
    return Settings()
