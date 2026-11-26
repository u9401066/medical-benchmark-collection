import gzip
import hashlib
import json

import pytest

from scripts.prepare_medaesqa import audit, build_index, encode, unique_object


def sentence(sid, text, citations=None):
    return {
        "answer_sentence_id": sid,
        "answer_sentence": text,
        "answer_sentence_relevance": None,
        "citation_assessment": citations,
    }


def assessment(pmid="001234", relation="supporting", snippet="source excerpt"):
    return {"cited_pmid": pmid, "evidence_relation": relation, "evidence_support": snippet}


def question(sentences):
    return {
        "question_id": "Q1",
        "machine_generated_answers": {
            "M1": {
                "answer": "甲🙂🙂🙂𠀋測",
                "is_answer_accurate": "yes",
                "answer_sentences": sentences,
            },
        },
    }


def test_unicode_offsets_overlapping_matches_and_unmatched_sentences():
    source = question([sentence("01", "𠀋測"), sentence("02", "🙂🙂"), sentence("03", "x")])
    rows, _ = build_index([source])
    assert [(r["match_count"], r["start"], r["end"]) for r in rows] == [
        (1, 4, 6), (2, None, None), (0, None, None),
    ]
    assert rows[0]["sentence_sha256"] == hashlib.sha256("𠀋測".encode()).hexdigest()
    assert rows[0]["answer_sentence_id"] == "01"


def test_repeat_relations_are_retained_and_citation_text_is_not_republished():
    citations = [assessment(), assessment(relation="neutral", snippet=None), assessment()]
    rows, _ = build_index([question([sentence("1", "甲", citations), sentence("2", "測")])])
    first = rows[0]["citation_assessment"]
    assert [c["cited_pmid"] for c in first] == ["001234"] * 3
    assert [c["has_evidence_excerpt"] for c in first] == [True, False, True]
    assert rows[1]["citation_assessment"] is None
    stats = audit(rows)
    assert (stats["citations"], stats["distinct_sentence_pmid"], stats["nonempty_evidence_excerpts"]) == (3, 1, 2)
    assert stats["distinct_sentence_pmid_with_mixed_labels"] == 1
    compressed, digest = encode(rows)
    assert encode(rows) == (compressed, digest)
    raw = gzip.decompress(compressed)
    assert digest == hashlib.sha256(raw).hexdigest()
    assert b"source excerpt" not in raw
    assert "甲" not in raw.decode()


@pytest.mark.parametrize("bad", [[assessment(pmid=123)], [assessment(snippet=17)], [assessment(snippet="")], "citation"])
def test_malformed_citation_fields_are_rejected(bad):
    with pytest.raises(ValueError):
        build_index([question([sentence("1", "甲", bad)])])


def test_empty_or_repeated_source_ids_are_rejected_in_their_own_scopes():
    with pytest.raises(ValueError, match="Repeated key"):
        json.loads('{"M1": {}, "M1": {}}', object_pairs_hook=unique_object)
    with pytest.raises(ValueError, match="Repeated answer_sentence_id"):
        build_index([question([sentence("1", "甲"), sentence("1", "測")])])
    with pytest.raises(ValueError, match="answer_sentence_id must"):
        build_index([question([sentence("", "甲")])])
    q = question([])
    with pytest.raises(ValueError, match="Repeated question_id"):
        build_index([q, q])
