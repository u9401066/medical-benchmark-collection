import importlib.util
import json
from copy import deepcopy
from pathlib import Path

import pytest


HERE = Path(__file__).resolve().parents[1] / "reports/tw-fit-date-probe"
SPEC = importlib.util.spec_from_file_location(
    "fit_grounding_probe", HERE / "grounding.py"
)
grounding = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(grounding)


def recorded():
    return json.loads((HERE / "grounding-results.json").read_bytes())


def test_only_current_prompt_gets_the_identical_frozen_publication():
    report = recorded()
    grounding.verify(report)
    src = report["source"]
    assignments = grounding.assignment(src)
    original = {
        m["id"]: prompt
        for m, prompt, _ in grounding.baseline.assignment()
        if m["period"] == "current"
    }
    first_arms = [m["arm"] for m, _, _ in assignments[::2]]
    assert first_arms.count("closed") == first_arms.count("supplied") == 3
    for m, prompt, _ in assignments:
        assert m["period"] == "current"
        if m["arm"] == "closed":
            assert prompt == original[m["id"]] and src["text"] not in prompt
        else:
            assert prompt.endswith(original[m["id"]]) and prompt.count(src["text"]) == 1
    assert len({m["id"] for m, _, _ in assignments}) == 6


@pytest.mark.parametrize("field", ["source", "arm", "raw", "summary"])
def test_grounding_offline_verifier_rejects_changed_evidence_or_pairs(field):
    report = deepcopy(recorded())
    if field == "source":
        report["source"]["text"] = report["source"]["text"].replace("45-74", "50-74")
    elif field == "arm":
        report["responses"][0]["arm"] = "historical"
    elif field == "raw":
        report["responses"][0]["raw"] += " "
    else:
        report["summary"]["groups"]["all"]["closed"]["draft_match"]["denominator"] = 5
    with pytest.raises(ValueError):
        grounding.verify(report)


def test_truncated_answer_stays_in_assigned_denominator():
    rows = recorded()["responses"]
    original = grounding.summary(rows)
    rows[0]["choice"] = None
    scored = grounding.summary(rows)
    arm = rows[0]["arm"]
    assert scored["groups"]["all"][arm]["parsed"]["denominator"] == 6
    assert (
        scored["paired_draft_match"]["unparsed_pair"]
        == original["paired_draft_match"]["unparsed_pair"] + 1
    )
    assert (
        scored["changed_choice_among_parsed_pairs"]["denominator"]
        == original["changed_choice_among_parsed_pairs"]["denominator"] - 1
    )
