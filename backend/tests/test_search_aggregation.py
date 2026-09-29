from types import SimpleNamespace

from app.services.search import aggregate_chunks


def _chunk(text, url="https://x.edu/"):
    return SimpleNamespace(text=text, url=url, page_title="T", heading=None)


def _prof(pid, name="P"):
    return SimpleNamespace(id=pid, name=f"{name}{pid}")


def test_aggregates_multiple_chunks_per_professor():
    prof_a, prof_b = _prof(1), _prof(2)
    rows = [
        (_chunk("a1"), prof_a, 0.89),
        (_chunk("b1"), prof_b, 0.86),
        (_chunk("a2"), prof_a, 0.84),
        (_chunk("a3"), prof_a, 0.77),
    ]
    results = aggregate_chunks(rows)
    assert [r.professor.id for r in results] == [1, 2]
    assert results[0].similarity == 0.89  # best chunk wins
    assert [e.text for e in results[0].evidence] == ["a1", "a2", "a3"]
    assert len(results[1].evidence) == 1


def test_returns_every_matching_professor():
    rows = [(_chunk(f"c{i}"), _prof(1), 0.9 - i * 0.01) for i in range(5)]
    rows += [(_chunk("d"), _prof(2), 0.5), (_chunk("e"), _prof(3), 0.4)]
    results = aggregate_chunks(rows)
    assert [r.professor.id for r in results] == [1, 2, 3]


def test_evidence_capped_per_professor():
    rows = [(_chunk(f"c{i}"), _prof(1), 0.9) for i in range(10)]
    results = aggregate_chunks(rows, evidence_per_professor=3)
    assert len(results[0].evidence) == 3


def test_empty_rows():
    assert aggregate_chunks([]) == []
