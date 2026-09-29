import httpx

from app.services.crawler import (
    crawl_professor_site,
    is_same_site,
    relevance_score,
    select_pages_to_crawl,
)


def test_is_same_site_www_insensitive():
    assert is_same_site("https://www.example.edu/a", "https://example.edu/")
    assert not is_same_site("https://cs.example.edu/a", "https://example.edu/")
    assert not is_same_site("https://other.com/", "https://example.edu/")


def test_relevance_score_prefers_research_pages():
    assert relevance_score("https://x.edu/research") > relevance_score("https://x.edu/cv")
    assert relevance_score("https://x.edu/p1", anchor_text="Publications") > 0


def test_select_pages_prioritizes_relevant_and_respects_budget():
    homepage = "https://prof.edu/"
    links = [
        ("https://prof.edu/misc", "Misc"),
        ("https://prof.edu/research", "Research"),
        ("https://prof.edu/paper.pdf", "PDF"),
        ("https://other.edu/research", "External research"),
        ("https://prof.edu/students", "Students"),
        ("https://prof.edu/", "Home"),
    ]
    selected = select_pages_to_crawl(links, homepage, max_pages=3)
    assert len(selected) == 2  # homepage takes one slot of the 3
    assert selected[0] in ("https://prof.edu/research", "https://prof.edu/students")
    assert "https://prof.edu/paper.pdf" not in selected
    assert "https://other.edu/research" not in selected
    assert "https://prof.edu/" not in selected


def _mock_client(pages: dict[str, str], status: dict[str, int] | None = None) -> httpx.Client:
    status = status or {}

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if url in pages:
            return httpx.Response(
                status.get(url, 200),
                text=pages[url],
                headers={"content-type": "text/html"},
            )
        return httpx.Response(404, text="not found", headers={"content-type": "text/html"})

    return httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=True)


HOMEPAGE_HTML = """
<html><head><title>Prof Home</title></head><body>
<h1>Prof Jane</h1>
<p>I am a professor working on formal verification and program analysis systems.</p>
<a href="/research">Research</a>
<a href="/hobbies">Hobbies</a>
</body></html>
"""

RESEARCH_HTML = """
<html><head><title>Research</title></head><body>
<h2>Projects</h2>
<p>We build automated theorem provers and SMT solvers for verified compilation.</p>
</body></html>
"""


def test_crawl_professor_site_end_to_end_mocked():
    client = _mock_client(
        {
            "https://prof.edu/": HOMEPAGE_HTML,
            "https://prof.edu/research": RESEARCH_HTML,
            "https://prof.edu/hobbies": "<html><body><p>short</p></body></html>",
        }
    )
    pages = crawl_professor_site(client, "https://prof.edu/", max_pages=10)
    urls = [p.url for p in pages]
    assert urls[0] == "https://prof.edu/"
    assert pages[0].page_type == "homepage"
    assert "https://prof.edu/research" in urls
    # hobbies page has <80 chars of text -> treated as JS-only/empty, skipped
    assert "https://prof.edu/hobbies" not in urls
    research = next(p for p in pages if p.url.endswith("/research"))
    assert "theorem provers" in research.clean_text
    assert research.content_hash != pages[0].content_hash


def test_crawl_survives_dead_homepage():
    client = _mock_client({}, {})
    pages = crawl_professor_site(client, "https://gone.edu/", max_pages=5)
    assert pages == []


def test_crawl_max_pages_respected():
    links = "".join(f'<a href="/research{i}">Research {i}</a>' for i in range(20))
    body = "<p>" + "verification and systems research content " * 5 + "</p>"
    pages_map = {"https://prof.edu/": f"<html><body>{body}{links}</body></html>"}
    for i in range(20):
        pages_map[f"https://prof.edu/research{i}"] = (
            f"<html><body><p>Unique research topic number {i}: "
            + f"subject-{i} " * 30
            + "</p></body></html>"
        )
    client = _mock_client(pages_map)
    pages = crawl_professor_site(client, "https://prof.edu/", max_pages=4)
    assert len(pages) == 4
