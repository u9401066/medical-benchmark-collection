"""Regressions for paired denominators in the bilingual exam workbook audit."""

import json
from pathlib import Path

import pytest

from scripts.audit_bilingual_exam import INVALID_STATUS, audit, summarize


def item(question):
    return {"question_id": question, "question_format": "single-select", "answer_key_version": "v1"}


def response(question, model, lang, valid=True):
    return {
        "question_id": question,
        "response_id": f"{question}_{model}_{lang}",
        "model": model,
        "language": lang,
        "response_status": "valid" if valid else INVALID_STATUS,
        "is_evaluable": "1" if valid else "0",
        "is_exact_correct_parseable": "0" if valid else "",
        "response_raw_cell": "private response placeholder",
    }


def test_pairs_count_both_one_and_zero_evaluable_sides_without_disclosing_responses():
    items = [item("q1"), item("q2"), item("q3")]
    responses = [
        response("q1", "A", "en"), response("q1", "A", "zh"),
        response("q2", "A", "en", False), response("q2", "A", "zh"),
        response("q3", "A", "en", False), response("q3", "A", "zh", False),
    ]
    report = summarize(items, reversed(responses))
    assert report["pairs_by_evaluable_languages"] == {"0": 1, "1": 1, "2": 1}
    assert [(s["responses"], s["evaluable"]) for s in report["strata"]] == [(3, 1), (3, 2)]
    assert "private response placeholder" not in json.dumps(report)
    assert "q1" not in json.dumps(report)


def test_equal_language_totals_can_hide_a_duplicate_and_a_missing_partner():
    rows = [response("q1", "A", "en"), response("q1", "A", "zh"), response("q2", "A", "en")]
    rows.append({**response("q1", "A", "zh"), "response_id": "distinct-id"})
    with pytest.raises(ValueError, match="Repeated response for an item"):
        summarize([item("q1"), item("q2")], rows)


def test_unpaired_rows_and_wholly_missing_item_model_combinations_are_rejected():
    rows = [response("q1", "A", "en"), response("q1", "A", "zh")]
    with pytest.raises(ValueError, match="Incomplete English/Chinese"):
        summarize([item("q1")], rows[:1])
    rows.extend([response("q2", "B", "en"), response("q2", "B", "zh")])
    with pytest.raises(ValueError, match="Incomplete item-by-model"):
        summarize([item("q1"), item("q2")], rows)


def test_excluded_row_with_a_recorded_score_is_rejected():
    row = {**response("q1", "A", "en", False), "is_exact_correct_parseable": "0"}
    with pytest.raises(ValueError, match="inconsistent excluded response"):
        summarize([item("q1")], [row])


def test_hash_is_checked_before_reading_workbook():
    with pytest.raises(ValueError, match="SHA-256"):
        audit(Path(__file__))
