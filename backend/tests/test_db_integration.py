"""Integration tests against real PostgreSQL + pgvector.

Skipped automatically when no database is reachable. Point TEST_DATABASE_URL
at a scratch database (tables are dropped/recreated per run):

    TEST_DATABASE_URL=postgresql+psycopg://localhost/grad_connect_test pytest
"""

import os

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from app.db.init import init_db
from app.models.tables import Base, Document, DocumentChunk, Professor
from app.services.ingest import ProfessorRecord, upsert_professors
from app.services.search import search_professors

TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL", "postgresql+psycopg://localhost/grad_connect_test"
)

DIM = 4


def _database_available() -> bool:
    try:
        engine = create_engine(TEST_DATABASE_URL)
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except Exception:
        return False


pytestmark = pytest.mark.skipif(
    not _database_available(), reason="test database not reachable"
)


@pytest.fixture
def session():
    engine = create_engine(TEST_DATABASE_URL)
    Base.metadata.drop_all(engine)
    init_db(engine, embedding_dim=DIM)
    with Session(engine) as sess:
        yield sess
    Base.metadata.drop_all(engine)
    engine.dispose()


def _seed(session: Session) -> None:
    profs = [
        Professor(name="Ada", affiliation="University X", homepage="https://x.edu/ada", country="United States"),
        Professor(name="Bob", affiliation="University Y", homepage="https://y.edu/bob", country="Canada"),
    ]
    session.add_all(profs)
    session.flush()
    for prof, base in ((profs[0], [1.0, 0.0, 0.0, 0.0]), (profs[1], [0.0, 1.0, 0.0, 0.0])):
        doc = Document(professor_id=prof.id, url=prof.homepage, content_hash="h")
        session.add(doc)
        session.flush()
        for i, scale in enumerate((1.0, 0.9)):
            vec = [v * scale + (0.1 * i) for v in base]
            session.add(
                DocumentChunk(
                    professor_id=prof.id,
                    document_id=doc.id,
                    chunk_index=i,
                    text=f"{prof.name} chunk {i}",
                    embedding=vec,
                    url=prof.homepage,
                )
            )
    session.commit()


def test_upsert_professors_is_idempotent(session):
    records = [
        ProfessorRecord(name="Ada", affiliation="University X", homepage="https://x.edu/ada"),
        ProfessorRecord(name="Bob", affiliation="University Y", homepage="https://y.edu/bob"),
    ]
    inserted, updated = upsert_professors(session, records)
    assert (inserted, updated) == (2, 0)
    inserted, updated = upsert_professors(session, records)
    assert (inserted, updated) == (0, 0)
    records[0].homepage = "https://x.edu/ada-new"
    inserted, updated = upsert_professors(session, records)
    assert (inserted, updated) == (0, 1)
    assert session.query(Professor).count() == 2


def test_vector_search_ranks_by_cosine_similarity(session):
    _seed(session)
    results = search_professors(session, [1.0, 0.0, 0.0, 0.0], limit=10, min_similarity=0).results
    assert [r.professor.name for r in results] == ["Ada", "Bob"]
    assert results[0].similarity > results[1].similarity
    assert results[0].evidence[0].text.startswith("Ada")


def test_min_similarity_excludes_distant_chunks(session):
    """An off-topic query must return nothing rather than its nearest
    neighbours — the 'xyz returns results' bug."""
    _seed(session)
    # Orthogonal to every seeded vector => similarity ~0 for all chunks.
    off_topic = [0.0, 0.0, 1.0, 0.0]
    assert search_professors(session, off_topic, limit=10, min_similarity=0.62).results == []
    # ...but the same query still returns neighbours when the floor is off.
    assert search_professors(session, off_topic, limit=10, min_similarity=0).results != []


def test_min_similarity_keeps_close_matches(session):
    _seed(session)
    results = search_professors(
        session, [1.0, 0.0, 0.0, 0.0], limit=10, min_similarity=0.62
    ).results
    assert [r.professor.name for r in results] == ["Ada"]
    assert results[0].similarity >= 0.62


