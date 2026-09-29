"""Resume → professor matching.

A resume (uploaded or pasted) is chunked, each chunk is embedded as a *query*
(bge's query prefix, same as topic search — professor chunks stay the passage
side of the index), and each chunk searches the existing document_chunks
index. Results aggregate to professors by their best (resume chunk, professor
chunk) pair.

Privacy: nothing here persists. The file bytes, extracted text, and resume
embeddings live only for the duration of the request.

No generative LLM anywhere: extraction is pypdf / python-docx / plain text,
matching is embedding cosine similarity only.
"""

from __future__ import annotations

import io
import re
from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from app.models.tables import Professor
from app.services.chunker import Chunk, chunk_sections
from app.services.embeddings import EmbeddingProvider
from app.services.extractor import Section
from app.services.search import search_chunks

# bge-small truncates at 512 tokens, so a resume must be chunked or only its
# beginning would ever match. 20 chunks (~12k tokens) covers any real resume;
# beyond that we keep the first 20 and tell the caller.
MAX_RESUME_CHUNKS = 20

MAX_UPLOAD_BYTES = 5 * 1024 * 1024

ALLOWED_EXTENSIONS = (".pdf", ".docx", ".txt", ".md")

# Extracted text shorter than this can't describe experience meaningfully —
# typical for scanned (image-only) PDFs.
MIN_TEXT_CHARS = 30

EXCERPT_CHARS = 280


class ResumeError(ValueError):
    """User-facing extraction/validation problem (maps to HTTP 400)."""


@dataclass
class MatchPair:
    resume_excerpt: str
    text: str  # professor chunk
    url: str
    page_title: str | None
    heading: str | None
    similarity: float


@dataclass
class ProfessorMatch:
    professor: Professor
    similarity: float  # best pair
    matches: list[MatchPair] = field(default_factory=list)


@dataclass
class MatchResult:
    results: list[ProfessorMatch]
    total: int
    chunks_used: int
    truncated: bool


# ---------------------------------------------------------------------------
# Extraction
# ---------------------------------------------------------------------------

def extract_resume_text(filename: str, content: bytes) -> str:
    """Extract plain text from an uploaded resume. Raises ResumeError with a
    plain message for anything unusable. Never executes or renders the file."""
    if len(content) > MAX_UPLOAD_BYTES:
        raise ResumeError("File is larger than 5 MB.")
    if not content:
        raise ResumeError("The uploaded file is empty.")

    name = filename.lower()
    if name.endswith(".pdf"):
        text = _extract_pdf(content)
    elif name.endswith(".docx"):
        text = _extract_docx(content)
    elif name.endswith((".txt", ".md")):
        text = _extract_plain(content)
    else:
        raise ResumeError(
            "Unsupported file type. Upload a .pdf, .docx, .txt or .md file, "
            "or paste the text instead."
        )

    text = _normalize(text)
    if len(text) < MIN_TEXT_CHARS:
        raise ResumeError(
            "No readable text found in the file (a scanned PDF has none). "
            "Paste the resume text instead."
        )
    return text


def _extract_pdf(content: bytes) -> str:
    from pypdf import PdfReader

    try:
        reader = PdfReader(io.BytesIO(content))
        return "\n\n".join(page.extract_text() or "" for page in reader.pages)
    except ResumeError:
        raise
    except Exception as exc:
        raise ResumeError("The PDF could not be read. Paste the text instead.") from exc


def _extract_docx(content: bytes) -> str:
    import docx

    try:
        document = docx.Document(io.BytesIO(content))
    except Exception as exc:
        raise ResumeError("The .docx file could not be read. Paste the text instead.") from exc
    parts = [p.text for p in document.paragraphs]
    for table in document.tables:
        for row in table.rows:
            parts.extend(cell.text for cell in row.cells)
    return "\n".join(parts)


def _extract_plain(content: bytes) -> str:
    if b"\x00" in content:
        raise ResumeError("The file is not plain text.")
    try:
        return content.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ResumeError("The file is not UTF-8 text.") from exc


_CONTROL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]")


def _normalize(text: str) -> str:
    text = _CONTROL_RE.sub("", text.replace("\r\n", "\n").replace("\r", "\n"))
    return text.strip()


# ---------------------------------------------------------------------------
# Chunking
# ---------------------------------------------------------------------------

def chunk_resume(
    text: str, chunk_size: int, chunk_overlap: int
) -> tuple[list[Chunk], bool]:
    """Split resume text into embedding-sized chunks via the shared chunker.

    Blank-line breaks split the resume into sections (headings stay part of
    the text — no LLM, no guessing which line is a heading); the chunker then
    packs them and skips fragments below its minimum. Returns (chunks,
    truncated_to_cap).
    """
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    sections = [Section(heading=None, text=p) for p in paragraphs] or [
        Section(heading=None, text=text)
    ]
    chunks = chunk_sections(sections, chunk_size, chunk_overlap)
    # Re-index after the chunker's own skipping so indexes stay sequential.
    for i, chunk in enumerate(chunks):
        chunk.chunk_index = i
    truncated = len(chunks) > MAX_RESUME_CHUNKS
    return chunks[:MAX_RESUME_CHUNKS], truncated


