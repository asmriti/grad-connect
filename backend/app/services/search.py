"""Semantic search: query embedding → pgvector cosine search → professor-level
aggregation with evidence chunks. Metadata filters (university, country) are
applied in SQL, not embedded into the semantic query."""

from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models.tables import DocumentChunk, Professor


@dataclass
class Evidence:
    text: str
    url: str
    page_title: str | None
    heading: str | None
    similarity: float


@dataclass
class ProfessorResult:
    professor: Professor
    similarity: float  # best chunk similarity
    evidence: list[Evidence] = field(default_factory=list)


@dataclass
class SearchPage:
    results: list[ProfessorResult]
    total: int  # matching professors across all pages


def aggregate_chunks(
    rows: list[tuple],  # (chunk, professor, similarity) sorted best-first
    evidence_per_professor: int = 3,
) -> list[ProfessorResult]:
    """Aggregate chunk hits into professor-level results.

    Strategy: a professor's score is their highest-scoring chunk; the top
    few distinct chunks are kept as evidence.
    """
    by_professor: dict[int, ProfessorResult] = {}
    for chunk, professor, similarity in rows:
        result = by_professor.get(professor.id)
        if result is None:
            result = ProfessorResult(professor=professor, similarity=similarity)
            by_professor[professor.id] = result
        if len(result.evidence) < evidence_per_professor:
            result.evidence.append(
                Evidence(
                    text=chunk.text,
                    url=chunk.url,
                    page_title=chunk.page_title,
                    heading=chunk.heading,
                    similarity=similarity,
                )
            )
    return sorted(by_professor.values(), key=lambda r: r.similarity, reverse=True)


def search_chunks(
    session: Session,
    query_embedding: list[float],
    university: str | None = None,
    country: str | None = None,
    min_similarity: float | None = None,
    chunk_pool: int = 2000,
) -> list[tuple]:
    """Filtered pgvector cosine search over professor chunks.

    Returns (chunk, professor, similarity) rows, best first — the shared
    retrieval step behind both topic search and resume matching.

    `min_similarity` drops chunks that are merely the nearest neighbours of an
    off-topic query; without it every query returns results. Pass 0 to disable.
    """
    if min_similarity is None:
        min_similarity = get_settings().min_similarity

    distance = DocumentChunk.embedding.cosine_distance(query_embedding)
    stmt = (
        select(DocumentChunk, Professor, (1 - distance).label("similarity"))
        .join(Professor, DocumentChunk.professor_id == Professor.id)
        .where(DocumentChunk.embedding.is_not(None))
    )
    if min_similarity > 0:
        # Expressed as distance so the comparison stays indexable.
        stmt = stmt.where(distance <= 1 - min_similarity)
    if university:
        stmt = stmt.where(Professor.affiliation.ilike(university))
    if country:
        stmt = stmt.where(Professor.country.ilike(country))
    stmt = stmt.order_by(distance).limit(chunk_pool)

    return [(chunk, professor, float(sim)) for chunk, professor, sim in session.execute(stmt)]


def search_professors(
    session: Session,
    query_embedding: list[float],
    limit: int = 10,
    offset: int = 0,
    university: str | None = None,
    country: str | None = None,
    evidence_per_professor: int = 3,
    chunk_pool: int = 2000,
    min_similarity: float | None = None,
) -> SearchPage:
    """Run filtered vector search, aggregate to professors, return one page.

    All chunks above the similarity floor (up to `chunk_pool`) are aggregated
    so the total match count and every page's ranking are stable; `offset` and
    `limit` then slice the professor-level ranking. With the floor active a
    query rarely produces more than a few hundred relevant chunks, so the pool
    cap only matters as a safety valve.
    """
    rows = search_chunks(
        session,
        query_embedding,
        university=university,
        country=country,
        min_similarity=min_similarity,
        chunk_pool=chunk_pool,
    )
    ranked = aggregate_chunks(rows, evidence_per_professor=evidence_per_professor)
    return SearchPage(results=ranked[offset : offset + limit], total=len(ranked))