def test_min_similarity_defaults_from_settings(session):
    _seed(session)
    from app.config import get_settings

    # Default path (min_similarity=None) must apply the configured floor.
    results = search_professors(session, [0.0, 0.0, 1.0, 0.0], limit=10).results
    assert get_settings().min_similarity > 0
    assert results == []


def test_metadata_filter_university(session):
    """Metadata filtering in isolation: similarity floor off so the filter is
    the only thing narrowing the results."""
    _seed(session)
    results = search_professors(
        session, [1.0, 0.0, 0.0, 0.0], limit=10, university="University Y", min_similarity=0
    ).results
    assert [r.professor.name for r in results] == ["Bob"]


def test_metadata_filter_country(session):
    _seed(session)
    results = search_professors(
        session, [1.0, 0.0, 0.0, 0.0], limit=10, country="Canada", min_similarity=0
    ).results
    assert [r.professor.name for r in results] == ["Bob"]


def test_filter_with_no_match_returns_empty(session):
    _seed(session)
    results = search_professors(
        session, [1.0, 0.0, 0.0, 0.0], limit=10, university="Nowhere U", min_similarity=0
    ).results
    assert results == []


def test_store_page_clamps_oversized_heading_and_title(session):
    """Regression: a >512-char heading (real pages produce them) aborted the
    whole indexing run with StringDataRightTruncation."""
    from app.services.crawler import CrawledPage
    from app.services.extractor import Section
    from app.services.indexer import store_crawled_pages

    class StubEmbedder:
        dimension = DIM

        def embed_texts(self, texts):
            return [[1.0, 0.0, 0.0, 0.0] for _ in texts]

    prof = Professor(name="Cara", affiliation="University Z", homepage="https://z.edu/cara")
    session.add(prof)
    session.flush()

    long_heading = "H" * 700
    long_title = "T" * 1500
    page = CrawledPage(
        url="https://z.edu/cara/notes",
        title=long_title,
        clean_text="body",
        page_type="subpage",
        content_hash="abc123",
        http_status=200,
        sections=[Section(heading=long_heading, text="Some research content. " * 10)],
    )
    stats = store_crawled_pages(session, StubEmbedder(), prof, [page], 600, 100)
    assert stats.error is None
    assert stats.chunks >= 1

    chunk = session.query(DocumentChunk).filter_by(professor_id=prof.id).first()
    assert len(chunk.heading) <= 512
    assert chunk.heading.endswith("…")
    assert len(chunk.page_title) <= 1024


def test_upsert_treats_same_homepage_as_alias(session):
    """A second name variant with the same (affiliation, homepage) must not
    create a duplicate professor row."""
    first = [ProfessorRecord(name="Alex Aiken", affiliation="Stanford University",
                             homepage="https://theory.stanford.edu/~aiken")]
    alias = [ProfessorRecord(name="Alexander Aiken", affiliation="Stanford University",
                             homepage="https://theory.stanford.edu/~aiken",
                             scholar_id="xyz123")]
    assert upsert_professors(session, first) == (1, 0)
    inserted, updated = upsert_professors(session, alias)
    assert inserted == 0  # alias recognised, no new row
    assert session.query(Professor).count() == 1
    prof = session.query(Professor).one()
    assert prof.name == "Alex Aiken"  # first-seen name kept
    assert prof.scholar_id == "xyz123"  # missing fields filled from the alias


def _seed_many(session: Session, n: int) -> None:
    """n professors, each with one chunk; professor i scores lower than i-1."""
    for i in range(n):
        prof = Professor(name=f"Prof{i:02d}", affiliation="University X",
                         homepage=f"https://x.edu/p{i}")
        session.add(prof)
        session.flush()
        doc = Document(professor_id=prof.id, url=prof.homepage, content_hash="h")
        session.add(doc)
        session.flush()
        # decreasing similarity to the query [1,0,0,0] as i grows
        vec = [1.0, 0.02 * i, 0.0, 0.0]
        session.add(DocumentChunk(professor_id=prof.id, document_id=doc.id,
                                  chunk_index=0, text=f"chunk {i}",
                                  embedding=vec, url=prof.homepage))
    session.commit()


