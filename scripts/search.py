"""CLI semantic search — debug the retrieval pipeline without the frontend.

Usage:
    python scripts/search.py "professors working on human computer interaction"
    python scripts/search.py "machine learning" --university "Stanford University" --limit 5
"""

import _bootstrap  # noqa: F401

import argparse
import textwrap

from app.db.session import get_sessionmaker
from app.services.embeddings import get_embedding_service
from app.services.search import search_professors


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("query", help="natural-language research query")
    parser.add_argument("--university", default=None)
    parser.add_argument("--country", default=None)
    parser.add_argument("--limit", type=int, default=10)
    args = parser.parse_args()

    embedder = get_embedding_service()
    query_embedding = embedder.embed_query(args.query)

    with get_sessionmaker()() as session:
        page = search_professors(
            session,
            query_embedding,
            limit=args.limit,
            university=args.university,
            country=args.country,
        )
    results = page.results

    if not results:
        print("No results. Have you run scripts/index.py?")
        return

    if page.total > len(results):
        print(f"Showing top {len(results)} of {page.total} matching professors.\n")

    for rank, result in enumerate(results, start=1):
        professor = result.professor
        print(f"{rank}. {professor.name}")
        print(f"   {professor.affiliation}" + (f" ({professor.country})" if professor.country else ""))
        print(f"   Similarity: {result.similarity:.2f}")
        for evidence in result.evidence[:2]:
            snippet = textwrap.shorten(evidence.text.replace("\n", " "), width=220)
            print(f"\n   Evidence: {snippet}")
            print(f"   URL: {evidence.url}")
        print()


if __name__ == "__main__":
    main()
