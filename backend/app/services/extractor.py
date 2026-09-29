"""HTML → clean, heading-aware text extraction (BeautifulSoup)."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from bs4 import BeautifulSoup

REMOVE_TAGS = ("script", "style", "nav", "footer", "header", "noscript", "form", "iframe", "svg")
HEADING_TAGS = ("h1", "h2", "h3", "h4", "h5", "h6")
BLOCK_TAGS = ("p", "li", "td", "th", "blockquote", "pre", "dd", "dt", "figcaption", "caption")

_WHITESPACE_RE = re.compile(r"[ \t\r\f\v]+")
# C0/C1 control characters (except \n, handled as line structure). Real pages
# occasionally embed NUL bytes, which PostgreSQL text columns reject outright.
_CONTROL_RE = re.compile(r"[\x00-\x08\x0b-\x1f\x7f-\x9f]")


@dataclass
class Section:
    heading: str | None
    text: str


@dataclass
class ExtractedPage:
    title: str | None
    sections: list[Section] = field(default_factory=list)

    @property
    def clean_text(self) -> str:
        parts = []
        for section in self.sections:
            if section.heading:
                parts.append(section.heading)
            parts.append(section.text)
        return "\n\n".join(parts)


def _clean(text: str) -> str:
    return _WHITESPACE_RE.sub(" ", _CONTROL_RE.sub("", text)).strip()


def extract_page(html: str) -> ExtractedPage:
    """Extract title + heading-grouped text blocks from raw HTML.

    Headings are preserved as section labels (e.g. "Research Interests")
    so downstream chunks keep their context for the embedding model.
    """
    soup = BeautifulSoup(html, "html.parser")

    title = None
    if soup.title and soup.title.string:
        title = _clean(soup.title.string) or None

    for tag_name in REMOVE_TAGS:
        for tag in soup.find_all(tag_name):
            tag.decompose()

    root = soup.body or soup
    sections: list[Section] = []
    current_heading: str | None = None
    current_blocks: list[str] = []

    def flush() -> None:
        nonlocal current_blocks
        text = "\n".join(b for b in current_blocks if b)
        if text.strip():
            sections.append(Section(heading=current_heading, text=text))
        current_blocks = []

    for element in root.descendants:
        if getattr(element, "name", None) in HEADING_TAGS:
            flush()
            current_heading = _clean(element.get_text(" ", strip=True)) or None
        elif getattr(element, "name", None) in BLOCK_TAGS:
            # Skip nested block tags (e.g. <p> inside <li>) — the parent
            # already contributes the text.
            if element.find_parent(BLOCK_TAGS) is not None:
                continue
            text = _clean(element.get_text(" ", strip=True))
            if text:
                current_blocks.append(text)
    flush()

    if not sections:
        # Fallback for pages without block markup: grab all remaining text.
        text = _clean(root.get_text(" ", strip=True))
        if text:
            sections.append(Section(heading=None, text=text))

    return ExtractedPage(title=title, sections=sections)


def extract_links(html: str, base_url: str) -> list[tuple[str, str]]:
    """Extract (absolute_url, anchor_text) pairs from a page."""
    from urllib.parse import urljoin, urldefrag

    soup = BeautifulSoup(html, "html.parser")
    links: list[tuple[str, str]] = []
    seen: set[str] = set()
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        if href.startswith(("mailto:", "javascript:", "tel:", "#")):
            continue
        try:
            absolute = urldefrag(urljoin(base_url, href)).url
        except ValueError:
            continue  # malformed href (e.g. an invalid port) — skip the link
        if not absolute.startswith(("http://", "https://")):
            continue
        if absolute in seen:
            continue
        seen.add(absolute)
        links.append((absolute, a.get_text(" ", strip=True)))
    return links
