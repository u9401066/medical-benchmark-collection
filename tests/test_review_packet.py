import json
from datetime import date

import pytest

from medbench.curation import decisions, records
from medbench.review_packet import candidate, main, markdown, prepare, read_json


ON = date(2026, 11, 26)
URL = "https://example.org/policy"
FINGERPRINT = "a" * 64


@pytest.fixture
def review(tmp_path):
    folder = tmp_path / "drafts"
    folder.mkdir()
    source = folder / "example.json"
    historical = {
        "comparison": "same_decision_single_option",
        "as_of": "2024-12-31",
        "url": URL,
        "locator": "section 1",
    }
    update = {
        "question": "Current question",
        "as_of": ON.isoformat(),
        "review_due": "2027-03-01",
        "jurisdiction": "TW",
        "outcome": "single_valid_option",
        "valid_options": ["B"],
        "answer": "B",
        "rationale": "The current test rule applies.",
        "evidence_ids": ["order"],
    }
    draft = {
        "concept_id": "example",
        "revision": 1,
        "kind": "mcq",
        "split": "public_development",
        "permitted_uses": ["development"],
        "source_rights": {
            "origin": "project_original",
            "status": "cleared",
            "allowed_uses": ["development"],
            "attribution": "test fixture",
            "scope": "public development",
            "checked_on": ON.isoformat(),
        },
        "variants": [
            {
                "id": "example-" + lang,
                "lang": lang,
                "question": "Historical question",
                "options": {"A": "First", "B": "Second"},
                "answer": "A",
                "historical_basis": historical,
                "clinical_update": update,
            }
            for lang in ("zh-TW", "en-US")
        ],
        "evidence": [
            {
                "id": "order",
                "url": URL,
                "locator": "section 2",
                "version": "2",
                "published_on": "2024-12-30",
                "effective_from": "2025-01-01",
                "watch_xpath": "//p",
                "passage_sha256": FINGERPRINT,
            }
        ],
    }
    source.write_text(json.dumps(draft), encoding="utf-8")
    log = tmp_path / "decisions.jsonl"
    watch = {
        "checked_on": ON.isoformat(),
        "sources": [
            {
                "url": URL,
                "watch_xpath": "//p",
                "expected_sha256": FINGERPRINT,
                "observed_sha256": FINGERPRINT,
                "status": "unchanged",
            },
        ],
    }
    packet = prepare(folder, {}, ON, watch)
    sheet = packet["reviews"][0]
    sheet["review"].update(
        decision="approve",
        reviewer="Test fixture",
        date=ON.isoformat(),
        reason="Verified both dates for this language.",
        evidence_locator="HPA service eligibility text and Gazette p. 101",
        checked=["clinical", "language", "temporal"],
        approved_uses=["development"],
    )
    return folder, source, log, watch, packet, sheet


def test_review_worksheet_preserves_historical_and_current_context(review):
    folder, _, _, watch, _, sheet = review
    family = sheet["context"]["item"]["family_id"]
    packet = prepare(folder, {}, ON, watch, [family])
    assert len(packet["reviews"]) == 2
    assert all(row["review"]["decision"] is None for row in packet["reviews"])
    rendered = markdown(packet)
    for row in packet["reviews"]:
        context = row["context"]
        assert context["item"]["id"] in rendered
        assert (
            context["question"] in rendered
            and context["clinical_update"]["question"] in rendered
        )
        assert "2024-12-31" in rendered and "2026-11-26" in rendered


def test_import_creates_separate_valid_ledger_and_only_approved_translation(
    review, tmp_path
):
    folder, _, log, watch, packet, sheet = review
    prepared = tmp_path / "completed.json"
    prepared.write_text(json.dumps(packet), encoding="utf-8")
    watch_path = tmp_path / "watch.json"
    watch_path.write_text(json.dumps(watch), encoding="utf-8")
    out = tmp_path / "candidate.jsonl"
    args = [
        "candidate",
        "--drafts",
        str(folder),
        "--decisions",
        str(log),
        "--as-of",
        ON.isoformat(),
        "--watch-report",
        str(watch_path),
        "--packet",
        str(prepared),
        "--out",
        str(out),
    ]
    main(args)
    original = out.read_bytes()
    events = decisions(out, ON)
    assert list(events) == [sheet["context"]["item"]["id"]]
    assert len(records(folder, events, "clinical-development", ON, watch)) == 1
    assert records(folder, events, "clinical-evaluation", ON, watch) == []
    assert records(folder, events, "clinical-train", ON, watch) == []
    assert not log.exists()
    with pytest.raises(SystemExit):
        main(args)
    assert out.read_bytes() == original


@pytest.mark.parametrize(
    "change",
    [
        "text",
        "context",
        "context_lang",
        "option_order",
        "other_decision",
        "old_date",
        "rights",
        "watch",
        "extra_uses",
        "missing_temporal",
    ],
)
def test_changed_or_unreviewable_proposal_is_rejected(review, change):
    folder, source, log, watch, packet, sheet = review
    raw = b""
    if change in {"text", "rights"}:
        draft = read_json(source)
        if change == "text":
            draft["variants"][0]["question"] += " changed"
        else:
            draft["source_rights"]["status"] = "pending"
        source.write_text(json.dumps(draft), encoding="utf-8")
        if change == "rights":
            packet["reviews"][0]["context"] = prepare(folder, {}, ON, watch)["reviews"][
                0
            ]["context"]
    if change == "context":
        sheet["context"]["clinical_update"]["question"] += " changed"
    if change == "context_lang":
        sheet["context"]["item"]["lang"] = "en-US"
    if change == "option_order":
        sheet["context"]["options"] = {"B": "Second", "A": "First"}
    if change == "other_decision":
        raw = candidate(packet, folder, log, raw, ON, watch)
    if change == "old_date":
        sheet["review"]["date"] = "2026-11-25"
    if change == "watch":
        watch = None
    if change == "extra_uses":
        sheet["review"]["approved_uses"].append("train")
    if change == "missing_temporal":
        sheet["review"]["checked"].remove("temporal")
    with pytest.raises(ValueError):
        candidate(packet, folder, log, raw, ON, watch)


def test_revise_working_copy_is_permitted_when_watch_has_no_observation(review):
    folder, _, log, _, packet, sheet = review
    sheet["review"].update(decision="revise", approved_uses=[])
    merged = candidate(packet, folder, log, b"", ON)
    assert next(iter(decisions(log, raw=merged).values()))["decision"] == "revise"


def test_order_available_but_not_effective_fails_before_an_export(review):
    folder, source, _, watch, *_ = review
    draft = read_json(source)
    order = draft["evidence"][0]
    order["effective_from"] = "2026-11-27"
    source.write_text(json.dumps(draft), encoding="utf-8")
    with pytest.raises(ValueError, match="not yet in effect"):
        records(folder, {}, "queue", ON, watch)
