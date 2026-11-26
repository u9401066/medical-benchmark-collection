from collections import Counter
from copy import deepcopy
from importlib.util import module_from_spec, spec_from_file_location
import json
from pathlib import Path

import httpx
import pytest


PATH = (
    Path(__file__).resolve().parents[1]
    / "reports/anatomy-batch-pilot/prefix-cache/run.py"
)
SPEC = spec_from_file_location("anatomy_prefix_cache", PATH)
pilot = module_from_spec(SPEC)
SPEC.loader.exec_module(pilot)


def test_target_and_condition_are_balanced_in_each_round():
    jobs = pilot.plan()
    for r in range(1, 5):
        part = [j for j in jobs if j["round"] == r]
        assert Counter(j["id"] for j in part) == Counter(pilot.TARGETS)
        assert Counter((j["length"], j["state"]) for j in part) == Counter(pilot.ARMS)
    for key in pilot.TARGETS:
        assert Counter(
            (j["length"], j["state"]) for j in jobs if j["id"] == key
        ) == Counter(pilot.ARMS)


@pytest.fixture
def experiment():
    items = {
        k: {
            "question": f"Question {k}?",
            "options": {"A": "one", "B": "two"},
            "answer": "B",
        }
        for k in pilot.TARGETS
    }
    previous = []
    requests = Counter()

    def reply(req):
        nonlocal previous
        path = req.url.path
        body = json.loads(req.content)
        requests[path] += 1
        if path == "/apply-template":
            return httpx.Response(
                200, json={"prompt": "|".join(m["content"] for m in body["messages"])}
            )
        if path == "/tokenize":
            assert body["parse_special"] is True and body["add_special"] is False
            return httpx.Response(200, json={"tokens": list(body["content"].encode())})
        if path == "/slots/0":
            assert req.url.params["action"] == "erase"
            old, previous = previous, []
            return httpx.Response(200, json={"id_slot": 0, "n_erased": len(old)})
        assert path == "/completion"
        assert {k: v for k, v in body.items() if k != "prompt"} == pilot.PARAMS
        ids = body["prompt"]
        n = next(
            (i for i, (a, b) in enumerate(zip(previous, ids)) if a != b),
            min(len(previous), len(ids)),
        )
        previous = ids
        timings = {
            "cache_n": n,
            "prompt_n": len(ids) - n,
            "prompt_ms": float(len(ids) - n),
            "predicted_n": 8,
            "predicted_ms": 10.0,
        }
        return httpx.Response(
            200,
            json={
                "id_slot": 0,
                "timings": timings,
                "content": '{"choice":"A"}',
                "tokens_evaluated": len(ids),
                "tokens_predicted": 8,
                "tokens_cached": len(ids) + 7,
                "stop_type": "eos",
                "truncated": False,
            },
        )

    with httpx.Client(
        base_url="https://fixture.invalid", transport=httpx.MockTransport(reply)
    ) as client:
        result = pilot.run(items, client)
    assert requests == {
        "/apply-template": 10,
        "/tokenize": 10,
        "/completion": 32,
        "/slots/0": 24,
    }
    return items, result


def test_same_target_received_cold_and_warm_preserving_token_accounting(experiment):
    items, result = experiment
    assert pilot.replay(items, result) == result["summary"]
    for trial in result["trials"]:
        t = trial["target"]["timings"]
        name = trial["length"] + "/" + trial["id"]
        assert trial["primer"]["timings"]["cache_n"] == 0
        if trial["state"] == "cold":
            assert trial["before_target"]["n_erased"] > 0 and t["cache_n"] == 0
        else:
            assert (
                trial["before_target"] is None
                and t["cache_n"] == result["tokens"]["overlaps"][name]["length"]
            )


@pytest.mark.parametrize(
    "mutation",
    ["cold_hit", "fake_boundary", "raw_answer", "missing_trial", "wrong_target"],
)
def test_replay_detects_corruption(experiment, mutation):
    items, original = experiment
    result = deepcopy(original)
    row = result["trials"][0]
    if mutation == "cold_hit":
        t = row["target"]["timings"]
        t["cache_n"] += 1
        t["prompt_n"] -= 1
    elif mutation == "fake_boundary":
        o = next(iter(result["tokens"]["overlaps"].values()))
        o["target_next"] = o["primer_next"]
    elif mutation == "raw_answer":
        row["target"]["content"] += " "
    elif mutation == "missing_trial":
        result["trials"].pop()
    else:
        row["id"] = pilot.TARGETS[-1]
    with pytest.raises(ValueError):
        pilot.replay(items, result)
