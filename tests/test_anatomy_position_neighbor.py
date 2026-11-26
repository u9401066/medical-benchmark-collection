import asyncio
from collections import Counter, defaultdict
from importlib.util import module_from_spec, spec_from_file_location
import json
from pathlib import Path

import httpx
import pytest


ROOT = Path(__file__).resolve().parents[1]
SPEC = spec_from_file_location(
    "position_neighbor", ROOT / "reports/anatomy-batch-pilot/position-neighbor/run.py"
)
pilot = module_from_spec(SPEC)
SPEC.loader.exec_module(pilot)


@pytest.fixture
def items():
    return {
        f"id{i}": {
            "id": f"id{i}",
            "question": f"Practice item {i}?",
            "options": {"A": "one", "B": "two", "C": "three", "D": "four"},
            "answer": "A",
        }
        for i in range(18)
    }


def test_every_position_and_neighbor_contrast_holds_other_factor_fixed(items):
    targets, plan = pilot.assignment(items)
    assert len(plan) == 36 and len(set(targets)) == 6
    per_target = defaultdict(dict)
    neighbors = defaultdict(list)
    for round_no in range(1, 7):
        jobs = [j for j in plan if j["round"] == round_no]
        assert Counter(j["arm"] for j in jobs) == Counter(pilot.ARMS)
        assert Counter(j["target"] for j in jobs) == Counter(targets)
        for j in jobs:
            per_target[j["target"]][j["arm"]] = j["ids"]
    for target, arms in per_target.items():
        assert arms["single"] == arms["single_repeat"] == [target]
        assert arms["first_a"][0] == arms["first_b"][0] == target
        assert arms["first_a"] == arms["second_a"][::-1]
        assert arms["first_b"] == arms["second_b"][::-1]
        a, b = arms["first_a"][1], arms["first_b"][1]
        assert a != b and a not in targets and b not in targets
        neighbors["a"].append(a)
        neighbors["b"].append(b)
    assert len(set(neighbors["a"])) == 6
    assert set(neighbors["a"]) == set(neighbors["b"])


def test_rejects_a_different_full_source(tmp_path):
    source = tmp_path / "anatomy.jsonl"
    source.write_bytes(b'{"id":"anatomy-test-001"}\n')
    with pytest.raises(ValueError, match="full normalized"):
        pilot.load_items(source)


def test_paired_denominators_and_wrong_to_wrong_flips():
    gold = dict.fromkeys("abcdef", "A")
    values = [
        {k: v for k, v in zip(gold, labels)}
        for labels in (
            ["B", "A", "A", None, None, "B"],
            ["C", "B", None, "B", None, "A"],
        )
    ]
    arms = {name: values[0] for name in pilot.ARMS}
    arms["single_repeat"] = values[1]
    result = pilot.summarize(arms, gold)
    pairs = result["comparisons"]["single_vs_single_repeat"]
    assert pairs["assigned"] == 6 and pairs["both_parsed"] == 3
    assert pairs["flips"] == 3 and pairs["flipped_ids"] == ["a", "b", "f"]
    assert [
        pairs[k] for k in ("correct_to_wrong", "wrong_to_correct", "wrong_to_wrong")
    ] == [1, 1, 1]
    assert [
        pairs[k] for k in ("missing_left_only", "missing_right_only", "missing_both")
    ] == [["d"], ["c"], ["e"]]
    assert result["arms"]["single"]["correct_source_key"] == 2


def test_wire_protocol_raw_replay_and_tamper_detection(items, monkeypatch):
    calls = []

    def respond(request):
        data = json.loads(request.content)
        assert {k: v for k, v in data.items() if k != "messages"} == pilot.PARAMETERS
        (message,) = data["messages"]
        assert message["role"] == "user"
        group = json.loads(message["content"].split("\n", 1)[1])
        assert all(set(q) == {"id", "question", "options"} for q in group)
        calls.append(group)
        if len(calls) == 2:
            return httpx.Response(503)
        answers = [{"id": q["id"], "answer": "B"} for q in reversed(group)]
        if len(calls) == 3:
            answers.append(answers[0])
        choice = {
            "finish_reason": "stop",
            "message": {"content": json.dumps({"answers": answers})},
        }
        return httpx.Response(200, json={"choices": [choice]})

    client = httpx.AsyncClient
    monkeypatch.setattr(
        pilot.httpx,
        "AsyncClient",
        lambda **kw: client(transport=httpx.MockTransport(respond), **kw),
    )
    report = asyncio.run(pilot.run(items, "https://mock.invalid"))
    assert len(calls) == 36 and sum(map(len, calls)) == 60
    assert report["calls"][1]["raw"] is None
    assert report["summary"] == pilot.replay(items, report)
    report["calls"][0]["raw"] += " "
    with pytest.raises(ValueError, match="response"):
        pilot.replay(items, report)
    report["calls"][0]["raw"] = report["calls"][0]["raw"][:-1]
    report["calls"] = report["calls"][1:]
    with pytest.raises(ValueError, match="count"):
        pilot.replay(items, report)
