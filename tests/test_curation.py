import json
from datetime import date

import pytest

from medbench.curation import decisions, digest, records


def test_split_and_same_revision_content_must_match_review(tmp_path):
    path = tmp_path / "case.json"
    draft = {"concept_id": "c", "revision": 1, "family_id": "family", "split": "public_development",
             "kind": "open", "evidence": [{"locator": "Methods"}], "permitted_uses": ["train", "development"],
             "variants": [{"id": "a", "lang": "zh-TW", "question": "Q", "answer": "A"}]}
    path.write_text(json.dumps(draft))
    assert records(tmp_path, {}, "train") == [] and records(tmp_path, {}, "queue")[0]["decision"] == "pending"
    event = {"reviewer": "fixture", "date": "2026-11-26", "reason": "fixture review", "evidence_locator": "Methods",
             "decision": "approve", "variant_id": "a", "content_sha256": digest(draft), "revision": 1,
             "approved_uses": ["development", "train"], "checked": ["clinical", "language"]}
    log = tmp_path / "events.jsonl"
    log.write_text(json.dumps(event))
    events = decisions(log)
    assert records(tmp_path, events, "development")[0]["messages"][1]["content"] == "A"
    assert records(tmp_path, events, "train") == []
    draft["variants"][0]["answer"] = "Edited"
    path.write_text(json.dumps(draft))
    assert records(tmp_path, events, "development") == []
    assert records(tmp_path, events, "queue")[0]["decision"] == "stale_review"
    second = {**draft, "split": "train", "variants": [{**draft["variants"][0], "id": "b"}]}
    (tmp_path / "another.json").write_text(json.dumps(second))
    with pytest.raises(ValueError, match="family"):
        records(tmp_path, events, "queue")


@pytest.fixture
def clinical_item(tmp_path):
    # Invented labels exercise release rules without establishing any clinical answer.
    variant = {
        "id": "case-en", "lang": "en-US", "question": "Using the old framework, select one.",
        "options": {"A": "First", "B": "Second"}, "answer": "A", "rationale": "Historical explanation",
        "historical_basis": {"as_of": "2018-01-01", "url": "https://example.org/2018", "locator": "Table 1"},
        "clinical_update": {
            "as_of": "2026-02-01", "review_due": "2027-02-01", "jurisdiction": "US",
            "question": "Under the 2026 framework, which, if any, is supported?",
            "outcome": "no_valid_option", "valid_options": [], "answer": "Neither option applies.",
            "rationale": "The new definition excludes both.", "evidence_ids": ["current"],
        },
    }
    draft = {
        "concept_id": "case", "family_id": "case", "revision": 2, "kind": "mcq", "split": "train",
        "permitted_uses": ["train"], "variants": [variant],
        "source_rights": {"origin": "project_original", "status": "cleared", "attribution": "Fixture authors",
                          "scope": "Original test items for these test exports.", "checked_on": "2026-01-01",
                          "allowed_uses": ["train", "development", "evaluation"]},
        "evidence": [{"url": "https://example.org/2018", "locator": "Table 1"},
                     {"id": "current", "url": "https://example.org/2026", "locator": "Table 3",
                      "version": "v2", "published_on": "2026-01-01"}],
    }
    event = {"reviewer": "fixture", "date": "2026-02-02", "reason": "fixture review", "evidence_locator": "Table 3",
             "decision": "approve", "variant_id": variant["id"], "revision": draft["revision"],
             "approved_uses": ["train"], "checked": ["clinical", "language", "temporal"]}

    def save(approve=True):
        (tmp_path / "case.json").write_text(json.dumps(draft), encoding="utf-8")
        return {variant["id"]: {**event, "content_sha256": digest(draft)}} if approve else {}

    return draft, variant, event, save


