"""Indexing pipeline: crawl → extract → chunk → embed → store.

Idempotent: pages whose content hash is unchanged are not re-chunked or
re-embedded. Per-professor failures are logged and never stop the run.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import httpx
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models.tables import Document, DocumentChunk, Professor
from app.services.chunker import chunk_sections
from app.services.crawler import CrawledPage, crawl_professor_site
from app.services.embeddings import EmbeddingProvider

logger = logging.getLogger(__name__)


@dataclass
class IndexStats:
    pages_found: int = 0
    pages_new_or_changed: int = 0
    chunks: int = 0
    embeddings: int = 0
    error: str | None = None


def crawl_only(
    client: httpx.Client,
    homepage: str,
    max_pages: int,
    limiter=None,
    robots=None,
) -> tuple[list[CrawledPage], str | None]:
    """Crawl one professor's site. Touches no database, so it is safe to run
    in a worker thread. Returns (pages, error)."""
    try:
        pages = crawl_professor_site(client, homepage, max_pages, limiter, robots)
    except Exception as exc:  # defensive: one bad site must not stop the run
        logger.exception("crawl failed for %s", homepage)
        return [], f"crawl failed: {exc}"
    if not pages:
        return [], "no pages could be crawled (site down, blocked, or JS-only)"
    return pages, None


def store_crawled_pages(
    session: Session,
    embedder: EmbeddingProvider,
    professor: Professor,
    pages: list[CrawledPage],
    chunk_size: int,
    chunk_overlap: int,
) -> IndexStats:
    """Chunk, embed and persist already-crawled pages. Main thread only."""
    stats = IndexStats()
    stats.pages_found = len(pages)
    for page in pages:
        try:
            changed = _store_page(
                session, embedder, professor, page, chunk_size, chunk_overlap, stats
            )
            if changed:
                stats.pages_new_or_changed += 1
            session.commit()
        except Exception as exc:
            session.rollback()
            logger.exception("indexing failed for page %s", page.url)
            stats.error = f"page {page.url}: {exc}"
    return stats


def index_professor(
    session: Session,
    client: httpx.Client,
    embedder: EmbeddingProvider,
    professor: Professor,
    max_pages: int,
    chunk_size: int,
    chunk_overlap: int,
) -> IndexStats:
    """Sequential crawl-and-store for a single professor."""
    stats = IndexStats()
    try:
        pages = crawl_professor_site(client, professor.homepage, max_pages)
    except Exception as exc:  # defensive: one bad site must not stop the run
        logger.exception("crawl failed for %s", professor.name)
        stats.error = f"crawl failed: {exc}"
        return stats

    stats.pages_found = len(pages)
    if not pages:
        stats.error = "no pages could be crawled (site down or JS-only)"
        return stats

    for page in pages:
        try:
            changed = _store_page(
                session, embedder, professor, page, chunk_size, chunk_overlap, stats
            )
            if changed:
                stats.pages_new_or_changed += 1
            session.commit()
        except Exception as exc:
            session.rollback()
            logger.exception("indexing failed for page %s", page.url)
            stats.error = f"page {page.url}: {exc}"
    return stats


def _store_page(
    session: Session,
    embedder: EmbeddingProvider,
    professor: Professor,
    page: CrawledPage,
    chunk_size: int,
    chunk_overlap: int,
    stats: IndexStats,
) -> bool:
    """Insert/update one crawled page. Returns True if (re)indexed."""
    document = session.execute(
        select(Document).where(
            Document.professor_id == professor.id, Document.url == page.url
        )
    ).scalar_one_or_none()

    if document is not None and document.content_hash == page.content_hash:
        document.http_status = page.http_status  # touchs crawled_at via onupdate
        return False

    if document is None:
        document = Document(professor_id=professor.id, url=page.url)
        session.add(document)
    else:
        session.execute(
            delete(DocumentChunk).where(DocumentChunk.document_id == document.id)
        )

    document.title = _fit(page.title, 1024)
    document.clean_text = page.clean_text
    document.page_type = page.page_type
    document.content_hash = page.content_hash
    document.http_status = page.http_status
    session.flush()  # ensure document.id

    chunks = chunk_sections(page.sections, chunk_size, chunk_overlap)
    stats.chunks += len(chunks)
    vectors = embedder.embed_texts([c.text for c in chunks])
    stats.embeddings += len(vectors)
    for chunk, vector in zip(chunks, vectors):
        session.add(
            DocumentChunk(
                professor_id=professor.id,
                document_id=document.id,
                chunk_index=chunk.chunk_index,
                text=chunk.text,
                embedding=vector,
                page_title=_fit(page.title, 1024),
                heading=_fit(chunk.heading, 512),
                url=page.url,
            )
        )
    return True


def _fit(value: str | None, max_length: int) -> str | None:
    """Clamp scraped metadata to its column size. Real pages produce
    pathological titles/headings (e.g. a whole paragraph inside <h2>), and one
    oversized value must not abort a professor's indexing."""
    if value is not None and len(value) > max_length:
        return value[: max_length - 1] + "…"
    return value
