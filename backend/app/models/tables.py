"""SQLAlchemy ORM models.

Structured, filterable facts live in relational columns; natural-language
website content lives in `document_chunks` with a pgvector embedding.
"""

from datetime import datetime, timezone
from typing import Optional

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class Professor(Base):
    __tablename__ = "professors"
    # A professor is uniquely identified by (name, affiliation): the same name
    # can exist at two universities, but within one university a duplicate
    # name+affiliation row is the same person (matches CSRankings semantics).
    __table_args__ = (UniqueConstraint("name", "affiliation", name="uq_professor_name_affiliation"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    affiliation: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    homepage: Mapped[str] = mapped_column(String(2048), nullable=False)
    scholar_id: Mapped[Optional[str]] = mapped_column(String(64))
    orcid: Mapped[Optional[str]] = mapped_column(String(32))
    # Not present in the current CSV; kept as a nullable, filterable column so
    # metadata filtering works as soon as the data exists.
    country: Mapped[Optional[str]] = mapped_column(String(128), index=True)

    documents: Mapped[list["Document"]] = relationship(
        back_populates="professor", cascade="all, delete-orphan"
    )
    chunks: Mapped[list["DocumentChunk"]] = relationship(
        back_populates="professor", cascade="all, delete-orphan"
    )


class Document(Base):
    """One crawled web page belonging to a professor.

    Raw HTML is intentionally not persisted (only cleaned text + metadata) to
    keep the database small; `content_hash` detects unchanged pages across
    crawls so they are not re-chunked/re-embedded.
    """

    __tablename__ = "documents"
    __table_args__ = (UniqueConstraint("professor_id", "url", name="uq_document_professor_url"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    professor_id: Mapped[int] = mapped_column(
        ForeignKey("professors.id", ondelete="CASCADE"), nullable=False, index=True
    )
    url: Mapped[str] = mapped_column(String(2048), nullable=False)
    title: Mapped[Optional[str]] = mapped_column(String(1024))
    clean_text: Mapped[Optional[str]] = mapped_column(Text)
    page_type: Mapped[Optional[str]] = mapped_column(String(64))
    content_hash: Mapped[Optional[str]] = mapped_column(String(64), index=True)
    http_status: Mapped[Optional[int]] = mapped_column(Integer)
    crawled_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )

    professor: Mapped[Professor] = relationship(back_populates="documents")
    chunks: Mapped[list["DocumentChunk"]] = relationship(
        back_populates="document", cascade="all, delete-orphan"
    )


class DocumentChunk(Base):
    __tablename__ = "document_chunks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    professor_id: Mapped[int] = mapped_column(
        ForeignKey("professors.id", ondelete="CASCADE"), nullable=False, index=True
    )
    document_id: Mapped[int] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True
    )
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    # Dimension is set at DDL time by scripts/init_db.py from the embedding
    # model; `Vector` without a fixed dim accepts any dimension at the ORM
    # level, so the ORM stays model-agnostic.
    embedding: Mapped[list[float]] = mapped_column(Vector(), nullable=True)
    page_title: Mapped[Optional[str]] = mapped_column(String(1024))
    heading: Mapped[Optional[str]] = mapped_column(String(512))
    url: Mapped[str] = mapped_column(String(2048), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    professor: Mapped[Professor] = relationship(back_populates="chunks")
    document: Mapped[Document] = relationship(back_populates="chunks")
