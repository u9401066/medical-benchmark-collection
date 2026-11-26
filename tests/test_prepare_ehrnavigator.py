import csv
import hashlib
import io
from pathlib import Path

import pytest

from scripts.prepare_ehrnavigator import build_index, prepare


def test_exact_utf8_spans_and_text_identity_with_mixed_line_endings():
    source = "3. 測量？\r\n12. 測量？\n19. 測量？ ".encode()
    output, count, distinct = build_index(source)
    rows = list(csv.DictReader(io.StringIO(output.decode()), delimiter="\t"))
    assert (count, distinct) == (3, 2)
    assert [r["source_line"] for r in rows] == ["1", "2", "3"]
    assert [r["question_number"] for r in rows] == ["3", "12", "19"]
    assert [r["duplicate_group"] for r in rows] == ["3", "3", ""]
    for r, text in zip(rows, ["測量？", "測量？", "測量？ "]):
        excerpt = source[int(r["question_start_byte"]):int(r["question_end_byte"])]
        assert excerpt == text.encode()
        assert hashlib.sha256(excerpt).hexdigest() == r["question_sha256"]
    assert "測量？".encode() not in output
    assert output == build_index(source)[0]


@pytest.mark.parametrize("source", [b"1. first?\n1. different?\n", b"1. first?\nunlabeled?\n"])
def test_rejects_ambiguous_question_numbering(source):
    with pytest.raises(ValueError):
        build_index(source)


def test_hash_guard_rejects_other_files():
    with pytest.raises(ValueError, match="SHA-256"):
        prepare(Path(__file__), Path("unused-index.tsv"), check=True)