def test_current_training_uses_reviewed_prompt_corrected_key_and_only_current_evidence(tmp_path, clinical_item):
    draft, variant, event, save = clinical_item
    as_of = date(2026, 3, 1)
    for outcome, choices, answer, reason in [
        ("no_valid_option", [], "Neither option applies.", "Both listed options were retired."),
        ("single_valid_option", ["B"], "B", "The revised rule specifies the second option."),
        ("insufficient_information", [], "Need the missing detail.", "The new rule requires a field absent in the question."),
    ]:
        variant["clinical_update"].update(outcome=outcome, valid_options=choices, answer=answer, rationale=reason)
        events = save()
        rows = records(tmp_path, events, "clinical-train", as_of)
        assert records(tmp_path, events, "train", as_of) == rows
        row, = rows
        assert row["answer_basis"] == "clinical_as_of" and row["valid_options"] == choices
        assert row["messages"][0]["content"].startswith("Under the 2026")
        assert row["messages"][1]["content"] == answer + "\n" + reason
        assert [e["id"] for e in row["evidence"]] == ["current"]
        assert row["content_sha256"] == digest(draft) and variant["answer"] == "A"

    events = save()
    variant["clinical_update"]["rationale"] = "Corrected explanation"
    save()
    assert records(tmp_path, events, "queue", as_of)[0]["clinical_status"] == "stale_review"
    assert records(tmp_path, events, "train", as_of) == []
    variant.pop("clinical_update")
    assert records(tmp_path, save(), "train", as_of) == []
    variant.pop("historical_basis")
    events = save()
    assert records(tmp_path, events, "clinical-train", as_of) == []
    row, = records(tmp_path, events, "train", as_of)
    assert row["answer_basis"] == "source_version_unassessed" and row["messages"][1]["content"].startswith("A\n")


def test_temporal_gate_rejects_due_unreviewed_conflicting_or_out_of_scope_training(tmp_path, clinical_item):
    draft, variant, event, save = clinical_item
    as_of = date(2026, 3, 1)
    events = save()
    assert records(tmp_path, {}, "clinical-train", as_of) == []
    assert records(tmp_path, events, "clinical-train", date(2026, 1, 31)) == []
    assert records(tmp_path, events, "clinical-train", date(2026, 2, 1)) == []
    assert records(tmp_path, events, "queue", date(2027, 2, 1))[0]["clinical_status"] == "review_due"
    assert records(tmp_path, events, "train", date(2027, 2, 1)) == []
    event["checked"].remove("temporal")
    assert records(tmp_path, save(), "clinical-train", as_of) == []
    event["checked"].append("temporal")
    variant["clinical_update"]["outcome"] = "conflicting_evidence"
    events = save()
    assert records(tmp_path, events, "queue", as_of)[0]["clinical_status"] == "needs_adjudication"
    assert records(tmp_path, events, "train", as_of) == []
    variant["clinical_update"]["outcome"] = "no_valid_option"
    draft["split"] = "heldout_evaluation"
    assert records(tmp_path, save(), "clinical-train", as_of) == []
    draft["split"], draft["permitted_uses"] = "train", ["evaluation"]
    assert records(tmp_path, save(), "clinical-train", as_of) == []


@pytest.mark.parametrize(("rule", "answer"), [("any_one", "B"), ("all_required", "B, A")])
def test_multiple_answer_rule_preserves_accepted_set_and_reviewed_training_target(tmp_path, clinical_item, rule, answer):
    draft, variant, event, save = clinical_item
    as_of = date(2026, 3, 1)
    update = variant["clinical_update"]
    update.update(outcome="multiple_valid_options", valid_options=["A", "B"], selection_rule=rule,
                  answer=answer, rationale="Both labels qualify.")
    row, = records(tmp_path, save(), "clinical-train", as_of)
    assert row["selection_rule"] == rule and row["valid_options"] == ["A", "B"]
    assert row["messages"][1]["content"].splitlines()[0] == answer
    del update["selection_rule"]
    with pytest.raises(ValueError, match="selection_rule"):
        records(tmp_path, save(), "clinical-train", as_of)
    update["selection_rule"] = rule
    update["answer"] = "A, B" if rule == "any_one" else "A"
    with pytest.raises(ValueError, match=rule):
        records(tmp_path, save(), "clinical-train", as_of)