def test_pagination_slices_professor_ranking(session):
    _seed_many(session, 25)
    query = [1.0, 0.0, 0.0, 0.0]
    page1 = search_professors(session, query, limit=10, offset=0, min_similarity=0)
    page2 = search_professors(session, query, limit=10, offset=10, min_similarity=0)
    page3 = search_professors(session, query, limit=10, offset=20, min_similarity=0)

    assert page1.total == page2.total == page3.total == 25
    assert len(page1.results) == 10
    assert len(page2.results) == 10
    assert len(page3.results) == 5

    names = [r.professor.name for p in (page1, page2, page3) for r in p.results]
    assert len(set(names)) == 25  # no overlap between pages
    # global ranking is preserved across page boundaries
    assert names == sorted(names)  # Prof00 (closest) ... Prof24


def test_pagination_offset_past_end_is_empty(session):
    _seed_many(session, 3)
    page = search_professors(session, [1.0, 0.0, 0.0, 0.0], limit=10, offset=30,
                             min_similarity=0)
    assert page.results == []
    assert page.total == 3


class _KeywordEmbedder:
    """4-dim stub: direction chosen by keyword, so resume chunks can be
    steered toward or away from seeded professor chunks."""

    dimension = DIM

    def _vec(self, text):
        if "vision" in text:
            return [1.0, 0.0, 0.0, 0.0]  # aligned with Ada's chunks
        if "theory" in text:
            return [0.0, 1.0, 0.0, 0.0]  # aligned with Bob's chunks
        return [0.0, 0.0, 1.0, 0.0]  # orthogonal to everyone

    def embed_texts(self, texts):
        return [self._vec(t) for t in texts]

    def embed_text(self, text):
        return self._vec(text)

    def embed_query(self, text):
        return self._vec(text)

    def embed_queries(self, texts):
        return [self._vec(t) for t in texts]


RESUME_VISION = (
    "Built computer vision pipelines for object detection during my internship, "
    "with plenty of concrete engineering detail to pass the chunk minimum."
)
RESUME_THEORY = (
    "Studied complexity theory and wrote proofs about approximation algorithms, "
    "again described at enough length to form a full resume chunk."
)
RESUME_OFFTOPIC = (
    "Organised the university baking society and managed weekly cake sales with "
    "a small volunteer team across two campuses for three years running."
)


def test_match_resume_merges_chunks_and_ranks_by_best_pair(session):
    from app.services.resume import match_resume

    _seed(session)
    text = RESUME_VISION + "\n\n" + RESUME_THEORY
    result = match_resume(session, _KeywordEmbedder(), text, 600, 100, min_similarity=0.62)
    assert result.chunks_used == 2
    assert not result.truncated
    # Ada's best chunk is exactly [1,0,0,0] (sim 1.0); Bob's best for the
    # theory chunk is [0,1,0,0]. Both professors match, Ada or Bob first by
    # their best pair; both totals counted at professor level.
    assert result.total == 2
    names = [r.professor.name for r in result.results]
    assert set(names) == {"Ada", "Bob"}
    top = result.results[0]
    assert top.similarity >= result.results[1].similarity
    assert top.matches[0].url.startswith("https://")


def test_match_resume_below_floor_returns_empty(session):
    from app.services.resume import match_resume

    _seed(session)
    result = match_resume(
        session, _KeywordEmbedder(), RESUME_OFFTOPIC, 600, 100, min_similarity=0.62
    )
    assert result.chunks_used == 1
    assert result.results == []
    assert result.total == 0


def test_match_resume_university_filter_applies(session):
    from app.services.resume import match_resume

    _seed(session)
    text = RESUME_VISION + "\n\n" + RESUME_THEORY
    result = match_resume(
        session, _KeywordEmbedder(), text, 600, 100,
        university="University Y", min_similarity=0.62,
    )
    assert [r.professor.name for r in result.results] == ["Bob"]
    assert result.total == 1
