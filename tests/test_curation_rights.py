from datetime import date
import json

import pytest

from medbench.curation import SPLITS, digest, records


DAY = date(2026, 11, 26)
ORIGINAL = {
    "origin": "project_original", "status": "cleared", "allowed_uses": ["development"],
    "attribution": "Fixture authors", "scope": "Original wording released for public development.",
    "checked_on": "2026-11-25",
}
LICENSED = {
    **ORIGINAL, "origin": "third_party", "attribution": "Fixture publisher and authors",
    "scope": "Permission to adapt, translate and distribute the v2 items for public development.",
    "version": "v2", "source_url": "https://example.org/items/v2",
    "license": "Fixture permission for translations", "terms_url": "https://example.org/grants/1",
}


def assigned(folder, use, rights):
    variant = {
        "id": "demo-en", "lang": "en-US", "question": "Historical test question", "answer": "Old answer",
        "clinical_update": {"question": "Current test question", "as_of": "2026-11-01", "jurisdiction": "TW",
                            "review_due": "2027-01-01", "outcome": "free_text", "valid_options": [],
                            "answer": "Current answer", "rationale": "Test rationale", "evidence_ids": ["s"]},
    }
    draft = {
        "concept_id": "demo", "revision": 1, "kind": "open", "split": SPLITS[use],
        "permitted_uses": [use], "variants": [variant],
        "evidence": [{"id": "s", "version": "v1", "url": "https://example.org/reference", "locator": "Section 1"}],
    }
    if rights is not None:
        draft["source_rights"] = rights
    (folder / "demo.json").write_text(json.dumps(draft), encoding="utf-8")
    return {variant["id"]: {"decision": "approve", "revision": 1, "content_sha256": digest(draft),
                            "date": "2026-11-26", "reviewer": "test clinician", "reason": "test",
                            "checked": ["clinical", "language", "temporal"], "approved_uses": [use]}}


@pytest.mark.parametrize("use", ["train", "development", "evaluation"])
def test_clinician_approval_and_declared_item_uses_do_not_supply_data_rights(tmp_path, use):
    events = assigned(tmp_path, use, None)
    queue, = records(tmp_path, events, "queue", DAY)
    assert queue["clinical_status"] == "current" and queue["rights_status"] == "not_documented"
    assert not records(tmp_path, events, "clinical-" + use, DAY)
    if use == "train":
        assert not records(tmp_path, events, "train", DAY)
    else:
        historical, = records(tmp_path, events, use, DAY)
        assert historical["answer_basis"] == "source_version"


@pytest.mark.parametrize(("rights", "status"), [
    ({"status": "pending"}, "pending"),
    ({"status": "denied"}, "denied"),
    ({**ORIGINAL, "allowed_uses": ["evaluation"]}, "use_not_cleared"),
    ({**ORIGINAL, "allowed_uses": "development"}, "incomplete"),
    ({**ORIGINAL, "checked_on": "2026-11-27"}, "future_check"),
    ({**ORIGINAL, "checked_on": "unknown"}, "incomplete"),
    ({**ORIGINAL, "attribution": ""}, "incomplete"),
    ({**LICENSED, "version": ""}, "incomplete"),
    ({**LICENSED, "license": ""}, "incomplete"),
    ({**LICENSED, "source_url": "missing URL"}, "incomplete"),
    ({**LICENSED, "terms_url": "mailto:test@example.org"}, "incomplete"),
])
def test_incomplete_pending_or_unavailable_rights_stay_in_queue(tmp_path, rights, status):
    events = assigned(tmp_path, "development", rights)
    queue, = records(tmp_path, events, "queue", DAY)
    assert queue["rights_status"] == status
    assert not records(tmp_path, events, "clinical-development", DAY)


@pytest.mark.parametrize("rights", [ORIGINAL, LICENSED])
def test_releasable_rights_are_auditable_and_changes_invalidate_review(tmp_path, rights):
    events = assigned(tmp_path, "development", rights)
    result, = records(tmp_path, events, "clinical-development", DAY)
    assert result["rights_status"] == "cleared" and result["source_rights"] == rights
    assigned(tmp_path, "development", {**rights, "scope": "Different permission scope."})
    queue, = records(tmp_path, events, "queue", DAY)
    assert queue["decision"] == "stale_review"
    assert not records(tmp_path, events, "clinical-development", DAY)
