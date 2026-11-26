import importlib.util
import json
from copy import deepcopy
from pathlib import Path
import sys

import httpx
import pytest


ROOT = Path(__file__).resolve().parents[1]
ENTRY = ROOT / "reports" / "tw-fit-date-probe" / "run.py"
SPEC = importlib.util.spec_from_file_location("fit_date_probe", ENTRY)
probe = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(probe)


@pytest.mark.parametrize("constrain", [False, True])
def test_model_receives_only_one_dates_question_and_options(
    monkeypatch, tmp_path, constrain
):
    expected = set()
    for n in (1, 2, 3):
        d = json.loads((ROOT / "drafts" / f"mbc-tw-fit-{n:04d}.json").read_bytes())
        for v in d["variants"]:
            options = "\n".join(f"{k}. {text}" for k, text in v["options"].items())
            for question in (v["question"], v["clinical_update"]["question"]):
                expected.add(
                    question + "\n" + options + "\n\n" + probe.SUFFIX[v["lang"]]
                )
    assert len(expected) == 12
    seen = []

    def respond(request):
        packet = json.loads(request.content)
        assert packet["response_format"] == (
            probe.CONSTRAINED_FORMAT if constrain else {"type": "json_object"}
        )
        assert (
            packet["temperature"],
            packet["seed"],
            packet["max_tokens"],
            packet["stream"],
        ) == (0, 20261126, 256, False)
        assert packet["messages"] == [
            {"role": "user", "content": packet["messages"][0]["content"]}
        ]
        assert set(packet) == {
            "messages",
            "model",
            "temperature",
            "seed",
            "max_tokens",
            "response_format",
            "stream",
        }
        seen.append(packet["messages"][0]["content"])
        assert seen[-1] in expected
        response = {"choice": "B", "reason": "This is an offline fixture."}
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "finish_reason": "stop",
                        "message": {"content": json.dumps(response)},
                    }
                ]
            },
        )

    client = httpx.Client
    monkeypatch.setattr(
        probe.httpx,
        "Client",
        lambda **kw: client(transport=httpx.MockTransport(respond), **kw),
    )
    out = tmp_path / "responses.json"
    mode = ["--constrain"] if constrain else []
    monkeypatch.setattr(sys, "argv", [str(ENTRY), "--run", str(out), *mode])
    probe.main()
    report = json.loads(out.read_bytes())
    assert len(seen) == len(set(seen)) == len(report["responses"]) == 12
    assert set(seen) == expected
    monkeypatch.setattr(sys, "argv", [str(ENTRY), "--verify", str(out), *mode])
    probe.main()
    with pytest.raises(ValueError, match="protocol"):
        probe.verify(report, constrain=not constrain)


def test_constraint_covers_every_response_class_and_declares_nonempty_reason(report):
    answer_format = deepcopy(probe.CONSTRAINED_FORMAT)
    assert (
        answer_format["type"] == "json_schema"
        and answer_format["json_schema"]["strict"] is True
    )
    schema = answer_format["json_schema"]["schema"]
    assert schema["additionalProperties"] is False and set(schema["required"]) == {
        "choice",
        "reason",
    }
    assert schema["properties"]["reason"] == {"type": "string", "minLength": 1}
    for _, _, options in probe.assignment():
        assert set(schema["properties"]["choice"]["enum"]) == set(options) | {
            "no_valid_option",
            "insufficient_information",
            "abstain",
        }
    report["parameters"]["response_format"] = answer_format
    probe.verify(report, constrain=True)
    schema["additionalProperties"] = True
    with pytest.raises(ValueError, match="protocol"):
        probe.verify(report, constrain=True)


@pytest.fixture
def report():
    rows = []
    for meta, _, _ in probe.assignment():
        raw = '{"choice": "B", "reason": "Fixture"}'
        rows.append(
            {
                **meta,
                "raw": raw,
                "response_sha256": probe.sha(raw),
                "finish_reason": "stop",
                "choice": "B",
                "usage": None,
            }
        )
    return {
        "started_utc": "2026-11-26T03:00:00+00:00",
        "parameters": {
            "model": "fixture",
            "temperature": 0,
            "seed": 20261126,
            "max_tokens": 256,
            "response_format": {"type": "json_object"},
            "stream": False,
        },
        "responses": rows,
    }


