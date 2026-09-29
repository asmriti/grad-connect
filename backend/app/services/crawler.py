"""Website crawler for professor homepages.

Fetches the homepage, extracts internal links, prioritizes research-relevant
pages, and crawls up to `max_pages` pages on the professor's own site.
Pages that need JavaScript rendering (or fail) are logged and skipped —
no browser automation in the MVP.
"""

from __future__ import annotations

import hashlib
import logging
import threading
import time
from dataclasses import dataclass
from urllib.parse import urlsplit
from urllib.robotparser import RobotFileParser

import httpx

from app.services.extractor import ExtractedPage, extract_links, extract_page

logger = logging.getLogger(__name__)

# Terms that suggest a page is research-relevant (matched against URL + anchor
# text + title). Scoring, not a hard filter: unmatched internal pages still
# get crawled if budget remains.
RELEVANT_TERMS = (
    "research",
    "publication",
    "publications",
    "project",
    "projects",
    "lab",
    "group",
    "student",
    "students",
    "phd",
    "graduate",
    "prospective",
    "join",
    "opening",
    "openings",
    "position",
    "positions",
    "news",
    "teaching",
    "bio",
    "about",
)

SKIP_EXTENSIONS = (
    ".pdf", ".ps", ".zip", ".gz", ".tar", ".doc", ".docx", ".ppt", ".pptx",
    ".xls", ".xlsx", ".jpg", ".jpeg", ".png", ".gif", ".svg", ".mp4", ".mp3",
    ".bib", ".txt", ".ics", ".css", ".js", ".xml", ".rss",
)


@dataclass
class CrawledPage:
    url: str
    title: str | None
    clean_text: str
    page_type: str  # "homepage" | "subpage"
    content_hash: str
    http_status: int
    sections: list  # list[Section] from the extractor


class HostRateLimiter:
    """Enforces a minimum interval between requests to the same host.

    Professors cluster heavily on a few institutional hosts (125 of 417 are on
    www.cs.cmu.edu), so crawling many professors in parallel would otherwise
    hammer a handful of servers. Requests to *different* hosts never block
    each other; requests to the same host queue up.
    """

    def __init__(self, min_interval: float) -> None:
        self.min_interval = min_interval
        self._next_allowed: dict[str, float] = {}
        self._lock = threading.Lock()

    def wait(self, host: str) -> None:
        if self.min_interval <= 0:
            return
        while True:
            with self._lock:
                now = time.monotonic()
                earliest = self._next_allowed.get(host, 0.0)
                if now >= earliest:
                    self._next_allowed[host] = now + self.min_interval
                    return
                delay = earliest - now
            time.sleep(delay)


class RobotsCache:
    """Per-host robots.txt rules, fetched once and cached.

    We are crawling hundreds of real university sites; honouring robots.txt is
    the baseline for doing that responsibly. A missing or unreadable
    robots.txt means "allowed", per the usual convention.
    """

    def __init__(self, client: httpx.Client, user_agent: str, limiter: "HostRateLimiter | None" = None) -> None:
        self._client = client
        self._user_agent = user_agent
        self._limiter = limiter
        self._parsers: dict[str, RobotFileParser | None] = {}
        self._lock = threading.Lock()
        self._host_locks: dict[str, threading.Lock] = {}

    def _lock_for(self, host: str) -> threading.Lock:
        with self._lock:
            return self._host_locks.setdefault(host, threading.Lock())

    def _parser_for(self, scheme: str, host: str) -> RobotFileParser | None:
        with self._lock:
            if host in self._parsers:
                return self._parsers[host]
        # Fetch outside the global lock, but once per host.
        with self._lock_for(host):
            with self._lock:
                if host in self._parsers:
                    return self._parsers[host]
            parser: RobotFileParser | None = None
            try:
                if self._limiter is not None:
                    self._limiter.wait(host)
                response = self._client.get(f"{scheme}://{host}/robots.txt")
                if response.status_code < 400 and response.text.strip():
                    parser = RobotFileParser()
                    parser.parse(response.text.splitlines())
            except httpx.HTTPError as exc:
                logger.debug("robots.txt unavailable for %s: %s", host, exc)
            with self._lock:
                self._parsers[host] = parser
            return parser

    def allowed(self, url: str) -> bool:
        parts = urlsplit(url)
        if not parts.netloc:
            return False
        parser = self._parser_for(parts.scheme or "https", parts.netloc)
        if parser is None:
            return True
        return parser.can_fetch(self._user_agent, url)


def content_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _host(url: str) -> str:
    host = urlsplit(url).netloc.lower()
    return host[4:] if host.startswith("www.") else host


def is_same_site(url: str, base_url: str) -> bool:
    """True if `url` belongs to the professor's own site (www-insensitive)."""
    return _host(url) == _host(base_url)


def relevance_score(url: str, anchor_text: str = "", title: str = "") -> int:
    """How research-relevant a link looks; higher is better."""
    haystack = f"{urlsplit(url).path} {urlsplit(url).query} {anchor_text} {title}".lower()
    return sum(1 for term in RELEVANT_TERMS if term in haystack)


