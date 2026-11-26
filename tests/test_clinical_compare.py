import pytest

from medbench.clinical_compare import compare, summarize, Pair


def record(
    key="a",
    family="f1",
    lang="zh-TW",
    state="pass",
    outcome="single_valid_option",
    target=True,
    historical="obsolete",
    reuse=False,
    response_type="select",
    fabricated=None,
):
    return dict(
        id=key,
        family_id=family,
        lang=lang,
        content_sha256="e" * 64,
        outcome=outcome,
        target_match=target,
        clinical_result=state,
        historical_relation=historical,
        selected_obsolete_option=reuse,
        response_type=response_type,
        fabricated_citation=fabricated,
    )


def report(*items):
    return dict(
        gold_sha256="f" * 64,
        assigned=len(items),
        split="heldout_evaluation",
        export_as_of="2026-11-26",
        score_as_of="2026-11-26",
        items=list(items),
    )


def test_no_resolved_clinical_difference_is_reported_if_one_pair_pending():
    left = report(record(), record(key="b", lang="en-US", state="pending", reuse=True))
    right = report(record(key="b", lang="en-US", state="fail", reuse=False), record())
    summary = compare(left, right)
    clinical = summary["clinical_pass"]
    assert clinical["assigned_pairs"] == 2
    assert clinical["pending_pairs"] == 1
    assert clinical["case_families"] == 1
    assert clinical["bounds_over_unresolved_reviews"] == [-0.5, 0]
    assert clinical["right_minus_left"] is None
    assert clinical["family_bootstrap_95"] is None
    assert summary["obsolete_choice_reuse"]["right_minus_left"] == -0.5
    assert summary["obsolete_choice_reuse"]["left_true_right_false"] == 1


def test_review_and_response_type_use_separate_denominators():
    left = report(
        record(response_type="abstain", fabricated=True),
        record(
            key="b",
            family="f2",
            outcome="no_valid_option",
            target=False,
            fabricated=False,
        ),
        record(key="c", family="f3", outcome="insufficient_information", target=True),
    )
    right = report(
        record(response_type="select", fabricated=False),
        record(
            key="b",
            family="f2",
            outcome="no_valid_option",
            target=True,
            response_type="no_valid_option",
            fabricated=False,
        ),
        record(
            key="c",
            family="f3",
            outcome="insufficient_information",
            target=False,
            response_type="missing",
        ),
    )
    result = compare(left, right)
    assert result["inappropriate_abstention"]["assigned_pairs"] == 1
    assert result["inappropriate_abstention"]["right_minus_left"] == -1
    assert result["no_valid_option_recognition"]["right_minus_left"] == 1
    assert result["insufficient_information_recognition"]["right_minus_left"] == -1
    audit = result["fabricated_citation"]
    assert audit["assigned_pairs"] == 3 and audit["pending_pairs"] == 1
    assert audit["bounds_over_unresolved_reviews"] == [-2 / 3, 0]
    assert audit["right_minus_left"] is None


def test_cluster_bootstrap_draws_whole_families():
    # Each family has two translations. In family 1 they cancel, so sampling whole families
    # can only produce differences 0, 1/2, 1.
    pairs = [
        Pair("f1", False, True),
        Pair("f1", True, False),
        Pair("f2", False, True),
        Pair("f2", False, True),
    ]
    result = summarize(pairs, 201, 1000)
    assert result["case_families"] == 2 and result["left_false_right_true"] == 3
    assert result["right_minus_left"] == 0.5
    assert result["family_bootstrap_95"] == [0, 1]
    assert result == summarize(list(reversed(pairs)), 201, 1000)
    assert summarize(pairs[:2], 201, 1000)["family_bootstrap_95"] is None


@pytest.mark.parametrize(
    "error", ["sha", "split", "missing", "version", "duplicate", "family", "value"]
)
def test_unmatched_or_invalid_score_reports_are_rejected(error):
    left, right = report(record()), report(record())
    if error == "sha":
        right["gold_sha256"] = "a" * 64
    if error == "split":
        right["split"] = "public_development"
    if error == "missing":
        right["items"] = []
    if error == "version":
        right["items"][0]["content_sha256"] = "b" * 64
    if error == "duplicate":
        right["items"].append(right["items"][0])
    if error == "family":
        right["items"][0]["family_id"] = "f2"
    if error == "value":
        right["items"][0]["target_match"] = "false"
    with pytest.raises(ValueError):
        compare(left, right)
