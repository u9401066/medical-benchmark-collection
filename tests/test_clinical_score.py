from datetime import date, timedelta
from copy import deepcopy
import hashlib
import json

import pytest

from medbench.clinical_score import main, score
from medbench.curation import digest, records
from medbench.evidence_audit import worksheet


def gold(key, outcome="single_valid_option", valid=("A",), rule=None):
    row = {
        "id": key, "family_id": "family-" + key, "lang": "zh-TW", "jurisdiction": "TW",
        "decision": "approve", "clinical_status": "current", "answer_basis": "clinical_as_of",
        "split": "heldout_evaluation", "source_watch_status": "not_configured", "reviewer": "test clinician",
        "rights_status": "cleared", "source_rights": {"origin": "project_original", "status": "cleared",
            "attribution": "test authors", "scope": "Scoring test fixture.", "checked_on": "2026-10-01",
            "allowed_uses": ["evaluation"]},
        "clinical_as_of": "2026-10-01", "decision_date": "2026-10-02", "export_as_of": "2026-11-01",
        "review_due": "2027-01-01", "content_sha256": "a" * 64, "outcome": outcome,
        "offered_option_labels": [] if outcome == "free_text" else ["A", "B", "C", "D"],
        "valid_options": list(valid), "evidence": [{"id": "s", "url": "https://example.org",
                                                   "locator": "section 1", "version": "1"}],
    }
    if rule:
        row["selection_rule"] = rule
    return row


def prediction(row, kind, *labels):
    result = {"id": row["id"], "content_sha256": row["content_sha256"], "response_type": kind}
    if kind != "timeout":
        result["text"] = "test output"
    if labels:
        result["selected_options"] = list(labels)
    return result


def test_all_assigned_ids_count_and_different_reasons_for_abstaining():
    batch = [gold("single"), gold("missing"), gold("timeout"), gold("generic"), gold("unparsed"),
             gold("none", "no_valid_option", ()), gold("wrong-reason", "insufficient_information", ()),
             gold("open", "free_text", ())]
    predictions = [prediction(batch[0], "select", "A"), prediction(batch[2], "timeout"),
                   prediction(batch[3], "abstain"), prediction(batch[4], "parse_error"),
                   prediction(batch[5], "no_valid_option"), prediction(batch[6], "no_valid_option"),
                   prediction(batch[7], "free_text")]
    result = score(batch, predictions)
    metrics = result["metrics"]
    assert result["assigned"] == 8 and result["case_families"] == 8
    assert result["response_counts"]["missing"] == result["response_counts"]["timeout"] == 1
    assert metrics["inappropriate_abstention"] == {"numerator": 1, "denominator": 5, "rate": .2}
    assert metrics["structured_target_match"]["numerator"] == 2
    assert metrics["structured_target_match"]["denominator"] == 7
    assert metrics["no_valid_option_recognition"]["rate"] == 1
    assert metrics["insufficient_information_recognition"]["rate"] == 0
    assert metrics["confirmed_clinical_pass_share"]["numerator"] == 0
    assert metrics["clinical_pass_rate"] is None
    assert result["pending_clinical_review"] == ["single", "none", "open"]
    assert result["items"][-1]["target_match"] is None


@pytest.mark.parametrize(("rule", "selection", "correct"), [
    ("any_one", ["C"], True), ("any_one", ["A", "C"], False), ("any_one", ["D"], False),
    ("all_required", ["C", "A"], True), ("all_required", ["A"], False),
    ("all_required", ["A", "C", "D"], False),
])
def test_accepts_only_the_reviewed_multiple_choice_rule(rule, selection, correct):
    row = gold("q", "multiple_valid_options", ["A", "C"], rule)
    result = score([row], [prediction(row, "select", *selection)])
    assert result["items"][0]["target_match"] is correct
    assert result["metrics"]["selected_answer_error"]["rate"] == int(not correct)


