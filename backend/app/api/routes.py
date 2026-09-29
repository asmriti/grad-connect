from fastapi import APIRouter, Depends, Form, HTTPException, Query, UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db.session import get_db
from app.models.tables import Document, DocumentChunk, Professor
from app.schemas.search import (
    ChunkOut,
    DocumentOut,
    EvidenceOut,
    FiltersOut,
    MatchPairOut,
    MatchResponse,
    MatchResultOut,
    ProfessorDetailOut,
    ProfessorOut,
    SearchRequest,
    SearchResponse,
    SearchResultOut,
)
from app.services.embeddings import get_embedding_service
from app.services.resume import (
    MAX_UPLOAD_BYTES,
    MIN_TEXT_CHARS,
    ResumeError,
    extract_resume_text,
    match_resume,
)
from app.services.search import search_professors

router = APIRouter(prefix="/api")


def _run_search(request: SearchRequest, db: Session) -> SearchResponse:
    embedder = get_embedding_service()
    query_embedding = embedder.embed_query(request.query)
    page = search_professors(
        db,
        query_embedding,
        limit=request.limit,
        offset=(request.page - 1) * request.limit,
        university=request.university,
        country=request.country,
    )
    return SearchResponse(
        query=request.query,
        total=page.total,
        page=request.page,
        page_size=request.limit,
        results=[
            SearchResultOut(
                professor=ProfessorOut.model_validate(r.professor),
                similarity=round(r.similarity, 2),
                evidence=[
                    EvidenceOut(
                        text=e.text,
                        url=e.url,
                        page_title=e.page_title,
                        heading=e.heading,
                    )
                    for e in r.evidence
                ],
            )
            for r in page.results
        ],
    )


@router.get("/search", response_model=SearchResponse)
def search_get(
    query: str = Query(min_length=1, max_length=1000),
    university: str | None = None,
    country: str | None = None,
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=10, ge=1, le=100),
    db: Session = Depends(get_db),
) -> SearchResponse:
    request = SearchRequest(
        query=query, university=university, country=country, page=page, limit=limit
    )
    return _run_search(request, db)


@router.post("/search", response_model=SearchResponse)
def search_post(request: SearchRequest, db: Session = Depends(get_db)) -> SearchResponse:
    return _run_search(request, db)


@router.post("/match", response_model=MatchResponse)
def match(
    file: UploadFile | None = None,
    text: str | None = Form(default=None),
    university: str | None = Form(default=None),
    country: str | None = Form(default=None),
    page: int = Form(default=1, ge=1),
    limit: int = Form(default=10, ge=1, le=100),
    db: Session = Depends(get_db),
) -> MatchResponse:
    """Match a resume against the professor chunk index.

    Nothing is stored: file bytes, extracted text, and embeddings are
    discarded when the request ends.
    """
    filename: str | None = None
    if file is not None and file.filename:
        content = file.file.read(MAX_UPLOAD_BYTES + 1)
        filename = file.filename
        try:
            resume_text = extract_resume_text(filename, content)
        except ResumeError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
    elif text is not None and text.strip():
        resume_text = text.strip()
        if len(resume_text) < MIN_TEXT_CHARS:
            raise HTTPException(
                status_code=400,
                detail="The pasted text is too short to match against.",
            )
    else:
        raise HTTPException(
            status_code=400,
            detail="Upload a resume file or paste its text.",
        )

    settings = get_settings()
    result = match_resume(
        db,
        get_embedding_service(),
        resume_text,
        chunk_size=settings.chunk_size,
        chunk_overlap=settings.chunk_overlap,
        limit=limit,
        offset=(page - 1) * limit,
        university=university,
        country=country,
    )
    return MatchResponse(
        filename=filename,
        chunks_used=result.chunks_used,
        truncated=result.truncated,
        total=result.total,
        page=page,
        page_size=limit,
        results=[
            MatchResultOut(
                professor=ProfessorOut.model_validate(r.professor),
                similarity=round(r.similarity, 2),
                matches=[
                    MatchPairOut(
                        resume_excerpt=m.resume_excerpt,
                        text=m.text,
                        url=m.url,
                        page_title=m.page_title,
                        heading=m.heading,
                    )
                    for m in r.matches
                ],
            )
            for r in result.results
        ],
    )


@router.get("/professors/{professor_id}", response_model=ProfessorDetailOut)
def professor_detail(professor_id: int, db: Session = Depends(get_db)) -> ProfessorDetailOut:
    professor = db.get(Professor, professor_id)
    if professor is None:
        raise HTTPException(status_code=404, detail="professor not found")
    documents = (
        db.execute(
            select(Document)
            .where(Document.professor_id == professor_id)
            .order_by(Document.id)
        )
        .scalars()
        .all()
    )
    chunks = (
        db.execute(
            select(DocumentChunk)
            .where(DocumentChunk.professor_id == professor_id)
            .order_by(DocumentChunk.document_id, DocumentChunk.chunk_index)
        )
        .scalars()
        .all()
    )
    return ProfessorDetailOut(
        professor=ProfessorOut.model_validate(professor),
        documents=[DocumentOut.model_validate(d) for d in documents],
        chunks=[ChunkOut.model_validate(c) for c in chunks],
    )


@router.get("/filters", response_model=FiltersOut)
def filters(db: Session = Depends(get_db)) -> FiltersOut:
    universities = (
        db.execute(select(Professor.affiliation).distinct().order_by(Professor.affiliation))
        .scalars()
        .all()
    )
    countries = (
        db.execute(
            select(Professor.country)
            .where(Professor.country.is_not(None))
            .distinct()
            .order_by(Professor.country)
        )
        .scalars()
        .all()
    )
    return FiltersOut(universities=list(universities), countries=list(countries))
