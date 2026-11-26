import gzip
import json
from pathlib import Path

from medbench.moex_coverage import write
from medbench import moex_rulings as rulings


DECISIONS = Path(__file__).resolve().parents[1] / "datasets/moex/notices/decisions.json"


def published_dental_case():
    data = json.loads(DECISIONS.read_text(encoding="utf-8"))
    return next(it for it in data["clinical_items"] if it["id"] == "exam-yuan-111-143-dentaltechnology-046")


def inputs(tmp):
    case = published_dental_case()
    pid = "111110-109-0804"
    keys = []
    for role, label in (("S", "original_asset"), ("M", "corrected_asset")):
        ref = case[label]
        keys.append({"paper_id": pid, "asset_type": role, "asset_id": ref["asset_id"], "source_url": ref["url"],
                     "status": "verified", "sha256": ref["sha256"]})
    subject = {field: case[field] for field in ("exam_code", "category_code", "subject_code")}
    subject.update(year_roc="111", scope="medical")
    write(tmp / "index/subjects.tsv", list(subject), [subject])
    write(tmp / "files.tsv", list(keys[0]), keys)
    ledger = {"paper_id": pid, "sources": keys, "items": [
        {"id": pid + "-046", "number": 46, "section": "objective", "pages": [4], "rule": {"kind": "single", "choices": ["C"]},
         "key_evidence": {"S": {"token": "Ｃ", "page": 1}, "M": {"token": "C", "page": 1}}},
        {"id": pid + "-018", "number": 18, "section": "objective", "pages": [2], "rule": {"kind": "all_credit"},
         "key_evidence": {"S": {"token": "D", "page": 1}, "M": {"token": "#", "page": 1, "note": {"text": "第18題一律給分。"}}}}]}
    shard = tmp / "items/111/111110.jsonl.gz"
    shard.parent.mkdir(parents=True)
    with gzip.open(shard, "wt", encoding="utf-8") as stream:
        stream.write(json.dumps(ledger) + "\n")
    return keys, ledger, subject


def test_companion_rulings_have_only_sheet_provenance(tmp_path):
    inputs(tmp_path)
    result = rulings.build(tmp_path / "index", tmp_path / "files.tsv", tmp_path / "items", DECISIONS, tmp_path / "out")
    records = [json.loads(s) for s in (tmp_path / "out/items.jsonl").read_text(encoding="utf-8").splitlines()]
    cases = {r["decision_id"]: r for r in records}
    ref_id = published_dental_case()["id"]
    appeal = cases[ref_id]
    assert appeal["grid_comparison"] == "upheld_on_sheet_with_other_corrections"
    assert appeal["documents"][0]["identifier"] == "考試院111考臺訴決字第143號"
    assert appeal["item_id"] == "111110-109-0804-046"
    assert set(appeal["answer_sources"]) == {"S", "M"}
    assert appeal["compared_key_roles"] == ["S", "M"]
    companion = cases[ref_id + "-sheet-018"]
    assert companion["grid_comparison"] == "agrees" and companion["related_case_id"] == ref_id
    assert [d["kind"] for d in companion["documents"]] == ["official_correction_sheet"]
    assert "appeal_decision_date" not in companion["ruling"]
    boundary = cases["moex-news-5979-socialwork-034"]
    assert boundary["scope"] == "boundary_social_work"
    assert [s["kind"] for s in boundary["documents"]] == ["preliminary_statement", "official_item_ruling"]
    assert result["default_item_notice_status"] == "not_reviewed_against_independent_notices"
    assert "moex-news-7892" in result["aggregate_only_documents"]