def test_reviews_bind_to_exact_output_and_keep_inconclusive_pending():
    row = gold("q", "insufficient_information", ())
    answer = prediction(row, "insufficient_information")
    first = score([row], [answer])["items"][0]
    review = {"id": row["id"], "prediction_sha256": first["prediction_sha256"], "reviewer": "test clinician",
              "date": "2026-11-15", "reason": "Identifies exactly which input is missing.", "verdict": "pass"}
    result = score([row], [answer], [review])
    assert result["metrics"]["clinical_pass_rate"] == {"numerator": 1, "denominator": 1, "rate": 1}
    assert score([row], [answer], [{**review, "verdict": "undetermined"}])["pending_clinical_review"] == ["q"]
    assert score([row], [answer], [{**review, "verdict": "fail"}])["metrics"]["clinical_pass_rate"]["rate"] == 0
    with pytest.raises(ValueError, match="wrong prediction"):
        score([row], [{**answer, "text": "New output"}], [review])
    with pytest.raises(ValueError, match="invalid review"):
        score([row], [], [review])
    cutoff = date(2026, 11, 15)
    for invalid_date in ("2026-10-31", "2026-11-16"):
        with pytest.raises(ValueError, match="review date"):
            score([row], [answer], [{**review, "date": invalid_date}], score_as_of=cutoff)
    for boundary in (row["export_as_of"], cutoff.isoformat()):
        assert score([row], [answer], [{**review, "date": boundary}], score_as_of=cutoff)["items"][0]["clinical_result"] == "pass"
    expired = {**row, "review_due": "2026-11-03"}
    assert score([expired], [answer], [review], score_as_of=cutoff)["items"][0]["clinical_result"] == "pass"
    with pytest.raises(ValueError, match="exported after"):
        score([row], [], score_as_of=date(2026, 10, 31))
    with pytest.raises(ValueError, match="future"):
        score([], [], score_as_of=date.today() + timedelta(days=1))


def test_rejects_duplicate_unknown_mixed_unreviewed_or_stale_input():
    row = gold("q")
    answer = prediction(row, "select", "A")
    for batch, predictions in (([row, row], []), ([row], [answer, answer]),
                               ([row], [{**answer, "id": "unknown"}]), ([row], [{**answer, "content_sha256": "old"}]),
                               ([row], [{**answer, "selected_options": "A"}])):
        with pytest.raises(ValueError):
            score(batch, predictions)
    for patch in ({"clinical_status": "pending"}, {"decision": "revise"}, {"answer_basis": "source_version"},
                  {"split": "train"}, {"source_watch_status": "watch_changed"}, {"review_due": row["export_as_of"]},
                  {"outcome": "conflicting_evidence", "valid_options": []}, {"evidence": []},
                  {"evidence": [{"id": "missing-locator"}]}, {"source_watch_status": "unchanged"},
                  {"rights_status": "pending"}, {"offered_option_labels": ["B"]}):
        with pytest.raises(ValueError):
            score([{**row, **patch}], [])
    with pytest.raises(ValueError, match="one export"):
        score([row, {**row, "id": "q2", "split": "public_development",
                     "source_rights": {**row["source_rights"], "allowed_uses": ["development"]}}], [])
    with pytest.raises(ValueError, match="duplicate id"):
        score([row], [], [{"id": "q"}, {"id": "q"}])
    with pytest.raises(ValueError, match="outside the assignment"):
        score([], [], [{"id": "unknown"}])
    empty = score([], [])
    assert empty["metrics"]["clinical_pass_rate"]["rate"] is None


