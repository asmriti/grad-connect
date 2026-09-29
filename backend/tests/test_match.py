"""Resume matching: extraction, chunking, and pair aggregation.

No network, no model download — the embedding side is exercised only through
pure aggregation here (DB-backed matching lives in test_db_integration.py).
"""

import io
from types import SimpleNamespace

import pytest

from app.services.resume import (
    ResumeError,
    aggregate_pairs,
    chunk_resume,
    excerpt,
    extract_resume_text,
)


# ---------------------------------------------------------------------------
# Fixture builders (tiny in-memory files; no binary fixtures on disk)
# ---------------------------------------------------------------------------

def make_pdf(text: str) -> bytes:
    """Assemble a minimal one-page PDF with `text` in a content stream."""
    stream = f"BT /F1 12 Tf 72 720 Td ({text}) Tj ET".encode()
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
        b"/Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>",
        b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    out = io.BytesIO()
    out.write(b"%PDF-1.4\n")
    offsets = []
    for i, body in enumerate(objects, start=1):
        offsets.append(out.tell())
        out.write(f"{i} 0 obj\n".encode() + body + b"\nendobj\n")
    xref_at = out.tell()
    out.write(f"xref\n0 {len(objects) + 1}\n".encode())
    out.write(b"0000000000 65535 f \n")
    for offset in offsets:
        out.write(f"{offset:010d} 00000 n \n".encode())
    out.write(
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\n"
        f"startxref\n{xref_at}\n%%EOF\n".encode()
    )
    return out.getvalue()


def make_docx(paragraphs: list[str]) -> bytes:
    import docx

    document = docx.Document()
    for p in paragraphs:
        document.add_paragraph(p)
    out = io.BytesIO()
    document.save(out)
    return out.getvalue()


# ---------------------------------------------------------------------------
# Extraction
# ---------------------------------------------------------------------------

def test_extract_pdf():
    content = make_pdf("Built reinforcement learning agents for robotics.")
    text = extract_resume_text("resume.pdf", content)
    assert "reinforcement learning agents" in text


def test_extract_docx():
    content = make_docx(["Research Experience", "Implemented a compiler optimization pass."])
    text = extract_resume_text("resume.docx", content)
    assert "compiler optimization pass" in text
    assert "Research Experience" in text


def test_extract_txt_and_md():
    body = "Projects: distributed systems and consensus protocols.".encode()
    assert "consensus protocols" in extract_resume_text("cv.txt", body)
    assert "consensus protocols" in extract_resume_text("cv.md", body)


def test_reject_unsupported_extension():
    with pytest.raises(ResumeError, match="Unsupported file type"):
        extract_resume_text("resume.rtf", b"{\\rtf1 hello}")


def test_reject_binary_pretending_to_be_txt():
    with pytest.raises(ResumeError):
        extract_resume_text("cv.txt", b"PK\x03\x04\x00\x00binary")


def test_reject_oversized_file():
    with pytest.raises(ResumeError, match="5 MB"):
        extract_resume_text("cv.txt", b"a" * (5 * 1024 * 1024 + 1))


def test_scanned_pdf_with_no_text_gives_clear_error():
    content = make_pdf("")  # a page that draws no characters
    with pytest.raises(ResumeError, match="[Pp]aste"):
        extract_resume_text("scan.pdf", content)


def test_empty_file_rejected():
    with pytest.raises(ResumeError, match="empty"):
        extract_resume_text("cv.txt", b"")


# ---------------------------------------------------------------------------
# Chunking
# ---------------------------------------------------------------------------

def test_chunk_resume_splits_on_blank_lines():
    text = (
        "Research assistant working on graph neural networks for molecules.\n\n"
        "Built a Raft-based replicated key-value store in Rust for coursework."
    )
    chunks, truncated = chunk_resume(text, 600, 100)
    assert len(chunks) == 2
    assert not truncated
    assert [c.chunk_index for c in chunks] == [0, 1]
    assert "graph neural networks" in chunks[0].text
    assert "key-value store" in chunks[1].text


def test_chunk_resume_caps_at_20_and_reports_truncation():
    paragraph = "One distinct project with plenty of descriptive detail here. "
    text = "\n\n".join(paragraph + str(i) for i in range(30))
    chunks, truncated = chunk_resume(text, 600, 100)
    assert len(chunks) == 20
    assert truncated


def test_chunk_resume_skips_tiny_fragments():
    chunks, truncated = chunk_resume("Too short.\n\nAlso tiny.", 600, 100)
    assert chunks == []
    assert not truncated


def test_excerpt_shortens_on_word_boundary():
    text = "word " * 200
    short = excerpt(text, max_chars=50)
    assert len(short) <= 51
    assert short.endswith("…")
    assert excerpt("short text") == "short text"


# ---------------------------------------------------------------------------
# Pair aggregation
# ---------------------------------------------------------------------------

def _prof(pid):
    return SimpleNamespace(id=pid, name=f"P{pid}")


def _pchunk(text):
    return SimpleNamespace(text=text, url="https://x.edu/", page_title="T", heading=None)


def test_pairs_from_several_resume_chunks_merge_to_best():
    prof = _prof(1)
    pairs = [
        (0, "resume chunk zero", _pchunk("a"), prof, 0.71),
        (1, "resume chunk one", _pchunk("b"), prof, 0.83),
        (2, "resume chunk two", _pchunk("c"), prof, 0.77),
    ]
    results = aggregate_pairs(pairs)
    assert len(results) == 1
    assert results[0].similarity == 0.83  # best pair wins
    assert len(results[0].matches) == 3
    assert results[0].matches[0].resume_excerpt == "resume chunk one"


def test_evidence_prefers_distinct_resume_chunks():
    """One resume chunk with three strong pairs must not fill all slots when
    other resume chunks also matched."""
    prof = _prof(1)
    pairs = [
        (0, "chunk zero", _pchunk("a"), prof, 0.90),
        (0, "chunk zero", _pchunk("b"), prof, 0.89),
        (0, "chunk zero", _pchunk("c"), prof, 0.88),
        (1, "chunk one", _pchunk("d"), prof, 0.87),
        (2, "chunk two", _pchunk("e"), prof, 0.86),
    ]
    results = aggregate_pairs(pairs)
    excerpts = [m.resume_excerpt for m in results[0].matches]
    assert excerpts == ["chunk zero", "chunk one", "chunk two"]


def test_evidence_fills_from_same_chunk_when_no_others():
    prof = _prof(1)
    pairs = [
        (0, "chunk zero", _pchunk("a"), prof, 0.90),
        (0, "chunk zero", _pchunk("b"), prof, 0.85),
    ]
    results = aggregate_pairs(pairs)
    assert len(results[0].matches) == 2


def test_professors_ranked_by_best_pair():
    pa, pb = _prof(1), _prof(2)
    pairs = [
        (0, "r0", _pchunk("a"), pa, 0.70),
        (1, "r1", _pchunk("b"), pb, 0.80),
        (2, "r2", _pchunk("c"), pa, 0.75),
    ]
    results = aggregate_pairs(pairs)
    assert [r.professor.id for r in results] == [2, 1]


def test_no_pairs_no_results():
    assert aggregate_pairs([]) == []
