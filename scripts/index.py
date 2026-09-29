"""Run the full indexing pipeline: crawl → extract → chunk → embed → store.

Idempotent: unchanged pages (same content hash) are skipped.

Crawling runs across several worker threads, but requests to any single host
are serialised with a delay — professors cluster on a few institutional
servers, so this keeps the crawl fast without hammering them. robots.txt is
honoured per host.

Usage:
    python scripts/index.py                  # index every professor
    python scripts/index.py --limit 10       # only the first N professors
    python scripts/index.py --professor 42   # a single professor by id
    python scripts/index.py --workers 8 --host-delay 1.0
    python scripts/index.py --resume         # skip professors already indexed
"""

import _bootstrap  # noqa: F401

import argparse
import logging
import sys
import time
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from urllib.parse import urlsplit

from sqlalchemy import select

from app.config import get_settings
from app.db.session import get_sessionmaker
from app.models.tables import Document, Professor
from app.services.crawler import (
    HostRateLimiter,
    RobotsCache,
    interleave_by_host,
    make_client,
)
from app.services.embeddings import get_embedding_service
from app.services.indexer import crawl_only, store_crawled_pages

logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=None, help="index only the first N professors")
    parser.add_argument("--professor", type=int, default=None, help="index a single professor id")
    parser.add_argument("--max-pages", type=int, default=None, help="override MAX_PAGES_PER_PROFESSOR")
    parser.add_argument("--workers", type=int, default=8, help="concurrent crawl workers (default 8)")
    parser.add_argument(
        "--host-delay",
        type=float,
        default=1.0,
        help="minimum seconds between requests to the same host (default 1.0)",
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help="skip professors that already have at least one indexed page",
    )
    parser.add_argument(
        "--ignore-robots",
        action="store_true",
        help="do not fetch or honour robots.txt (not recommended)",
    )
    args = parser.parse_args()

    settings = get_settings()
    max_pages = args.max_pages or settings.max_pages_per_professor
    embedder = get_embedding_service()

    with get_sessionmaker()() as session:
        stmt = select(Professor).order_by(Professor.id)
        if args.professor is not None:
            stmt = stmt.where(Professor.id == args.professor)
        if args.resume:
            already = select(Document.professor_id).distinct().scalar_subquery()
            stmt = stmt.where(Professor.id.not_in(already))
        if args.limit is not None:
            stmt = stmt.limit(args.limit)
        professors = session.execute(stmt).scalars().all()

        if not professors:
            print("No professors to index. Run scripts/ingest.py first, or drop --resume.")
            return

        # Worker threads must never touch live ORM objects: a rollback on the
        # main-thread session expires them, and a lazy refresh from a worker
        # raises "concurrent operations are not permitted". Hand workers plain
        # values instead, and keep the ORM objects here keyed by id.
        by_id = {p.id: p for p in professors}
        jobs = [(p.id, p.name, p.homepage) for p in professors]

        # Spread hosts so workers rarely queue behind the same rate limit.
        jobs = interleave_by_host(jobs, lambda j: urlsplit(j[2]).netloc.lower())

        total = len(jobs)
        distinct_hosts = len({urlsplit(j[2]).netloc.lower() for j in jobs})
        print(
            f"Indexing {total} professors across {distinct_hosts} hosts "
            f"({args.workers} workers, {args.host_delay:.1f}s between requests per host)\n"
        )

        limiter = HostRateLimiter(args.host_delay)
        started = time.monotonic()
        done = failed = 0
        total_pages = total_chunks = 0

        with make_client(
            settings.crawl_timeout_seconds,
            settings.crawl_user_agent,
            max_connections=max(args.workers * 2, 10),
        ) as client:
            robots = (
                None
                if args.ignore_robots
                else RobotsCache(client, settings.crawl_user_agent, limiter)
            )

            def crawl(job):
                prof_id, name, homepage = job
                return prof_id, name, crawl_only(
                    client, homepage, max_pages, limiter, robots
                )

            with ThreadPoolExecutor(max_workers=args.workers) as pool:
                pending = set()
                queue = iter(jobs)
                # Keep a bounded number of crawls in flight so crawled text
                # does not pile up in memory ahead of the embedder.
                for job in queue:
                    pending.add(pool.submit(crawl, job))
                    if len(pending) >= args.workers * 3:
                        break

                while pending:
                    finished, pending = wait(pending, return_when=FIRST_COMPLETED)
                    for future in finished:
                        prof_id, name, (pages, error) = future.result()
                        done += 1

                        if error:
                            failed += 1
                            stats_line = error
                        else:
                            stats = store_crawled_pages(
                                session,
                                embedder,
                                by_id[prof_id],
                                pages,
                                settings.chunk_size,
                                settings.chunk_overlap,
                            )
                            total_pages += stats.pages_new_or_changed
                            total_chunks += stats.chunks
                            stats_line = (
                                f"{stats.pages_found} pages, "
                                f"{stats.pages_new_or_changed} new, "
                                f"{stats.chunks} chunks"
                            )
                            if stats.error:
                                failed += 1
                                stats_line += f" | {stats.error}"

                        elapsed = time.monotonic() - started
                        rate = done / elapsed if elapsed else 0
                        eta = (total - done) / rate if rate else 0
                        print(
                            f"[{done}/{total}] {name[:38]:<38} "
                            f"{stats_line}  (eta {eta/60:.0f}m)",
                            flush=True,
                        )

                        # Top the queue back up as slots free.
                        for job in queue:
                            pending.add(pool.submit(crawl, job))
                            break

        elapsed = time.monotonic() - started
        print(
            f"\nDone in {elapsed/60:.1f} minutes. "
            f"{total - failed}/{total} professors indexed without errors. "
            f"{total_pages} pages, {total_chunks} chunks embedded."
        )


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        # Work is committed per professor, so --resume picks up where this left off.
        print("\nInterrupted. Re-run with --resume to continue.", file=sys.stderr)
        sys.exit(130)
