"""API response/request schemas."""

from __future__ import annotations

from pydantic import BaseModel, Field


class ProfessorOut(BaseModel):
    id: int
    name: str
    affiliation: str
    country: str | None = None
    homepage: str
    scholar_id: str | None = None
    orcid: str | None = None

    model_config = {"from_attributes": True}


class EvidenceOut(BaseModel):
    text: str
    url: str
    page_title: str | None = None
    heading: str | None = None


class SearchResultOut(BaseModel):
    professor: ProfessorOut
    # Rounded: raw float precision is meaningless to users.
    similarity: float
    evidence: list[EvidenceOut]


class SearchResponse(BaseModel):
    query: str
    results: list[SearchResultOut]
    total: int  # matching professors across all pages
    page: int
    page_size: int


class SearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=1000)
    university: str | None = None
    country: str | None = None
    page: int = Field(default=1, ge=1)
    limit: int = Field(default=10, ge=1, le=100)  # page size


class MatchPairOut(BaseModel):
    resume_excerpt: str
    # professor side
    text: str
    url: str
    page_title: str | None = None
    heading: str | None = None


class MatchResultOut(BaseModel):
    professor: ProfessorOut
    similarity: float
    matches: list[MatchPairOut]


class MatchResponse(BaseModel):
    filename: str | None
    chunks_used: int
    truncated: bool
    results: list[MatchResultOut]
    total: int
    page: int
    page_size: int


class DocumentOut(BaseModel):
    id: int
    url: str
    title: str | None = None
    page_type: str | None = None
    http_status: int | None = None

    model_config = {"from_attributes": True}


class ChunkOut(BaseModel):
    id: int
    text: str
    url: str
    page_title: str | None = None
    heading: str | None = None

    model_config = {"from_attributes": True}


class ProfessorDetailOut(BaseModel):
    professor: ProfessorOut
    documents: list[DocumentOut]
    chunks: list[ChunkOut]


class FiltersOut(BaseModel):
    universities: list[str]
    countries: list[str]