def select_pages_to_crawl(
    links: list[tuple[str, str]], homepage: str, max_pages: int
) -> list[str]:
    """Choose which internal links to crawl, best-scoring first.

    The homepage itself is not in the returned list (it is always fetched
    first by `crawl_professor_site`).
    """
    candidates: list[tuple[int, int, str]] = []
    seen: set[str] = set()
    for order, (url, anchor) in enumerate(links):
        if not is_same_site(url, homepage):
            continue
        if urlsplit(url).path.lower().endswith(SKIP_EXTENSIONS):
            continue
        normalized = url.rstrip("/")
        if normalized in seen or normalized == homepage.rstrip("/"):
            continue
        seen.add(normalized)
        candidates.append((-relevance_score(url, anchor), order, url))
    candidates.sort()
    return [url for _, _, url in candidates[: max(0, max_pages - 1)]]


def fetch_page(
    client: httpx.Client,
    url: str,
    limiter: HostRateLimiter | None = None,
    robots: RobotsCache | None = None,
) -> httpx.Response | None:
    if robots is not None and not robots.allowed(url):
        logger.info("disallowed by robots.txt, skipping: %s", url)
        return None
    if limiter is not None:
        limiter.wait(urlsplit(url).netloc)
    try:
        response = client.get(url)
    except httpx.HTTPError as exc:
        logger.warning("fetch failed for %s: %s", url, exc)
        return None
    content_type = response.headers.get("content-type", "")
    if "html" not in content_type and "text" not in content_type:
        logger.info("skipping non-HTML content at %s (%s)", url, content_type)
        return None
    return response


def looks_javascript_only(page: ExtractedPage) -> bool:
    """Heuristic: page rendered almost no text → likely JS-only."""
    return len(page.clean_text) < 80


def crawl_professor_site(
    client: httpx.Client,
    homepage: str,
    max_pages: int,
    limiter: HostRateLimiter | None = None,
    robots: RobotsCache | None = None,
) -> list[CrawledPage]:
    """Crawl a professor's site starting at the homepage. Never raises for
    per-page failures; returns whatever could be fetched."""
    pages: list[CrawledPage] = []

    response = fetch_page(client, homepage, limiter, robots)
    if response is None or response.status_code >= 400:
        status = response.status_code if response is not None else 0
        logger.warning("homepage unavailable (%s): %s", status, homepage)
        return pages

    final_url = str(response.url)  # after redirects
    extracted = extract_page(response.text)
    if looks_javascript_only(extracted):
        logger.warning("homepage appears to need JavaScript rendering: %s", homepage)
    pages.append(
        CrawledPage(
            url=homepage,
            title=extracted.title,
            clean_text=extracted.clean_text,
            page_type="homepage",
            content_hash=content_hash(extracted.clean_text),
            http_status=response.status_code,
            sections=extracted.sections,
        )
    )

    links = extract_links(response.text, final_url)
    seen_hashes = {pages[0].content_hash}
    for url in select_pages_to_crawl(links, final_url, max_pages):
        sub_response = fetch_page(client, url, limiter, robots)
        if sub_response is None or sub_response.status_code >= 400:
            continue
        sub_extracted = extract_page(sub_response.text)
        if looks_javascript_only(sub_extracted):
            logger.info("skipping near-empty (likely JS-rendered) page: %s", url)
            continue
        digest = content_hash(sub_extracted.clean_text)
        if digest in seen_hashes:
            continue  # duplicate content under a different URL
        seen_hashes.add(digest)
        pages.append(
            CrawledPage(
                url=url,
                title=sub_extracted.title,
                clean_text=sub_extracted.clean_text,
                page_type="subpage",
                content_hash=digest,
                http_status=sub_response.status_code,
                sections=sub_extracted.sections,
            )
        )
        if len(pages) >= max_pages:
            break
    return pages


def _ssl_context():
    """Verify TLS against the OS trust store (like a browser) instead of
    Python's bundled CA list. Several university servers send incomplete
    certificate chains; the OS verifier fetches the missing intermediates,
    certifi does not. Falls back to httpx's default when truststore is
    unavailable. Verification itself is never disabled."""
    try:
        import ssl

        import truststore

        return truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    except ImportError:
        return True


def make_client(timeout: float, user_agent: str, max_connections: int = 20) -> httpx.Client:
    """httpx.Client is thread-safe, so one client is shared by all crawl
    workers; politeness is enforced by HostRateLimiter, not by the pool size."""
    return httpx.Client(
        timeout=timeout,
        follow_redirects=True,
        verify=_ssl_context(),
        headers={"User-Agent": user_agent},
        limits=httpx.Limits(
            max_connections=max_connections,
            max_keepalive_connections=max_connections,
        ),
    )


def interleave_by_host(items: list, host_of) -> list:
    """Reorder so consecutive items rarely share a host.

    Crawl workers pull from this list, so spreading hosts keeps them working
    in parallel instead of all queueing behind one host's rate limit.
    """
    groups: dict[str, list] = {}
    for item in items:
        groups.setdefault(host_of(item), []).append(item)
    ordered: list = []
    queues = list(groups.values())
    while queues:
        still_filling = []
        for queue in queues:
            ordered.append(queue.pop(0))
            if queue:
                still_filling.append(queue)
        queues = still_filling
    return ordered