def test_unoffered_invalid_and_open_question_selections_stay_in_the_assignment():
    rows = [gold("good"), gold("bad-option"), gold("open", "free_text", ()),
            gold("duplicate", "multiple_valid_options", ["A", "B"], "all_required"), gold("blank"), gold("wrong")]
    preds = [prediction(rows[0], "select", "A"), prediction(rows[1], "select", "ZZ-never-offered"),
             prediction(rows[2], "select", "Z"), prediction(rows[3], "select", "A", "B", "B"),
             {**prediction(rows[4], "select"), "selected_options": []}, prediction(rows[5], "select", "C")]
    result = score(rows, preds)
    assert result["selection_counts"] == {"offered": 2, "invalid": 4, "unverified": 0}
    assert result["metrics"]["selection_coverage"] == {"numerator": 2, "denominator": 6, "rate": 2 / 6}
    assert result["metrics"]["selected_answer_error"] == {"numerator": 1, "denominator": 2, "rate": .5}
    assert all(r["clinical_result"] == "fail" for r in result["items"] if r["selection_status"] == "invalid")


def test_reusing_a_sourced_obsolete_option_counts_the_full_assigned_subgroup():
    rows = [gold("changed"), gold("none", "no_valid_option", ()), gold("missing"), gold("several"),
            gold("stable", valid=["B"]), gold("any", "multiple_valid_options", ["A", "B"], "any_one"),
            gold("part", "multiple_valid_options", ["A", "B"], "all_required"),
            gold("insufficient", "insufficient_information", ()), gold("legacy")]
    ref = {"label": "B", "as_of": "2020-01-01", "url": "https://example.org/2020", "locator": "row 2"}
    rows[1]["family_id"] = rows[0]["family_id"]
    for row in rows[:-1]:
        row["historical_option"] = ref
    pred = [prediction(rows[0], "select", "B"), prediction(rows[1], "select", "C"),
            prediction(rows[3], "select", "A", "B"), prediction(rows[4], "select", "B")]
    result = score(rows, pred)
    assert result["metrics"]["obsolete_option_reuse"] == {"numerator": 1, "denominator": 4, "rate": .25}
    assert result["obsolete_case_families"] == 3
    assert result["historical_relation_counts"] == {
        "obsolete": 4, "still_accepted": 2, "part_of_required_set": 1, "not_comparable": 1, "undocumented": 1}
    assert [r["selected_obsolete_option"] for r in result["items"]] == [True, False, False, False] + [None] * 5
    assert score(rows[-1:], [])["metrics"]["obsolete_option_reuse"]["rate"] is None
    for patch in ({"label": "E"}, {"as_of": rows[0]["clinical_as_of"]}, {"url": "unverified"}, {"locator": ""}):
        with pytest.raises(ValueError, match="historical option"):
            score([{**rows[0], "historical_option": {**ref, **patch}}], [])


def audit_fixture(kind="select"):
    row = gold("item")
    row["claims"] = [{"text": t, "evidence_ids": ["s"]} for t in ("First claim", "Second claim")]
    pred = prediction(row, kind, *(["A"] if kind == "select" else []))
    pred["text"] = "甲🙂 ab [X]"
    pred_hash = score([row], [pred])["items"][0]["prediction_sha256"]
    sheet = worksheet(row, pred, pred_hash)
    sheet.update(state="complete", inventory_complete=True, reviewer="fixture clinician", date="2026-11-15", minutes=1.5)
    sheet["reference_claims"] = [
        {"index": 1, "status": "supported", "span": {"start": 0, "end": 2, "quote": "甲🙂"},
         "evidence_ids": ["s"], "source_locators": {"s": "Table 1, first row"}, "note": "Matches the frozen table."},
        {"index": 2, "status": "omitted", "span": None, "evidence_ids": [], "note": "Answer does not address claim two."}]
    sheet["additional_claims"] = [{"status": "unverified", "span": {"start": 3, "end": 5, "quote": "ab"},
                                  "evidence_ids": [], "note": "Cannot establish the extra assertion."}]
    sheet["citations"] = [{"status": "unresolved", "span": {"start": 6, "end": 9, "quote": "[X]"},
                           "check_url": "https://example.org/registry", "check_locator": "Exact title query",
                           "note": "Lookup did not establish identity."}]
    return row, pred, sheet


