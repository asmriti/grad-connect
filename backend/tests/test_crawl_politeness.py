"""Tests for concurrent-crawl politeness: per-host rate limiting, robots.txt,
and host interleaving."""

import threading
import time

import httpx
import pytest

from app.services.crawler import (
    HostRateLimiter,
    RobotsCache,
    crawl_professor_site,
    fetch_page,
    interleave_by_host,
)


def test_rate_limiter_spaces_requests_to_same_host():
    limiter = HostRateLimiter(0.05)
    start = time.monotonic()
    for _ in range(4):
        limiter.wait("a.edu")
    elapsed = time.monotonic() - start
    # 4 requests at 0.05s spacing => at least 3 gaps
    assert elapsed >= 0.15


def test_rate_limiter_does_not_block_across_hosts():
    limiter = HostRateLimiter(0.2)
    start = time.monotonic()
    for host in ("a.edu", "b.edu", "c.edu", "d.edu"):
        limiter.wait(host)
    assert time.monotonic() - start < 0.1  # distinct hosts never wait


def test_rate_limiter_is_thread_safe():
    limiter = HostRateLimiter(0.02)
    hits: list[float] = []
    lock = threading.Lock()

    def worker():
        limiter.wait("shared.edu")
        with lock:
            hits.append(time.monotonic())

    threads = [threading.Thread(target=worker) for _ in range(6)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    hits.sort()
    gaps = [b - a for a, b in zip(hits, hits[1:])]
    assert len(hits) == 6
    # every consecutive pair respects the interval (small tolerance for timing)
    assert all(g >= 0.015 for g in gaps), gaps


def test_rate_limiter_zero_interval_is_a_noop():
    limiter = HostRateLimiter(0)
    start = time.monotonic()
    for _ in range(50):
        limiter.wait("a.edu")
    assert time.monotonic() - start < 0.05


def _client(handler) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=True)


ROBOTS_DENY = "User-agent: *\nDisallow: /private\n"


def test_robots_blocks_disallowed_paths():
    def handler(request):
        if request.url.path == "/robots.txt":
            return httpx.Response(200, text=ROBOTS_DENY, headers={"content-type": "text/plain"})
        return httpx.Response(200, text="<html><body><p>ok</p></body></html>",
                              headers={"content-type": "text/html"})

    with _client(handler) as client:
        robots = RobotsCache(client, "test-bot")
        assert robots.allowed("https://x.edu/public")
        assert not robots.allowed("https://x.edu/private/notes")


def test_robots_missing_file_allows_everything():
    def handler(request):
        if request.url.path == "/robots.txt":
            return httpx.Response(404, text="")
        return httpx.Response(200, text="ok", headers={"content-type": "text/html"})

    with _client(handler) as client:
        robots = RobotsCache(client, "test-bot")
        assert robots.allowed("https://x.edu/anything")


def test_robots_fetched_once_per_host():
    calls = {"robots": 0}

    def handler(request):
        if request.url.path == "/robots.txt":
            calls["robots"] += 1
            return httpx.Response(200, text=ROBOTS_DENY, headers={"content-type": "text/plain"})
        return httpx.Response(200, text="ok", headers={"content-type": "text/html"})

    with _client(handler) as client:
        robots = RobotsCache(client, "test-bot")
        for _ in range(5):
            robots.allowed("https://x.edu/page")
        assert calls["robots"] == 1


def test_fetch_page_respects_robots():
    def handler(request):
        if request.url.path == "/robots.txt":
            return httpx.Response(200, text=ROBOTS_DENY, headers={"content-type": "text/plain"})
        return httpx.Response(200, text="<html><body><p>hello</p></body></html>",
                              headers={"content-type": "text/html"})

    with _client(handler) as client:
        robots = RobotsCache(client, "test-bot")
        assert fetch_page(client, "https://x.edu/private/x", robots=robots) is None
        assert fetch_page(client, "https://x.edu/ok", robots=robots) is not None


def test_crawl_skips_robots_disallowed_subpages():
    home = """<html><head><title>H</title></head><body>
    <p>Research in distributed systems, formal verification methods, and fault
    tolerance at very large scale across many datacenters worldwide.</p>
    <a href="/private/secret">Research secret</a><a href="/research">Research</a>
    </body></html>"""
    sub = """<html><head><title>R</title></head><body>
    <p>We study consensus protocols, fault tolerant replication, and the
    practical performance of state machine replication in production.</p>
    </body></html>"""

    def handler(request):
        path = request.url.path
        if path == "/robots.txt":
            return httpx.Response(200, text=ROBOTS_DENY, headers={"content-type": "text/plain"})
        body = home if path == "/" else sub
        return httpx.Response(200, text=body, headers={"content-type": "text/html"})

    with _client(handler) as client:
        robots = RobotsCache(client, "test-bot")
        pages = crawl_professor_site(client, "https://x.edu/", 10, robots=robots)
        urls = [p.url for p in pages]
        assert "https://x.edu/research" in urls
        assert not any("/private/" in u for u in urls)


def test_interleave_spreads_hosts():
    items = [f"a{i}" for i in range(5)] + ["b1", "b2"] + ["c1"]
    host = lambda s: s[0]  # noqa: E731
    ordered = interleave_by_host(items, host)
    assert len(ordered) == len(items)
    assert set(ordered) == set(items)
    # the three hosts should lead the ordering rather than all of 'a' first
    assert {host(x) for x in ordered[:3]} == {"a", "b", "c"}


def test_interleave_handles_single_host():
    items = ["a1", "a2", "a3"]
    assert interleave_by_host(items, lambda s: "a") == items


def test_interleave_empty():
    assert interleave_by_host([], lambda s: s) == []