def excerpt(text: str, max_chars: int = EXCERPT_CHARS) -> str:
    flat = re.sub(r"\s+", " ", text).strip()
    if len(flat) <= max_chars:
        return flat
    return flat[:max_chars].rsplit(" ", 1)[0] + "…"


# ---------------------------------------------------------------------------
# Matching
# ---------------------------------------------------------------------------

def aggregate_pairs(
    pairs: list[tuple[int, str, object, object, float]],
    matches_per_professor: int = 3,
) -> list[ProfessorMatch]:
    """Aggregate (resume_chunk_index, resume_text, prof_chunk, professor,
    similarity) pairs into ranked professors.

    A professor's score is their best pair. Evidence keeps up to 3 pairs,
    preferring pairs from *different* resume chunks first so one repeated
    resume sentence does not fill every slot; remaining slots then take the
    next-best pairs regardless of resume chunk.
    """
    by_professor: dict[int, list[tuple[int, str, object, float]]] = {}
    professors: dict[int, object] = {}
    for chunk_index, resume_text, prof_chunk, professor, similarity in pairs:
        by_professor.setdefault(professor.id, []).append(
            (chunk_index, resume_text, prof_chunk, similarity)
        )
        professors[professor.id] = professor

    results: list[ProfessorMatch] = []
    for professor_id, prof_pairs in by_professor.items():
        prof_pairs.sort(key=lambda p: p[3], reverse=True)

        picked: list[tuple[int, str, object, float]] = []
        seen_resume_chunks: set[int] = set()
        seen_prof_chunks: set[int] = set()
        # Pass 1: best pair per distinct resume chunk.
        for pair in prof_pairs:
            if len(picked) >= matches_per_professor:
                break
            if pair[0] in seen_resume_chunks or id(pair[2]) in seen_prof_chunks:
                continue
            picked.append(pair)
            seen_resume_chunks.add(pair[0])
            seen_prof_chunks.add(id(pair[2]))
        # Pass 2: fill remaining slots with the next-best distinct pairs.
        for pair in prof_pairs:
            if len(picked) >= matches_per_professor:
                break
            if pair in picked or id(pair[2]) in seen_prof_chunks:
                continue
            picked.append(pair)
            seen_prof_chunks.add(id(pair[2]))
        picked.sort(key=lambda p: p[3], reverse=True)

        results.append(
            ProfessorMatch(
                professor=professors[professor_id],
                similarity=prof_pairs[0][3],
                matches=[
                    MatchPair(
                        resume_excerpt=excerpt(resume_text),
                        text=prof_chunk.text,
                        url=prof_chunk.url,
                        page_title=prof_chunk.page_title,
                        heading=prof_chunk.heading,
                        similarity=similarity,
                    )
                    for _, resume_text, prof_chunk, similarity in picked
                ],
            )
        )
    results.sort(key=lambda r: r.similarity, reverse=True)
    return results


def match_resume(
    session: Session,
    embedder: EmbeddingProvider,
    resume_text: str,
    chunk_size: int,
    chunk_overlap: int,
    limit: int = 10,
    offset: int = 0,
    university: str | None = None,
    country: str | None = None,
    min_similarity: float | None = None,
) -> MatchResult:
    """Chunk the resume, embed each chunk as a query, search the existing
    professor chunk index, and aggregate to a ranked professor page.

    Below-floor chunks simply contribute nothing: an unrelated resume returns
    an empty list, never its nearest neighbours.
    """
    chunks, truncated = chunk_resume(resume_text, chunk_size, chunk_overlap)
    if not chunks:
        return MatchResult(results=[], total=0, chunks_used=0, truncated=False)

    embeddings = embedder.embed_queries([chunk.text for chunk in chunks])

    pairs: list[tuple[int, str, object, object, float]] = []
    for chunk, embedding in zip(chunks, embeddings):
        rows = search_chunks(
            session,
            embedding,
            university=university,
            country=country,
            min_similarity=min_similarity,
        )
        for prof_chunk, professor, similarity in rows:
            pairs.append((chunk.chunk_index, chunk.text, prof_chunk, professor, similarity))

    ranked = aggregate_pairs(pairs)
    return MatchResult(
        results=ranked[offset : offset + limit],
        total=len(ranked),
        chunks_used=len(chunks),
        truncated=truncated,
    )