def test_evidence_review_reports_observed_support_and_unresolved_citations_without_granting_clinical_approval():
    row, pred, sheet = audit_fixture()
    failed, bad_pred, unresolved = audit_fixture("parse_error")
    failed["id"] = bad_pred["id"] = unresolved["id"] = "unparsed"
    unresolved["prediction_sha256"] = score([failed], [bad_pred])["items"][0]["prediction_sha256"]
    unresolved["minutes"] = None
    sheet["citations"][0]["status"] = "confirmed_fabricated"
    sheet["citations"][0].update(verification_basis="affirmative_primary_confirmation",
                                 confirmation_excerpt="This citation was invented (synthetic fixture).")
    sheet["citations"][0]["check_locator"] = "Publisher confirmation, reference 42"
    sheet["citations"][0]["note"] = "Synthetic fixture representing an explicit confirmation."
    missed = gold("missing")
    result = score([row, failed, missed], [pred, bad_pred], evidence_reviews=[sheet, unresolved])
    audit = result["evidence_review"]
    assert result["assigned"] == 3 and audit["coverage"]["rate"] == 1
    assert audit["complete_audits"] == audit["readable_responses"] == 2
    assert audit["audits_with_reference_claims"] == 2 and audit["audits_without_reference_claims"] == 0
    assert audit["reference_claim_support"] == {"numerator": 2, "denominator": 4, "rate": .5}
    assert audit["additional_claim_counts"] == {"unverified": 2}
    assert audit["confirmed_fabricated_response_share"]["rate"] == .5
    assert audit["fabricated_response_rate_among_audited"] is None
    assert audit["responses_with_unresolved_citations_and_no_confirmed_fabrication"] == 1
    assert audit["timed_reviews"] == 1 and audit["median_review_minutes"] == audit["total_review_minutes"] == 1.5
    assert [r["clinical_result"] for r in result["items"]] == ["pending", "fail", "fail"]
    template = worksheet(row, pred, sheet["prediction_sha256"])
    partial = score([row, missed], [pred], evidence_reviews=[template])
    assert partial["evidence_review"]["complete_audits"] == 0
    assert [r["evidence_audit_status"] for r in partial["items"]] == ["pending", "not_reviewed"]
    assert [r["evidence_audit_status"] for r in result["items"]] == ["complete", "complete", "not_reviewed"]
    assert [r["fabricated_citation"] for r in result["items"]] == [True, None, None]
    with pytest.raises(ValueError, match="practice worksheet"):
        score([row], [pred], evidence_reviews=[{**sheet, "use": "public_development_review_practice"}])
    other = deepcopy(sheet)
    other["citations"] = []
    other["reference_claims"][0].update(status="contradicted", evidence_ids=["new"], source_locators={"new": "Table 3, row 1"})
    other["additional_evidence"] = [{"id": "new", "url": "https://example.org/new", "version": "v1",
                                    "locator": "Table 3", "available_on": row["clinical_as_of"]}]
    audit = score([row], [pred], evidence_reviews=[other])["evidence_review"]
    assert audit["fabricated_response_rate_among_audited"]["rate"] == 0 and audit["reference_claim_support"]["rate"] == 0
    assert score([row], [pred], evidence_reviews=[other])["items"][0]["fabricated_citation"] is False
    other["additional_evidence"][0]["available_on"] = "2026-10-02"
    with pytest.raises(ValueError, match="supplemental"):
        score([row], [pred], evidence_reviews=[other])
    other["additional_evidence"][0].update(available_on="2026-09-30", effective_from="2026-10-02")
    with pytest.raises(ValueError, match="supplemental"):
        score([row], [pred], evidence_reviews=[other])


def test_failed_lookup_is_not_affirmative_fabrication_and_sources_must_precede_cutoff():
    row, pred, sheet = audit_fixture()
    sheet["citations"][0]["status"] = "confirmed_fabricated"
    with pytest.raises(ValueError, match="affirmative"):
        score([row], [pred], evidence_reviews=[sheet])
    sheet["citations"][0]["status"] = "unresolved"
    sheet["reference_claims"][0].pop("source_locators")
    with pytest.raises(ValueError, match="locate the passage"):
        score([row], [pred], evidence_reviews=[sheet])
    row["evidence"][0]["published_on"] = "2099-11-26"
    with pytest.raises(ValueError, match="published after"):
        score([row], [pred])
    row["evidence"][0].update(published_on="2026-09-25", effective_from="2026-10-02")
    with pytest.raises(ValueError, match="not yet in effect"):
        score([row], [pred])


