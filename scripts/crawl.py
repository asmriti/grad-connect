"""Crawl professor websites and store cleaned pages (no chunking/embedding).

Useful for inspecting crawler behavior; scripts/index.py runs the whole
pipeline including this step.

Usage:
    python scripts/crawl.py [--limit N] [--professor ID]
"""

import _bootstrap  # noqa: F401

import argparse
import logging

from sqlalchemy import delete, select

from app.config import get_settings
from app.db.session import get_sessionmaker
from app.models.tables import Document, DocumentChunk, Professor
from app.services.crawler import crawl_professor_site, make_client

logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--professor", type=int, default=None)
    args = parser.parse_args()

    settings = get_settings()
    with get_sessionmaker()() as session:
        stmt = select(Professor).order_by(Professor.id)
        if args.professor is not None:
            stmt = stmt.where(Professor.id == args.professor)
        if args.limit is not None:
            stmt = stmt.limit(args.limit)
        professors = session.execute(stmt).scalars().all()

        with make_client(settings.crawl_timeout_seconds, settings.crawl_user_agent) as client:
            for i, professor in enumerate(professors, start=1):
                print(f"[{i}/{len(professors)}] {professor.name}")
                pages = crawl_professor_site(
                    client, professor.homepage, settings.max_pages_per_professor
                )
                print(f"  Pages crawled: {len(pages)}")
                for page in pages:
                    existing = session.execute(
                        select(Document).where(
                            Document.professor_id == professor.id,
                            Document.url == page.url,
                        )
                    ).scalar_one_or_none()
                    if existing is not None and existing.content_hash == page.content_hash:
                        continue
                    if existing is None:
                        existing = Document(professor_id=professor.id, url=page.url)
                        session.add(existing)
                    else:
                        session.execute(
                            delete(DocumentChunk).where(DocumentChunk.document_id == existing.id)
                        )
                    existing.title = page.title
                    existing.clean_text = page.clean_text
                    existing.page_type = page.page_type
                    existing.content_hash = page.content_hash
                    existing.http_status = page.http_status
                session.commit()


if __name__ == "__main__":
    main()
