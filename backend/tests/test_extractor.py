from app.services.extractor import extract_links, extract_page

HTML = """
<html>
  <head><title> Prof. Jane Smith — HCI Lab </title><style>p {color:red}</style></head>
  <body>
    <nav><a href="/hidden">nav link</a>should not appear</nav>
    <header>site header</header>
    <h1>Jane Smith</h1>
    <p>Professor of Computer Science.</p>
    <h2>Research Interests</h2>
    <p>Human computer interaction and accessibility.</p>
    <ul><li>Assistive technology</li><li>Eye tracking</li></ul>
    <script>alert("nope")</script>
    <form><input name="q"></form>
    <footer>copyright</footer>
  </body>
</html>
"""


def test_extract_page_removes_boilerplate_tags():
    page = extract_page(HTML)
    assert "alert(" not in page.clean_text
    assert "site header" not in page.clean_text
    assert "copyright" not in page.clean_text
    assert "nav link" not in page.clean_text


def test_extract_page_preserves_headings_as_sections():
    page = extract_page(HTML)
    assert page.title == "Prof. Jane Smith — HCI Lab"
    headings = [s.heading for s in page.sections]
    assert "Research Interests" in headings
    research = next(s for s in page.sections if s.heading == "Research Interests")
    assert "Human computer interaction" in research.text
    assert "Assistive technology" in research.text
    # heading text appears before its section body in the flat clean text
    assert page.clean_text.index("Research Interests") < page.clean_text.index(
        "Human computer interaction"
    )


def test_extract_page_fallback_without_block_markup():
    page = extract_page("<html><body>just some bare text here</body></html>")
    assert "just some bare text here" in page.clean_text


def test_extract_links_resolves_and_filters():
    html = """
    <a href="/research">Research</a>
    <a href="https://other.edu/page">External</a>
    <a href="mailto:x@y.z">mail</a>
    <a href="#section">anchor</a>
    <a href="pubs.html#recent">Publications</a>
    """
    links = extract_links(html, "https://prof.example.edu/home/")
    urls = [u for u, _ in links]
    assert "https://prof.example.edu/research" in urls
    assert "https://prof.example.edu/home/pubs.html" in urls  # fragment stripped
    assert "https://other.edu/page" in urls  # cross-site kept here; crawler filters
    assert all(not u.startswith("mailto:") for u in urls)
    assert len(urls) == 3


def test_extract_page_strips_nul_and_control_bytes():
    """Regression: PostgreSQL text columns reject NUL (0x00) bytes, and one
    real faculty page contained them."""
    html = "<html><body><h2>Res\x00earch</h2><p>NUL\x00 and bell\x07 bytes gone.</p></body></html>"
    page = extract_page(html)
    assert "\x00" not in page.clean_text
    assert "\x07" not in page.clean_text
    assert "Research" in page.clean_text
    assert "NUL and bell bytes gone." in page.clean_text


def test_extract_links_skips_malformed_href():
    """Regression: a malformed href (here an invalid IPv6-style authority)
    made urljoin raise and took the whole professor's crawl down with it."""
    html = '<a href="http://[broken">bad</a><a href="/ok">ok</a>'
    links = extract_links(html, "https://prof.edu/")
    assert [u for u, _ in links] == ["https://prof.edu/ok"]