@pytest.mark.parametrize("error", ["hash", "context", "reviewer", "date", "minutes", "incomplete", "extra_ref",
                                    "duplicate", "unknown_id", "omission", "unicode_offset", "wrong_quote",
                                    "no_evidence", "citation_check", "duplicate_citation", "duplicate_extra"])
def test_evidence_review_rejects_stale_or_untraceable_findings(error):
    row, pred, sheet = audit_fixture()
    ref, omitted = sheet["reference_claims"]
    if error == "hash":
        pred["text"] += "!"
    elif error == "context":
        sheet["context"]["response"] = "different text"
    elif error == "reviewer":
        sheet["reviewer"] = " "
    elif error == "date":
        sheet["date"] = "2019-01-01"
    elif error == "minutes":
        sheet["minutes"] = float("nan")
    elif error == "incomplete":
        sheet["inventory_complete"] = False
    elif error == "extra_ref":
        sheet["reference_claims"].pop()
    elif error == "duplicate":
        omitted["index"] = 1
    elif error == "unknown_id":
        ref["evidence_ids"] = ["unknown"]
    elif error == "omission":
        omitted["span"] = ref["span"]
    elif error == "unicode_offset":
        ref["span"]["end"] = 3
    elif error == "wrong_quote":
        ref["span"]["quote"] = "another sentence"
    elif error == "no_evidence":
        ref["evidence_ids"] = []
    elif error == "citation_check":
        sheet["citations"][0]["check_url"] = ""
    elif error == "duplicate_citation":
        sheet["citations"] *= 2
    else:
        sheet["additional_claims"] *= 2
    with pytest.raises(ValueError):
        score([row], [pred], evidence_reviews=[sheet])


def test_cli_can_round_trip_evidence_worksheet_and_preserves_clinician_edits(tmp_path):
    row, pred, completed = audit_fixture("parse_error")
    paths = [tmp_path / name for name in ("gold.jsonl", "pred.jsonl", "worksheet.jsonl", "score.json")]
    gold_path, pred_path, output, scored = paths
    gold_path.write_bytes(json.dumps(row).encode())
    pred_path.write_bytes(json.dumps(pred).encode())
    args = ["--gold", str(gold_path), "--predictions", str(pred_path)]
    main([*args, "--worksheet", "--out", str(output)])
    blank = json.loads(output.read_bytes())
    assert blank["state"] == "pending" and blank["context"]["response"] == pred["text"]
    completed_bytes = json.dumps(completed).encode()
    output.write_bytes(completed_bytes)
    with pytest.raises(SystemExit):
        main([*args, "--worksheet", "--out", str(output)])
    assert output.read_bytes() == completed_bytes
    main([*args, "--evidence-reviews", str(output), "--out", str(scored)])
    report = json.loads(scored.read_bytes())
    assert report["evidence_review"]["complete_audits"] == 1 and report["items"][0]["clinical_result"] == "fail"
    with pytest.raises(SystemExit):
        main([*args, "--evidence-reviews", str(output), "--out", str(output)])
    assert output.read_bytes() == completed_bytes
    with pytest.raises(SystemExit):
        main([*args, "--out", str(output)])
    assert output.read_bytes() == completed_bytes
    main([*args, "--out", str(scored)])
    assert json.loads(scored.read_bytes())["evidence_review"]["complete_audits"] == 0


