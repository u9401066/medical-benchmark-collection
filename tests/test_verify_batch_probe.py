import argparse
import asyncio
import json

import httpx
import pytest

from medbench import batch_probe as probe
from scripts import verify_batch_probe as verifier


@pytest.fixture
def artifacts(monkeypatch, tmp_path):
    items, report, raw = (
        tmp_path / name for name in ("items.jsonl", "report.json", "raw.json")
    )
    pool = [
        {
            "id": f"q{i}",
            "kind": "mcq",
            "question": f"Question {i}?",
            "options": {"A": "First", "B": "Second"},
            "answer": "A",
            "meta": {"subject": "sample" if i < 5 else "other"},
        }
        for i in range(6)
    ]
    items.write_bytes("".join(json.dumps(x) + "\n" for x in pool).encode())
    first_packet = True

    def respond(request):
        nonlocal first_packet
        prompt = json.loads(request.content)["messages"][0]["content"]
        questions = json.loads(prompt.split("\n", 1)[1])
        if first_packet and questions[0]["id"] != "warmup":
            first_packet = False
            return httpx.Response(503)
        answers = [
            {"id": q["id"], "answer": "B: Second" if len(questions) > 1 else "A"}
            for q in questions
        ]
        choice = {
            "finish_reason": "stop",
            "message": {"content": json.dumps({"answers": answers})},
        }
        return httpx.Response(
            200,
            json={
                "choices": [choice],
                "usage": {"prompt_tokens": 70, "completion_tokens": 20},
            },
        )

    original_client = httpx.AsyncClient
    monkeypatch.setattr(
        probe.httpx,
        "AsyncClient",
        lambda **kw: original_client(transport=httpx.MockTransport(respond), **kw),
    )
    args = argparse.Namespace(
        items=items,
        out=report,
        raw=raw,
        url="https://mock.invalid",
        model="fixture",
        subject="sample",
        sample=4,
        pack_size=2,
        concurrency=2,
        seed=19,
        timeout=5,
        tokens_per_item=64,
    )
    asyncio.run(probe.run(args))
    return items, report, raw


def test_offline_replay_accepts_exact_artifacts_and_cli_fails_on_source_change(
    artifacts, capsys
):
    items, report, raw = artifacts
    argv = ["--items", str(items), "--report", str(report), "--raw", str(raw)]
    verifier.main(argv)
    output = capsys.readouterr().out
    assert "4 assigned / 5 eligible" in output and "Post-hoc" in output
    recovery = json.loads(output.split("strict_failed_but_exact_label_and_text:\n")[1])
    assert recovery["single"] == {"recovered": 0, "correct_source_key": 0}
    assert (
        recovery["shared"]["recovered"] >= 2
        and recovery["shared"]["correct_source_key"] == 0
    )
    items.write_bytes(items.read_bytes() + b"\n")
    with pytest.raises(SystemExit) as failure:
        verifier.main(argv)
    assert failure.value.code != 0


@pytest.mark.parametrize(
    ("which", "path", "change"),
    [
        ("report", ("eligible",), 6),
        ("report", ("gold",), "drop-one"),
        ("report", ("gold",), "wrong-label"),
        ("report", ("conditions", "single_repeat"), "delete"),
        ("raw", ("shared",), "delete"),
        ("report", ("conditions", "single", "calls"), "drop-one"),
        ("raw", ("shared_rotated",), "drop-one"),
        ("raw", ("single", 1), "{}"),
        ("report", ("conditions", "shared", "calls", 1, "ids"), "reverse"),
        ("report", ("conditions", "single", "calls", 1, "prompt_sha256"), "bad hash"),
        ("report", ("conditions", "single", "calls", 1, "response_sha256"), "bad hash"),
        ("report", ("conditions", "single", "calls", 1, "predictions"), {}),
        ("report", ("conditions", "shared", "calls", 1, "errors"), []),
        ("report", ("conditions", "single", "summary", "parsed_per_hour"), 0),
        ("report", ("conditions", "shared", "summary", "prompt_tokens"), 0),
        ("report", ("paired_vs_single", "shared_rotated", "flips"), 99),
    ],
)
def test_rejects_inconsistent_artifact(artifacts, which, path, change):
    source, report_path, raw_path = artifacts
    report, raw = (json.loads(p.read_bytes()) for p in (report_path, raw_path))
    parent = report if which == "report" else raw
    for part in path[:-1]:
        parent = parent[part]
    k = path[-1]
    if change == "delete":
        del parent[k]
    elif change == "drop-one":
        obj = parent[k]
        obj.pop(next(iter(obj)) if isinstance(obj, dict) else -1)
    elif change == "wrong-label":
        parent[k][next(iter(parent[k]))] = "B"
    elif change == "reverse":
        parent[k].reverse()
    else:
        parent[k] = change
    with pytest.raises((ValueError, KeyError)):
        verifier.verify(source.read_bytes(), report, raw)


def test_post_hoc_recovery_needs_unique_id_and_case_sensitive_full_label_and_text():
    ids = ["exact", "duplicate", "mismatch", "case", "partial", "strict", "absent"]
    items = [{"id": k, "options": {"A": "Oxygen", "B": "Venous pressure"}} for k in ids]
    rows = [
        ("exact", " B: Venous pressure "),
        ("duplicate", "A: Oxygen"),
        ("duplicate", "A: Oxygen"),
        ("mismatch", "B: Oxygen"),
        ("case", "A: oxygen"),
        ("partial", "B: Venous"),
        ("strict", "A"),
        ("unknown", "B: Venous pressure"),
    ]
    content = json.dumps({"answers": [{"id": k, "answer": v} for k, v in rows]})
    strict, _ = probe.parse_batch(content, items)
    assert verifier.exact_text_recoveries(content, items, strict) == {"exact": "B"}
    assert (
        verifier.exact_text_recoveries('{"answers": [], "answers": []}', items, strict)
        == {}
    )
