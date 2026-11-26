import asyncio
from collections import Counter
import hashlib
import json
import sys

import httpx
import pytest

from medbench import batch_probe as probe


def item(key, subject="exam"):
    return {
        "id": key,
        "kind": "mcq",
        "question": f"Question {key}?",
        "options": {"A": "Alpha", "B": "Beta", "C": "Gamma"},
        "answer": "A",
        "meta": {"subject": subject, "note": "reviewer-only"},
    }


@pytest.mark.parametrize("size", [2, 3])
def test_rotated_groups_change_positions_and_neighbors_on_one_reproducible_assignment(
    size,
):
    items = [item(str(i)) for i in range(9)]
    selected, conditions = probe.make_plan(items, 6, size, 2, 950)
    assert (selected, conditions) == probe.make_plan(items, 6, size, 2, 950)
    plans = {name: (concurrency, groups) for name, concurrency, groups in conditions}
    assert set(plans) == {
        "single",
        "single_repeat",
        "independent",
        "shared",
        "shared_rotated",
    }
    assert (
        plans["single"][1]
        == plans["single_repeat"][1]
        == plans["independent"][1]
        == [[k] for k in selected]
    )
    assert plans["single"][0] == plans["single_repeat"][0] == 1
    assert plans["independent"][0] == 2
    groupings = []
    for name in ("shared", "shared_rotated"):
        concurrency, groups = plans[name]
        assert concurrency == 1 and all(len(group) == size for group in groups)
        assert Counter(k for group in groups for k in group) == Counter(selected)
        groupings.append(
            {k: (group.index(k), set(group) - {k}) for group in groups for k in group}
        )
    for key in selected:
        (p1, neighbors1), (p2, neighbors2) = (grouping[key] for grouping in groupings)
        assert p1 != p2 and neighbors1 != neighbors2


def test_one_ambiguous_or_missing_id_does_not_damage_other_answers():
    items = [item(k) for k in ("duplicate", "missing", "wrong-label", "valid")]
    records = [
        {"id": "duplicate", "answer": "B"},
        {"id": "valid", "answer": "C"},
        {"id": "absent-from-batch", "answer": "A"},
        {"id": "duplicate", "answer": "C"},
        {"id": "wrong-label", "answer": "outside-options"},
        {},
    ]
    parsed, errors = probe.parse_batch(json.dumps({"answers": records}), items)
    assert parsed == {
        "duplicate": None,
        "missing": None,
        "wrong-label": None,
        "valid": "C",
    }
    assert Counter(errors) == Counter(
        ["duplicate_id", "missing_id", "unknown_id", "invalid_label", "invalid_record"]
    )
    malformed, errors = probe.parse_batch('{"answers": [', items)
    assert malformed == dict.fromkeys(parsed) and errors


def test_throughput_uses_elapsed_wall_time_and_flips_include_wrong_to_wrong():
    gold = dict.fromkeys(["q1", "q2", "q3", "q4"], "A")
    calls = [
        {
            "ids": ["q1", "q2"],
            "predictions": {"q1": "B", "q2": "A"},
            "latency_s": 6,
            "usage": {"prompt_tokens": 17, "completion_tokens": 4},
            "errors": [],
        },
        {
            "ids": ["q3", "q4"],
            "predictions": {"q3": None, "q4": "C"},
            "latency_s": 5,
            "usage": {"prompt_tokens": 23},
            "errors": ["missing_id"],
        },
    ]
    answers, summary = probe.summarize(calls, 8, gold)
    assert (
        summary["assigned"],
        summary["requests"],
        summary["parsed"],
        summary["correct_source_key"],
    ) == (4, 2, 3, 1)
    assert summary["parsed_per_hour"] == 1350 and summary["correct_per_hour"] == 450
    assert summary["p95_request_s"] == 6 and summary["protocol_events"] == {
        "missing_id": 1
    }
    assert summary["prompt_tokens"] == 40 and summary["completion_tokens"] is None
    base = {"q1": "C", "q2": "B", "q3": "A", "q4": "A"}
    comparison = probe.paired(base, answers, gold)
    assert comparison["assigned"] == 4 and comparison["both_parsed"] == 3
    assert comparison["flips"] == 3 and set(comparison["flipped_ids"]) == {
        "q1",
        "q2",
        "q4",
    }
    assert comparison["wrong_to_correct"] == 1 and comparison["correct_to_wrong"] == 1
    with pytest.raises(ValueError):
        probe.summarize(calls[:1], 8, gold)