@pytest.mark.parametrize(
    "corruption",
    [
        "missing_row",
        "repeat_row",
        "changed_order",
        "prompt_sha256",
        "draft_sha256",
        "changed_raw",
        "changed_choice",
        "wrong_finish",
        "missing_parameters",
        "model",
        "temperature",
        "seed",
        "max_tokens",
        "response_format",
        "stream",
    ],
)
def test_replay_rejects_broken_report(report, corruption):
    rows = report["responses"]
    if corruption == "missing_row":
        rows.pop()
    elif corruption == "repeat_row":
        rows[1] = deepcopy(rows[0])
    elif corruption == "changed_order":
        rows.reverse()
    elif corruption in ("prompt_sha256", "draft_sha256"):
        rows[0][corruption] = "0" * 64
    elif corruption == "changed_raw":
        rows[0]["raw"] += " "
    elif corruption == "changed_choice":
        rows[0]["choice"] = "A"
    elif corruption == "wrong_finish":
        rows[0]["finish_reason"] = "length"
    elif corruption == "missing_parameters":
        del report["parameters"]
    else:
        wrong = {
            "model": " ",
            "temperature": 1,
            "seed": 1,
            "max_tokens": 32,
            "response_format": {"type": "text"},
            "stream": True,
        }
        report["parameters"][corruption] = wrong[corruption]
    with pytest.raises((ValueError, KeyError)):
        probe.verify(report)


@pytest.mark.parametrize(
    ("raw", "finish"),
    [
        ('{"choice":"B","reason":"an incomplete', "stop"),
        ('{"choice":"B","reason":"seems complete"}', "length"),
        ('{"choice":"B","choice":"A","reason":"contradiction"}', "stop"),
        ('{"choice":"B","reason":" "}', "stop"),
        ('{"choice":"invented","reason":"invalid label"}', "stop"),
    ],
)
def test_unparseable_call_stays_in_assignment_without_a_choice(
    report, capsys, raw, finish
):
    row = report["responses"][0]
    row.update(
        raw=raw, finish_reason=finish, response_sha256=probe.sha(raw), choice=None
    )
    probe.verify(report)
    assert "Assigned 12 parsed 11" in capsys.readouterr().out
    row["choice"] = "B"
    with pytest.raises(ValueError):
        probe.verify(report)


@pytest.mark.parametrize(
    "change",
    [
        "missing_language",
        "duplicate_language",
        "wrong_id",
        "no_comparison",
        "wrong_historical_date",
        "wrong_current_date",
        "wrong_jurisdiction",
    ],
)
def test_assignment_requires_complete_and_comparable_date_pairs(
    monkeypatch, tmp_path, change
):
    folder = tmp_path / "drafts"
    folder.mkdir()
    for original in (ROOT / "drafts").glob("mbc-tw-fit-*.json"):
        d = json.loads(original.read_bytes())
        if original.name == "mbc-tw-fit-0001.json":
            variants = d["variants"]
            if change == "missing_language":
                variants.pop()
            elif change == "duplicate_language":
                variants[1]["lang"] = variants[0]["lang"]
            elif change == "wrong_id":
                variants[1]["id"] = "unrelated-case-en-US"
            elif change == "no_comparison":
                variants[1]["historical_basis"].pop("comparison")
            elif change == "wrong_historical_date":
                variants[1]["historical_basis"]["as_of"] = "2025-12-31"
            elif change == "wrong_current_date":
                variants[1]["clinical_update"]["as_of"] = "2027-11-26"
            else:
                variants[1]["clinical_update"]["jurisdiction"] = "US"
        (folder / original.name).write_bytes(json.dumps(d).encode())
    monkeypatch.setattr(probe, "ROOT", tmp_path)
    with pytest.raises((ValueError, KeyError)):
        probe.assignment()
