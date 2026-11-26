import json

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
