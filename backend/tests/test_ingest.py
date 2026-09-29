import pytest

from app.services.ingest import (
    InvalidRecord,
    normalize_url,
    parse_record,
    read_csv,
)


def test_normalize_url_adds_scheme():
    assert normalize_url("example.com/~prof") == "https://example.com/~prof"


def test_normalize_url_lowercases_host_keeps_path_case():
    assert normalize_url("http://EXAMPLE.com/~Prof") == "http://example.com/~Prof"


def test_normalize_url_strips_fragment_keeps_query():
    assert (
        normalize_url("http://x.com/page.php?id=1#top") == "http://x.com/page.php?id=1"
    )


def test_normalize_url_rejects_garbage():
    with pytest.raises(InvalidRecord):
        normalize_url("ftp://example.com/data")
    with pytest.raises(InvalidRecord):
        normalize_url("   ")


def test_parse_record_normalizes_placeholders():
    record = parse_record(
        {
            "name": " Jane Smith ",
            "affiliation": "University X",
            "homepage": "janesmith.org",
            "scholarid": "NOSCHOLARPAGE",
            "orcid": "0000-0000-0000-0000",
        }
    )
    assert record.name == "Jane Smith"
    assert record.homepage == "https://janesmith.org/"
    assert record.scholar_id is None
    assert record.orcid is None


def test_parse_record_missing_required_field():
    with pytest.raises(InvalidRecord):
        parse_record({"name": "X", "affiliation": "", "homepage": "http://x.com"})


def test_read_csv_parses_and_deduplicates(tmp_path):
    csv_file = tmp_path / "professors.csv"
    csv_file.write_text(
        "name,affiliation,homepage,scholarid,orcid\n"
        "Jane Smith,University X,http://x.com/jane,abc123,0000-0002-1825-0097\n"
        "Jane Smith,University X,http://x.com/jane,abc123,0000-0002-1825-0097\n"
        "Bad Row,,http://y.com,,\n"
        "John Doe,University Y,http://y.com/john,,0000-0000-0000-0000\n"
    )
    records, errors = read_csv(csv_file)
    assert [r.name for r in records] == ["Jane Smith", "John Doe"]
    assert len(errors) == 2  # one duplicate, one invalid
    assert records[1].orcid is None


def test_read_csv_collapses_name_aliases_sharing_homepage(tmp_path):
    """CSRankings lists the same person under several DBLP name variants;
    identical (affiliation, homepage) means the same professor."""
    csv_file = tmp_path / "professors.csv"
    csv_file.write_text(
        "name,affiliation,homepage,scholarid,orcid\n"
        "Alex Aiken,Stanford University,https://theory.stanford.edu/~aiken,abc,\n"
        "Alexander Aiken,Stanford University,https://theory.stanford.edu/~aiken,abc,\n"
        "Alex Aiken,Other University,https://other.edu/aiken,,\n"
    )
    records, errors = read_csv(csv_file)
    # the alias row is dropped; a same-named person elsewhere is kept
    assert [(r.name, r.affiliation) for r in records] == [
        ("Alex Aiken", "Stanford University"),
        ("Alex Aiken", "Other University"),
    ]
    assert len(errors) == 1 and "alias" in errors[0]


def test_parse_record_strips_dblp_numeric_suffix():
    record = parse_record(
        {"name": "Wei Wang 0004", "affiliation": "U", "homepage": "http://u.edu/w"}
    )
    assert record.name == "Wei Wang"
    # a 4-digit run elsewhere in a name is untouched
    record2 = parse_record(
        {"name": "John 1234 Smith", "affiliation": "U", "homepage": "http://u.edu/j"}
    )
    assert record2.name == "John 1234 Smith"