def test_temporal_references_and_answer_labels_must_validate(tmp_path, clinical_item):
    draft, variant, event, save = clinical_item
    update = variant["clinical_update"]
    update["valid_options"] = ["A"]
    with pytest.raises(ValueError, match="incompatible"):
        records(tmp_path, save(), "queue")
    update.update(outcome="single_valid_option", valid_options=["B"], answer="A")
    with pytest.raises(ValueError, match="must match"):
        records(tmp_path, save(), "queue")
    update.update(answer="B", evidence_ids=["nonexistent"])
    with pytest.raises(ValueError, match="evidence_ids"):
        records(tmp_path, save(), "queue")
    update["evidence_ids"] = ["current"]
    draft["evidence"][1]["published_on"] = "2026-02-15"
    with pytest.raises(ValueError, match="published after"):
        records(tmp_path, save(), "queue")


def test_comparable_historical_option_is_only_in_approved_scoring_export(tmp_path, clinical_item):
    draft, variant, event, save = clinical_item
    historical = variant["historical_basis"]
    historical["comparison"] = "same_decision_single_option"
    as_of = date(2026, 3, 1)
    assert "historical_option" not in records(tmp_path, save(), "clinical-train", as_of)[0]
    draft.update(split="public_development", permitted_uses=["development"])
    event["approved_uses"] = ["development"]
    assert not records(tmp_path, {}, "clinical-development", as_of)
    row, = records(tmp_path, save(), "clinical-development", as_of)
    expected = {k: historical[k] for k in ("as_of", "url", "locator")}
    assert row["historical_option"] == {**expected, "label": "A"}
    assert "historical_option" not in records(tmp_path, save(), "development", as_of)[0]
    del historical["comparison"]
    assert "historical_option" not in records(tmp_path, save(), "clinical-development", as_of)[0]
    historical["comparison"] = "administrative_full_credit"
    with pytest.raises(ValueError, match="unknown historical comparison"):
        records(tmp_path, save(), "queue", as_of)
    historical["comparison"] = "same_decision_single_option"
    historical["as_of"] = variant["clinical_update"]["as_of"]
    with pytest.raises(ValueError, match="strictly earlier"):
        records(tmp_path, save(), "queue", as_of)


@pytest.mark.parametrize(("mode", "split"), [("development", "public_development"), ("evaluation", "heldout_evaluation")])
def test_clinical_evaluation_uses_current_prompt_and_matching_use(tmp_path, clinical_item, mode, split):
    draft, variant, event, save = clinical_item
    draft["split"] = split
    draft["permitted_uses"] = [mode]
    as_of = date(2026, 3, 1)
    assert not records(tmp_path, save(), "clinical-" + mode, as_of)
    event["approved_uses"] = [mode]
    events = save()
    row, = records(tmp_path, events, "clinical-" + mode, as_of)
    assert row["answer_basis"] == "clinical_as_of" and row["outcome"] == "no_valid_option"
    assert row["messages"][0]["content"].startswith("Under the 2026 framework")
    assert not records(tmp_path, events, "clinical-train", as_of)
    assert not records(tmp_path, events, "clinical-" + mode, date(2027, 2, 1))
    old, = records(tmp_path, events, mode, as_of)
    assert old["answer_basis"] == "source_version" and "outcome" not in old
    assert old["messages"][0]["content"].startswith("Using the old framework")
    draft["split"] = "train"
    assert not records(tmp_path, save(), "clinical-" + mode, as_of)