def test_failed_request_leaves_all_assigned_ids_and_length_finish_is_reported():
    async def exercise():
        items = [item("q1"), item("q2")]
        payload = {"answers": [{"id": "q1", "answer": "A"}]}
        choices = [
            {"finish_reason": "length", "message": {"content": json.dumps(payload)}}
        ]
        responses = iter(
            [httpx.Response(503), httpx.Response(200, json={"choices": choices})]
        )
        transport = httpx.MockTransport(lambda _: next(responses))
        async with httpx.AsyncClient(
            base_url="https://mock.invalid", transport=transport
        ) as client:
            failed, raw = await probe.ask(client, "fixture", items, 9, 32)
            assert (
                failed["predictions"] == {"q1": None, "q2": None}
                and failed["errors"]
                and raw is None
            )
            partial, raw = await probe.ask(client, "fixture", items, 9, 32)
            assert partial["predictions"] == {"q1": "A", "q2": None}
            assert Counter(partial["errors"]) == Counter(["missing_id", "truncated"])
            assert json.loads(raw) == payload

    asyncio.run(exercise())


def test_cli_over_mock_http_keeps_gold_private_and_warmup_out_of_denominators(
    tmp_path, monkeypatch
):
    items_file, report_file, raw_file = (
        tmp_path / name for name in ("items.jsonl", "report.json", "raw.json")
    )
    pool = [item(f"q{i}") for i in range(4)] + [item("filtered-out", "other")]
    items_file.write_text(
        "".join(json.dumps(row) + "\n" for row in pool), encoding="utf-8"
    )
    in_flight, peak = 0, 0
    packets = []

    async def respond(request):
        nonlocal in_flight, peak
        in_flight += 1
        peak = max(peak, in_flight)
        try:
            await asyncio.sleep(0)
            assert (
                request.method == "POST" and request.url.path == "/v1/chat/completions"
            )
            body = json.loads(request.content)
            (message,) = body["messages"]
            questions = json.loads(message["content"].split("\n", 1)[1])
            ids = [question["id"] for question in questions]
            packets.append(ids)
            assert all(
                set(question) == {"id", "question", "options"} for question in questions
            )
            assert body["max_tokens"] == 32 * len(questions)
            assert body["seed"] == 712 and body["model"] == "fixture"
            assert (
                message["role"] == "user" and "reviewer-only" not in message["content"]
            )
            answers = [
                {"id": key, "answer": "B" if key == "warmup" else "A"}
                for key in reversed(ids)
            ]
            content = json.dumps({"answers": answers})
            return httpx.Response(
                200,
                json={
                    "choices": [
                        {"finish_reason": "stop", "message": {"content": content}}
                    ],
                    "usage": None,
                },
            )
        finally:
            in_flight -= 1

    original_client = httpx.AsyncClient
    monkeypatch.setattr(
        probe.httpx,
        "AsyncClient",
        lambda **kw: original_client(transport=httpx.MockTransport(respond), **kw),
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "batch_probe",
            "--items",
            str(items_file),
            "--out",
            str(report_file),
            "--raw",
            str(raw_file),
            "--url",
            "https://mock.invalid",
            "--model",
            "fixture",
            "--subject",
            "exam",
            "--sample",
            "4",
            "--pack-size",
            "2",
            "--concurrency",
            "2",
            "--seed",
            "712",
            "--tokens-per-item",
            "32",
        ],
    )
    probe.main()
    report = json.loads(report_file.read_text(encoding="utf-8"))
    raw = json.loads(raw_file.read_text(encoding="utf-8"))
    assert report["items_sha256"] == hashlib.sha256(items_file.read_bytes()).hexdigest()
    assert report["eligible"] == 4 and report["warmup_excluded"]["ids"] == ["warmup"]
    assert len(packets) == 17 and packets.count(["warmup"]) == 1 and peak == 2
    assert (
        set(raw) == set(report["conditions"]) and "filtered-out" not in report["gold"]
    )
    for name, condition in report["conditions"].items():
        summary = condition["summary"]
        assert summary["requests"] == (2 if name.startswith("shared") else 4)
        assert (
            summary["assigned"]
            == summary["parsed"]
            == summary["correct_source_key"]
            == 4
        )
        assert summary["prompt_tokens"] is None and summary["completion_tokens"] is None
        for call, content in zip(condition["calls"], raw[name], strict=True):
            assert (
                call["response_sha256"] == hashlib.sha256(content.encode()).hexdigest()
            )
            assert "warmup" not in call["ids"]
    for comparison in report["paired_vs_single"].values():
        assert comparison["both_parsed"] == 4 and comparison["flips"] == 0