def test_unlocated_and_disputed_item_numbers_stay_separate(tmp_path):
    pid = "086260-239-7004"
    subject = {"year_roc": "86", "exam_code": "086260", "category_code": "239",
               "subject_code": "7004", "scope": "medical"}
    write(tmp_path / "index/subjects.tsv", list(subject), [subject])
    write(tmp_path / "files.tsv", ["paper_id", "asset_type"], [])
    documents = {
        "compendium": {"url": "https://wwwc.moex.gov.tw/fixture.pdf", "sha256": "a" * 64, "locator": "p. 12"},
        "candidate-m": {"url": "https://wwwq.moex.gov.tw/fixture.pdf", "sha256": "b" * 64, "locator": "p. 1"},
    }
    base = {"id": "unlocated", "scope": "human_medical", "subject": "公共衛生學", "question": 86,
            "source": "compendium", "ruling": "accepted_alternatives", "accepted_options": ["B", "C"]}
    conflict = {"reported_question": 86, "candidate_paper_id": pid, "candidate_source": "candidate-m",
                "reason": "reported_item_exceeds_candidate_sheet_length", "candidate_item_count": 80,
                "candidate_question_68_responses": ["B", "BC"]}
    # An accidentally propagated paper or item ID must never override this conflict.
    disputed = {**base, "id": "disputed", "paper_item_id": pid + "-086", "mapping_conflict": conflict}
    path = tmp_path / "decisions.json"
    unnumbered = {"id": "no-item", "source": "compendium", "question": None,
                  "candidate_source": "candidate-m", "candidate_item_numbers": [49, 79]}
    path.write_text(json.dumps({"clinical_items": [base, disputed], "source_documents": documents,
                                "unresolved_case_summaries": [unnumbered]}), encoding="utf-8")
    summary = rulings.build(tmp_path / "index", tmp_path / "files.tsv", tmp_path / "items", path, tmp_path / "out")
    cases = {c["decision_id"]: c for c in map(json.loads, (tmp_path / "out/items.jsonl").read_text(encoding="utf8").splitlines())}
    assert cases["unlocated"]["mapping"] == "no_official_paper_identifier"
    assert cases["unlocated"]["item_id"] is None
    different = cases["disputed"]
    assert different["paper_id"] is None and different["item_id"] is None and different["ledger_item"] is None
    assert different["mapping"] == "documented_item_mapping_conflict"
    assert different["compared_key_roles"] == []
    assert different["ruling"]["accepted_options"] == ["B", "C"]
    assert different["ruling"]["mapping_conflict"] == conflict
    assert [d["role"] for d in different["documents"]] == ["decision", "conflicting_candidate_sheet"]
    assert [d["sha256"] for d in different["documents"]] == ["a" * 64, "b" * 64]
    assert different["answer_sources"]["M"]["version_comparison"] == "paper_unmapped"
    assert summary["records"] == 2 and "no-item" not in cases
    assert summary["unresolved_case_summaries"][0]["candidate_item_numbers"] == [49, 79]
    assert [r["sha256"] for r in summary["unresolved_case_summaries"][0]["documents"]] == ["a" * 64, "b" * 64]


def test_reviewed_corrected_sheet_without_original_never_confirms_original_key(tmp_path):
    keys, ledger, _ = inputs(tmp_path)
    case = published_dental_case()
    corrected_only = [r for r in keys if r["asset_type"] == "M"]
    del case["original_asset"]
    evidence = rulings._archive_evidence(case, corrected_only)
    assert evidence["S"]["version_comparison"] == "not_listed_in_current_manifest"
    assert rulings._grid_comparison(case, ledger, evidence)[0] == "paper_ledger_out_of_date"
    ledger["sources"] = corrected_only
    for item in ledger["items"]:
        del item["key_evidence"]["S"]
    status, item = rulings._grid_comparison(case, ledger, evidence)
    assert status == "reported_key_matches_correction_sheet_only"
    assert set(item["key_evidence"]) == {"M"}
    assert rulings._grid_comparison({**case, "original_key": "D"}, ledger, evidence)[0] == "rule_conflict"
    # A listed S with no reviewed digest has different provenance from an unlisted S.
    assert rulings._grid_comparison(case, ledger, rulings._archive_evidence(case, keys))[0] == "awaiting_matching_archived_keys"


def test_unfetched_different_sha_and_conflicting_rule_stay_distinct(tmp_path):
    keys, ledger, _ = inputs(tmp_path)
    case = published_dental_case()
    evidence = rulings._archive_evidence(case, keys)
    ledger["items"][0]["rule"] = {"kind": "all_credit"}
    assert rulings._grid_comparison(case, ledger, evidence)[0] == "rule_conflict"
    ledger["items"][0]["rule"] = {"kind": "unresolved"}
    assert rulings._grid_comparison(case, ledger, evidence)[0] == "ledger_rule_unresolved"
    changed = [{**k, "sha256": "0" * 64} for k in keys]
    assert rulings._grid_comparison(case, ledger, rulings._archive_evidence(case, changed))[0] == "archive_version_changed"
    pending = [{**k, "status": "pending"} for k in keys]
    assert rulings._grid_comparison(case, ledger, rulings._archive_evidence(case, pending))[0] == "awaiting_matching_archived_keys"
    assert rulings._grid_comparison(case, None, evidence)[0] == "paper_ledger_pending"


def test_same_subject_name_cannot_resolve_disagreeing_identifiers(tmp_path):
    _, _, subject = inputs(tmp_path)
    case = published_dental_case()
    source = {"url": "https://ws.exam.gov.tw/a.pdf", "sha256": "0" * 64}
    index = {"111110-109-0804": [subject]}
    assert rulings._identity(case, source, index) == ("111110-109-0804", "identified")
    assert rulings._identity({**case, "paper_id": "111110-109-0803"}, source, index) == (None, "conflicting_identifiers")
    assert rulings._identity(case, {**source, "sha256": ""}, index)[0] is None
    assert rulings._identity(case, {**source, "url": "https://elsewhere.example/exam.gov.tw"}, index)[0] is None
    assert rulings._identity(case, source, {"111110-109-0804": [subject, subject]}) == (None, "official_subject_absent_or_ambiguous")