def test_only_matching_same_day_watch_observation_allows_export(tmp_path, clinical_item):
    draft, variant, event, save = clinical_item
    source = draft["evidence"][1]
    expected = "a" * 64
    source.update(watch_xpath="//table[3]", passage_sha256=expected)
    events = save()
    as_of = date(2026, 3, 1)
    observation = {"url": source["url"], "watch_xpath": "//table[3]", "expected_sha256": expected,
                   "observed_sha256": expected, "status": "unchanged"}
    report = {"checked_on": as_of.isoformat(), "sources": [observation]}
    assert len(records(tmp_path, events, "clinical-train", as_of, report)) == 1
    assert not records(tmp_path, events, "clinical-train", as_of)
    assert not records(tmp_path, events, "train", as_of, {**report, "checked_on": "2026-02-28"})
    for changed, status in [
        ({"status": "changed", "observed_sha256": "b" * 64}, "watch_changed"),
        ({"status": "unavailable"}, "watch_unavailable"),
        ({"observed_sha256": "c" * 64}, "watch_unavailable"),
        ({"watch_xpath": "//section"}, "watch_required"),
        ({"expected_sha256": "d" * 64}, "watch_required"),
        ({"url": "https://example.org/other"}, "watch_required"),
    ]:
        mismatched = {**report, "sources": [{**observation, **changed}]}
        assert records(tmp_path, events, "queue", as_of, mismatched)[0]["clinical_status"] == status
        assert not records(tmp_path, events, "train", as_of, mismatched)


def test_claims_link_only_to_cited_current_evidence_and_preserve_target(tmp_path, clinical_item):
    draft, variant, event, save = clinical_item
    as_of = date(2026, 3, 1)
    update = variant["clinical_update"]
    claim = {"text": "Both supplied options fall outside the current definition.", "evidence_ids": ["current"]}
    update["claims"] = [claim]
    row, = records(tmp_path, save(), "clinical-train", as_of)
    assert row["claims"] == [claim]
    assert row["messages"][1]["content"] == update["answer"] + "\n" + update["rationale"]
    draft["evidence"][0]["id"] = "uncited"
    for refs in ([], ["current", "current"], ["uncited"]):
        claim["evidence_ids"] = refs
        with pytest.raises(ValueError, match="claim evidence_ids"):
            records(tmp_path, save(), "queue")
    claim.update(text=" ", evidence_ids=["current"])
    with pytest.raises(ValueError, match="nonempty text"):
        records(tmp_path, save(), "clinical-train", as_of)


def test_plain_train_excludes_unassessed_translations_in_temporal_family(tmp_path, clinical_item):
    draft, variant, event, save = clinical_item
    # The legacy variant comes first in file order and has its own matching approval.
    old_variant = {"id": "case-legacy", "lang": "zh-TW", "question": "Old question", "answer": "A"}
    legacy = {**draft, "variants": [old_variant]}
    (tmp_path / "a-legacy.json").write_text(json.dumps(legacy), encoding="utf-8")
    events = save()
    events[old_variant["id"]] = {**event, "variant_id": old_variant["id"], "content_sha256": digest(legacy)}
    as_of = date(2026, 3, 1)
    assert [row["id"] for row in records(tmp_path, events, "train", as_of)] == [variant["id"]]


@pytest.mark.parametrize("permission", ["approved_uses", "permitted_uses"])
def test_training_permissions_require_explicit_membership_not_a_substring(tmp_path, clinical_item, permission):
    draft, variant, event, save = clinical_item
    (event if permission == "approved_uses" else draft)[permission] = "not_for_train"
    assert not records(tmp_path, save(), "clinical-train", date(2026, 3, 1))


def test_as_of_selects_decision_in_effect_on_requested_day(tmp_path, clinical_item):
    draft, variant, event, save = clinical_item
    reviewed = save()[variant["id"]]
    withdrawal = {**reviewed, "decision": "withdraw", "date": "2026-06-01"}
    log = tmp_path / "log.jsonl"
    log.write_text("\n".join(map(json.dumps, [reviewed, withdrawal])), encoding="utf-8")
    early, late = date(2026, 5, 31), date(2026, 6, 1)
    assert len(records(tmp_path, decisions(log, early), "clinical-train", early)) == 1
    assert not records(tmp_path, decisions(log, late), "clinical-train", late)
