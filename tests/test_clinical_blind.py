from copy import deepcopy
import json

import pytest

from medbench import clinical_blind as blind
from medbench.clinical_run import payload, sha
from medbench.clinical_score import prediction_digest
from test_clinical_score import gold, prediction


@pytest.fixture
def frozen(tmp_path):
    items = [gold(key) for key in ("case-zh", "case-en", "second", "third")]
    items[0]["family_id"] = items[1]["family_id"] = "family-first"
    items[1]["lang"] = "en-US"
    for i, item in enumerate(items):
        item["messages"] = [
            {"role": "user", "content": f"Test question {i}"},
            {"role": "assistant", "content": f"Test reference {i}"},
        ]
        item["claims"] = [{"text": "First claim", "evidence_ids": ["s"]}]
    visible = "說明🐧\nSecond line [study]"
    left = [
        {
            **prediction(items[0], "select", "A"),
            "text": visible,
            "model": "model-version-left",
        },
        prediction(items[1], "timeout"),
        prediction(items[3], "parse_error"),
    ]
    right = [prediction(items[0], "select", "B"), prediction(items[1], "select", "A")]
    paths = [tmp_path / f"{stem}.jsonl" for stem in ("approved", "left", "right")]
    for path, rows in zip(paths, (items, left, right), strict=True):
        path.write_bytes(b"".join(payload(row) for row in rows))
    args = [
        "--gold",
        str(paths[0]),
        "--expected-gold-sha256",
        sha(paths[0].read_bytes()),
        "--left",
        str(paths[1]),
        "--right",
        str(paths[2]),
        "--key",
        str(tmp_path / "private" / "key.json"),
    ]
    return args, items, left, right, paths[1]


def test_pair_packet_roundtrip_keeps_raw_spans_and_full_assignment(frozen, tmp_path):
    args, items, left, _, left_path = frozen
    packet_path = tmp_path / "review" / "packet.json"
    blind.main(["prepare", *args, "--packet", str(packet_path)])
    packet_bytes = packet_path.read_bytes()
    assert all(
        token not in packet_bytes
        for token in (
            b"model-version-left",
            b"predictions_sha256",
            b"secret",
            b"case-zh",
        )
    )
    packet = json.loads(packet_bytes)
    assert len(packet) == 4 and len({answer["pair_id"] for answer in packet}) == 3
    first = [
        answer
        for answer in packet
        if answer["context"]["question"] == "Test question 0"
    ]
    assert sorted(answer["position"] for answer in first) == [1, 2]
    assert first[0]["pair_id"] == first[1]["pair_id"]
    assert all(
        answer["context"]["reference_answer"] == "Test reference 0" for answer in first
    )
    raw = left[0]["text"]
    row = next(answer for answer in first if answer["context"]["response"] == raw)
    row.update(
        reviewer="Fixture review",
        date="2026-11-20",
        clinical_verdict="pass",
        clinical_reason="Exact expected answer",
        state="complete",
        inventory_complete=True,
        minutes=2.5,
    )
    row["reference_claims"][0].update(
        status="supported",
        span={"start": 0, "end": 3, "quote": "說明🐧"},
        evidence_ids=["s"],
        source_locators={"s": "section 1"},
        note="Checked source locator for the synthetic case.",
    )

    review_path = tmp_path / "returned.json"
    review_path.write_bytes(blind.json_bytes([row]))
    output = tmp_path / "private" / "scored.json"
    finish = [
        "intake",
        *args,
        "--reviews",
        str(review_path),
        "--out",
        str(output),
        "--score-as-of",
        "2026-11-26",
    ]
    blind.main(finish)
    blind.main(finish)  # Repeating an unchanged intake leaves the exact artifact.
    returned = json.loads(output.read_bytes())
    assert returned["coverage"]["pairs_with_two_recorded_answers"] == 1
    assert returned["coverage"]["pairs_with_no_recorded_answers"] == 1
    assert returned["review_assignment_sha256"] == sha(packet_bytes)
    assert returned["returned_reviews_sha256"] == sha(review_path.read_bytes())
    arm = returned["arms"]["left"]
    review = arm["clinical_reviews"][0]
    assert review["id"] == items[0]["id"]
    assert review["prediction_sha256"] == prediction_digest(left[0])
    assert arm["score"]["evidence_review"]["total_review_minutes"] == 2.5
    assert (
        arm["score"]["assigned"] == returned["arms"]["right"]["score"]["assigned"] == 4
    )
    assert returned["paired"]["clinical_pass"]["pending_pairs"] == 1
    assert returned["paired"]["clinical_pass"]["right_minus_left"] is None

    left_path.write_bytes(left_path.read_bytes() + b"\n")
    with pytest.raises(SystemExit):
        blind.main(finish)


def test_rejects_relabelled_or_edited_packet_and_recovers_original(tmp_path, frozen):
    args, _, _, _, _ = frozen
    p = tmp_path / "packet.json"
    prep = ["prepare", *args, "--packet", str(p)]
    blind.main(prep)
    first = p.read_bytes()
    p.unlink()
    blind.main(prep)
    assert p.read_bytes() == first
    rows = json.loads(first)
    parsed_error = next(row for row in rows if not row["clinical_reviewable"])
    r = tmp_path / "review.json"
    out = tmp_path / "out.json"
    finish = ["intake", *args, "--reviews", str(r), "--out", str(out)]
    modified = deepcopy(rows[0])
    modified["context"]["response"] += " "
    for incorrect in (
        [modified],
        [rows[0], rows[0]],
        [{**rows[0], "id": "unknown"}],
        [
            {
                **parsed_error,
                "clinical_verdict": "pass",
                "clinical_reason": "Invalid manual override",
            }
        ],
    ):
        r.write_bytes(blind.json_bytes(incorrect))
        with pytest.raises(SystemExit):
            blind.main(finish)
        assert not out.exists()


def test_stratified_sample_keeps_both_languages_and_reports_sampling_fractions(
    tmp_path, frozen
):
    args, items, _, _, _ = frozen
    plan = [
        {"name": "mixed-language", "family_ids": ["family-first"], "n": 1},
        {"name": "control", "family_ids": ["family-second", "family-third"], "n": 1},
    ]
    selected = blind.draw_families(items, plan, 15)
    assert selected == blind.draw_families(items[::-1], plan[::-1], 15)
    assert selected[0]["inclusion_probability"] == 0.5
    assert selected[1]["inclusion_probability"] == 1.0
    for invalid in (
        plan[:1],
        [*plan, {"name": "duplicate", "family_ids": ["family-first"], "n": 1}],
    ):
        with pytest.raises(ValueError):
            blind.draw_families(items, invalid, 15)
    p = tmp_path / "plan.json"
    p.write_bytes(blind.json_bytes(plan))
    packet = tmp_path / "answers.json"
    blind.main(
        [
            "prepare",
            *args,
            "--plan",
            str(p),
            "--packet",
            str(packet),
            "--sample-seed",
            "15",
        ]
    )
    result = json.loads(packet.read_bytes())
    questions = {row["context"]["question"] for row in result}
    assert {"Test question 0", "Test question 1"} <= questions
    key = json.loads((tmp_path / "private" / "key.json").read_bytes())
    assert key["strata"] == selected
