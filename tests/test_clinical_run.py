import asyncio
from collections import Counter
from datetime import date
import json

import httpx
import pytest

from medbench import clinical_run as run
from medbench.clinical_score import score
from test_clinical_score import gold


def example(key, **kwargs):
    item = gold(key, **kwargs)
    item["messages"] = [
        {
            "role": "user",
            "content": f"Fixture prompt {key} showing the question and its options",
        },
        {
            "role": "assistant",
            "content": "Private reference answer sent only to the grader",
        },
    ]
    return item


@pytest.fixture
def frozen(tmp_path):
    items = [
        example("single"),
        example(
            "all",
            outcome="multiple_valid_options",
            valid=("B", "D"),
            rule="all_required",
        ),
        example("none", outcome="no_valid_option", valid=()),
        example("open", outcome="free_text", valid=()),
        example("lost"),
    ]
    items[1]["lang"] = "en-US"
    source = tmp_path / "approved.jsonl"
    raw = b"".join(run.payload(row) for row in items)
    source.write_bytes(raw)
    return source, run.sha(raw), items


def event(content, finish=None):
    return {
        "choices": [{"delta": {"content": content}, "finish_reason": finish}],
        "usage": {"prompt_tokens": 30, "completion_tokens": 20},
    }


def stream(text, finish="stop"):
    raw = "".join(
        f"data: {json.dumps(part, ensure_ascii=False)}\n\n"
        for part in (event(text[:12]), event(text[12:], finish))
    )
    return httpx.Response(200, content=(raw + "data: [DONE]\n\n").encode("utf-8"))


def answer(kind, labels=()):
    return json.dumps(
        {
            "response_type": kind,
            "selected_options": list(labels),
            "reason": "原文，含空白與引用 [X]。",
        },
        ensure_ascii=False,
    )


def test_frozen_approved_assignment_rejects_empty_changed_legacy_and_pending(
    frozen, tmp_path
):
    source, sha, items = frozen
    assert run.assignment(source, sha.upper()) == (items, sha)
    with pytest.raises(ValueError, match="frozen SHA-256"):
        run.assignment(source, "0" * 64)
    for row, message in (
        ({**items[0], "decision": "pending"}, "approved"),
        (
            {
                k: v
                for k, v in items[0].items()
                if k not in {"rights_status", "source_rights", "offered_option_labels"}
            },
            "documented",
        ),
        (
            {**items[0], "messages": [{"role": "assistant", "content": "gold"}]},
            "examinee-visible",
        ),
        (None, "no approved"),
    ):
        test = tmp_path / "changed.jsonl"
        raw = b"" if row is None else run.payload(row)
        test.write_bytes(raw)
        with pytest.raises(ValueError, match=message):
            run.assignment(test, run.sha(raw))


def test_real_sse_parser_run_preserves_formats_and_retries_only_technical(
    frozen, tmp_path
):
    source, sha, _ = frozen
    rows, actual = run.assignment(source, sha)
    counts = Counter()

    def reply(request):
        assert request.url.path == "/v1/chat/completions"
        body = json.loads(request.content)
        assert body["seed"] >= 0 and body["stream"] is True
        assert body["response_format"]["type"] == "json_schema"
        assert len(body["messages"]) == 1
        ask = body["messages"][0]["content"]
        assert "2026-10-01" in ask
        assert not any(
            word in ask
            for word in (
                "Private reference",
                "example.org",
                "test clinician",
                "all_required",
            )
        )
        assert "valid_options" not in body
        selected = ask.split()[2]
        counts[selected] += 1
        if selected == "lost":
            raise httpx.ReadTimeout(
                "This transport detail must stay out of the journal", request=request
            )
        if selected == "none" and counts[selected] == 1:
            return httpx.Response(503, text="A private server error body")
        if selected == "open" and counts[selected] == 1:
            return stream('{"response_type":"free_text"', "length")
        return stream(
            {
                "single": answer("select", ["N"]),
                "all": answer("select", ["D", "B"]),
                "open": answer("free_text"),
                "none": answer("no_valid_option"),
            }[selected]
        )

    config = {
        "model": "fixture",
        "format": "schema",
        "max_tokens": 123,
        "concurrency": 2,
        "timeout_s": 10,
    }
    out = tmp_path / "run"

    async def reproduce():
        async with httpx.AsyncClient(
            base_url="http://test.invalid", transport=httpx.MockTransport(reply)
        ) as client:
            first = await run.run(out, rows, actual, config, client)
            assert first["attempted"] == 5
            first_rows = run.export_predictions(out, rows, actual)
            assert [row["response_type"] for row in first_rows] == [
                "select",
                "select",
                "request_error",
                "parse_error",
                "timeout",
            ]
            assert first_rows[3]["text"] == '{"response_type":"free_text"'
            assert not (await run.run(out, rows, actual, config, client))["attempted"]
            retry = await run.run(out, rows, actual, config, client, retry_failed=True)
            assert retry["attempted"] == 3
            with pytest.raises(ValueError, match="manifest differs"):
                await run.run(
                    out,
                    rows,
                    actual,
                    {**config, "model": "other"},
                    client,
                    retry_failed=True,
                )

    asyncio.run(reproduce())
    assert counts == {"single": 1, "all": 1, "none": 2, "open": 2, "lost": 2}
    rows_out = run.export_predictions(out, rows, actual)
    assert rows_out[1]["text"] == answer("select", ["D", "B"])
    result = score(rows, rows_out, score_as_of=date(2026, 11, 26))
    assert result["assigned"] == 5
    assert result["metrics"]["structured_target_match"]["numerator"] == 2
    assert result["metrics"]["structured_target_match"]["denominator"] == 4
    assert result["selection_counts"]["invalid"] == 1
    assert [r["id"] for r in rows_out] == [r["id"] for r in rows]
    attempt_files = list((out / "attempts").glob("*.json"))
    assert len(attempt_files) == 8
    assert all(b"private server error" not in p.read_bytes() for p in attempt_files)

    # Export follows the frozen assignment even when the caller used a different cwd.
    predictions = tmp_path / "predictions.jsonl"
    args = [
        "predictions",
        "--gold",
        str(source),
        "--expected-gold-sha256",
        actual,
        "--run-dir",
        str(out),
        "--out",
        str(predictions),
    ]
    run.main(args)
    assert predictions.read_bytes() == b"".join(run.payload(row) for row in rows_out)
    with pytest.raises(SystemExit):
        run.main(args)


@pytest.mark.parametrize(
    "text",
    [
        '{"response_type":"select","response_type":"abstain","selected_options":[],"reason":"Reason"}',
        '{"response_type":"no_valid_option","selected_options":["A"],"reason":"Reason"}',
        '{"response_type":"select","selected_options":["A"],"reason":" "}',
        '{"response_type":"select","selected_options":[1],"reason":"Reason"}',
    ],
)
def test_parser_does_not_repair_invalid_json_or_guess_a_choice(text):
    item = example("a")
    record = {
        "failure": None,
        "completion": {"content": text, "rec": {"finish_reason": "stop"}},
    }
    pred = run.prediction(item, record)
    assert pred["response_type"] == "parse_error" and pred["text"] == text


def test_deadline_applies_to_the_complete_request():
    async def stalled(_):
        await asyncio.Event().wait()

    async def limited_run():
        async with httpx.AsyncClient(
            base_url="http://test.invalid", transport=httpx.MockTransport(stalled)
        ) as client:
            return await run.attempt(client, example("a"), {}, 1, "fingerprint", 0.01)

    result = asyncio.run(limited_run())
    assert result["failure"] == "timeout" and result["completion"] is None