@pytest.mark.parametrize("data", ['{"verdict":"fail","verdict":"pass"}', '{"claim":{"status":1,"status":2}}'])
def test_review_reader_rejects_conflicting_keys_with_line_number(tmp_path, data):
    from medbench.clinical_score import read_jsonl

    source = tmp_path / "reviews.jsonl"
    source.write_bytes(('{}\n' + data).encode())
    with pytest.raises(ValueError, match=r"reviews\.jsonl:2: Duplicate JSON key"):
        list(read_jsonl(source))


def test_frozen_legacy_exports_do_not_guess_missing_options_from_text():
    rows = [gold("legacy-correct"), gold("legacy-other")]
    for row in rows:
        del row["offered_option_labels"]
        del row["rights_status"], row["source_rights"]
        row["messages"] = [{"role": "user", "content": "A. First sentence in a clinical note\nZ. A quoted line"}]
    correct = prediction(rows[0], "select", "A")
    result = score(rows, [correct, prediction(rows[1], "select", "Z")])
    assert result["selection_counts"] == {"offered": 1, "invalid": 0, "unverified": 1}
    assert result["metrics"]["selection_coverage"] is None and result["metrics"]["selected_answer_error"] is None
    assert result["metrics"]["structured_target_match"]["rate"] == .5
    assert {r["rights_status"] for r in result["items"]} == {"legacy_undocumented"}


def test_cli_accepts_curation_export_and_preserves_report_after_error(tmp_path):
    drafts = tmp_path / "drafts"
    drafts.mkdir()
    variant = {"id": "format-test-en", "lang": "en-US", "question": "Old question",
               "options": {"A": "3", "B": "4"}, "answer": "A",
               "clinical_update": {"question": "Current question", "as_of": "2026-11-26", "review_due": "2027-01-01",
                                   "jurisdiction": "test", "outcome": "no_valid_option", "valid_options": [],
                                   "answer": "Neither applies.", "rationale": "The test rule now specifies 5.",
                                   "evidence_ids": ["s"]}}
    case = {"concept_id": "format-test", "revision": 1, "kind": "mcq", "permitted_uses": ["development"],
            "source_rights": {"origin": "project_original", "status": "cleared", "attribution": "test authors",
                              "scope": "Original test fixture for public development.", "checked_on": "2026-11-26",
                              "allowed_uses": ["development"]},
            "split": "public_development", "evidence": gold("test")["evidence"], "variants": [variant]}
    (drafts / "case.json").write_text(json.dumps(case), encoding="utf-8")
    event = {"decision": "approve", "revision": case["revision"], "content_sha256": digest(case),
             "date": "2026-11-26", "reason": "test", "reviewer": "test clinician",
             "approved_uses": ["development"], "checked": ["clinical", "language", "temporal"]}
    rows = records(drafts, {variant["id"]: event}, "clinical-development", date(2026, 11, 26))
    row, = rows
    assert row["offered_option_labels"] == ["A", "B"] and row["valid_options"] == []
    assignment, answers, out = (tmp_path / name for name in ("gold.jsonl", "answers.jsonl", "report.json"))
    assignment.write_text(json.dumps(row), encoding="utf-8")
    answer = prediction(row, "no_valid_option")
    answers.write_text(json.dumps(answer), encoding="utf-8")
    frozen_hash = hashlib.sha256(assignment.read_bytes()).hexdigest()
    arguments = ["--gold", str(assignment), "--predictions", str(answers), "--out", str(out),
                 "--expected-gold-sha256", frozen_hash, "--score-as-of", "2026-11-26"]
    main(arguments)
    report = out.read_bytes()
    assert json.loads(report)["pending_clinical_review"] == [row["id"]]
    assert json.loads(report)["gold_sha256"] == frozen_hash and json.loads(report)["score_as_of"] == "2026-11-26"
    answers.write_text(json.dumps(answer) + "\n" + json.dumps(answer), encoding="utf-8")
    with pytest.raises(SystemExit):
        main(arguments)
    assert out.read_bytes() == report
    assignment.write_bytes(b"")
    answers.write_bytes(b"")
    with pytest.raises(SystemExit):
        main(arguments)
    assert out.read_bytes() == report
