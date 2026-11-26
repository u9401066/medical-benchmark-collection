from itertools import product

import pytest

from scripts import audit_ese_repeats as ese


def fixture_grid():
    models = ["CHATGPT 4O"] + [f"MODEL {i}" for i in range(2, 9)]
    columns = [f"C{i}" for i in range(72)]
    header = {"A": "QUESTION NO"}
    for column, (day, model, account) in zip(
        columns, product(ese.DAYS, models, ese.ACCOUNTS)
    ):
        marker = (
            "CHAGTGPT 4O"
            if day == 7 and model == "CHATGPT 4O" and account == 3
            else model
        )
        header[column] = f"Day {day}  {marker}-{account}"
    rows = [(1, header)]
    for index, key in enumerate(sorted(ese.IDS), 2):
        rows.append((index, {"A": key, **dict.fromkeys(columns, "D")}))
    # The fixed source has extra notes below the 50-item grid.
    rows.append((70, {"A": "A1", "C0": "note"}))
    return rows


def test_audit_checks_question_counts_by_id_and_ignores_appendix_notes(monkeypatch):
    rows = fixture_grid()
    monkeypatch.setattr(ese, "sheet_rows", lambda _: iter(rows))
    questions = {
        key: ("MCQ" if key.startswith("A") else "Yes/No", 72) for key in ese.IDS
    }
    monkeypatch.setattr(ese, "question_totals", lambda _: questions)
    result = ese.audit(b"fixture", b"fixture")
    assert result["correct"] == result["responses"] == 3600
    assert result["question_formats"] == {"MCQ": 20, "Yes/No": 30}
    assert result["same_account_day_change"]["day_1_to_7"]["both_correct"] == 1200
    questions["A1"] = ("MCQ", 71)
    with pytest.raises(ValueError, match="A1"):
        ese.audit(b"fixture", b"fixture")


def test_correctness_transitions_exclude_neither_failed_side():
    assert ese.transition(
        [(False, False), (True, False), (False, True), (True, True)]
    ) == {
        "paired": 4,
        "both_correct": 1,
        "correct_to_incorrect": 1,
        "incorrect_to_correct": 1,
        "both_incorrect": 1,
    }
