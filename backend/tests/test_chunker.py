from app.services.chunker import CHARS_PER_TOKEN, chunk_sections
from app.services.extractor import Section


def test_short_section_kept_whole_with_heading_prefix():
    sections = [Section(heading="Research Interests", text="Human computer interaction and accessibility research.")]
    chunks = chunk_sections(sections, chunk_size_tokens=600, overlap_tokens=100)
    assert len(chunks) == 1
    assert chunks[0].heading == "Research Interests"
    assert chunks[0].text.startswith("Research Interests\n\n")
    assert "accessibility" in chunks[0].text


def test_long_section_split_with_overlap():
    sentence = "This sentence describes one research project in reasonable detail. "
    sections = [Section(heading="Projects", text=sentence * 120)]  # ~8000 chars
    chunks = chunk_sections(sections, chunk_size_tokens=500, overlap_tokens=100)
    max_chars = 500 * CHARS_PER_TOKEN
    assert len(chunks) > 1
    assert all(len(c.text) <= max_chars for c in chunks)
    # overlap: consecutive chunks share text
    first_body = chunks[0].text.split("\n\n", 1)[1]
    second_body = chunks[1].text.split("\n\n", 1)[1]
    assert first_body[-40:].strip() in second_body


def test_sentences_not_split_mid_sentence_when_possible():
    sentence = "Alpha beta gamma delta epsilon zeta eta theta. "
    sections = [Section(heading=None, text=sentence * 60)]
    chunks = chunk_sections(sections, chunk_size_tokens=100, overlap_tokens=20)
    for chunk in chunks:
        assert chunk.text.rstrip().endswith((".", "!", "?"))


def test_chunk_indexes_are_sequential_across_sections():
    sections = [
        Section(heading="A", text="First section content with clearly enough characters to keep around."),
        Section(heading="B", text="Second section content with clearly enough characters to keep around."),
    ]
    chunks = chunk_sections(sections, chunk_size_tokens=600, overlap_tokens=100)
    assert [c.chunk_index for c in chunks] == [0, 1]


def test_tiny_fragments_skipped():
    sections = [Section(heading=None, text="Too short.")]
    chunks = chunk_sections(sections, chunk_size_tokens=600, overlap_tokens=100)
    assert chunks == []
