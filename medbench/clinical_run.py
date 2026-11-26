"""Run one request per question from a frozen, approved clinical assignment."""

from __future__ import annotations

import argparse
import asyncio
from collections import Counter, defaultdict
from datetime import date, datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import time

import httpx

from .clinical_score import indexed, read_jsonl, validate_gold
from .curation import has_text
from .json_io import unique_keys, write_new
from .runner import item_seed, stream_completion


PROTOCOL = "clinical-independent-v1"
KINDS = (
    "select",
    "free_text",
    "no_valid_option",
    "insufficient_information",
    "abstain",
)
TECHNICAL = {"timeout", "parse_error", "request_error"}
RULES = {
    "zh-TW": (
        "請輸出一個 JSON 物件，包含 response_type、selected_options、reason。"
        "選擇題依題意作答，response_type 填 select，selected_options 填選項代號陣列。"
        "自由作答用 free_text。選項均不適用用 no_valid_option，題目缺少必要資訊用 "
        "insufficient_information，其他無法作答的情形用 abstain。"
        "這四類的 selected_options 填空陣列。reason 用臺灣繁體中文寫答案或理由。"
    ),
    "en-US": (
        "Return one JSON object with response_type, selected_options, and reason. "
        "For a choice, use select and list the labels required by the question in selected_options. "
        "Use free_text for an open response, no_valid_option if none of the listed choices apply, "
        "insufficient_information if a necessary fact is missing, or abstain if unable to answer for another reason. "
        "For these four types, use an empty selected_options array. Put your answer or rationale in reason in American English."
    ),
}
FORMAT = {
    "schema": {
        "type": "json_schema",
        "json_schema": {
            "name": "clinical_response",
            "strict": True,
            "schema": {
                "type": "object",
                "required": ["response_type", "selected_options", "reason"],
                "additionalProperties": False,
                "properties": {
                    "response_type": {"type": "string", "enum": list(KINDS)},
                    "selected_options": {"type": "array", "items": {"type": "string"}},
                    "reason": {"type": "string"},
                },
            },
        },
    },
    "json": {"type": "json_object"},
}


def payload(obj):
    return (
        json.dumps(obj, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
        + "\n"
    ).encode("utf-8")


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def read_json(path):
    return json.loads(path.read_bytes(), object_pairs_hook=unique_keys)


def assignment(path, expected):
    raw = path.read_bytes()
    fingerprint = sha(raw)
    if fingerprint != expected.lower():
        raise ValueError("The assignment does not match the frozen SHA-256")
    rows = list(indexed(read_jsonl(path, raw), "clinical assignment").values())
    if not rows:
        raise ValueError("The frozen assignment has no approved questions")
    if len({(r["split"], r["export_as_of"]) for r in rows}) != 1:
        raise ValueError("Use a single export date and split in the assignment")
    for item in rows:
        validate_gold(item, date.today())
        if (
            item.get("rights_status") != "cleared"
            or "offered_option_labels" not in item
        ):
            raise ValueError(
                f"{item['id']}: prepare a current export with uses and offered labels documented"
            )
        if item["lang"] not in RULES:
            raise ValueError(f"{item['id']}: unsupported answer language")
        messages = item.get("messages")
        if not (
            isinstance(messages, list)
            and messages
            and isinstance(messages[0], dict)
            and messages[0].get("role") == "user"
            and has_text(messages[0].get("content"))
            and all(
                isinstance(m, dict) and m.get("role") == "assistant"
                for m in messages[1:]
            )
        ):
            raise ValueError(
                f"{item['id']}: the assignment must begin with a single examinee-visible question"
            )
    return rows, fingerprint


def request_body(item, config):
    context = (
        f"適用地區：{item['jurisdiction']}。證據截止日：{item['clinical_as_of']}。"
        if item["lang"] == "zh-TW"
        else f"Jurisdiction: {item['jurisdiction']}. Clinical evidence cutoff: {item['clinical_as_of']}."
    )
    question = item["messages"][0]["content"]
    body = {
        "model": config["model"],
        "messages": [
            {
                "role": "user",
                "content": "\n\n".join((question, context, RULES[item["lang"]])),
            }
        ],
        "seed": item_seed(item["id"]),
        "temperature": 0,
        "max_tokens": config["max_tokens"],
        "stream": True,
        "stream_options": {"include_usage": True},
    }
    if config["format"] in FORMAT:
        body["response_format"] = FORMAT[config["format"]]
    return body


def prediction(item, record):
    result = {"id": item["id"], "content_sha256": item["content_sha256"]}
    if record["failure"] is not None:
        if record["failure"] not in {"timeout", "request_error"}:
            raise ValueError(f"{item['id']}: unsupported request failure")
        return {**result, "response_type": record["failure"]}
    text = record["completion"]["content"]
    parsed = None
    if record["completion"]["rec"]["finish_reason"] == "stop":
        try:
            parsed = json.loads(text, object_pairs_hook=unique_keys)
        except ValueError:
            pass
    error = {**result, "text": text, "response_type": "parse_error"}
    if not isinstance(parsed, dict) or parsed.keys() != {
        "response_type",
        "selected_options",
        "reason",
    }:
        return error
    response_type, labels = parsed["response_type"], parsed["selected_options"]
    if (
        response_type not in KINDS
        or not has_text(parsed["reason"])
        or not isinstance(labels, list)
        or not all(isinstance(label, str) for label in labels)
        or (response_type != "select" and labels)
    ):
        return error
    valid = {**result, "text": text, "response_type": response_type}
    if response_type == "select":
        valid["selected_options"] = labels
    return valid


def attempts_from_disk(folder, rows, request_hashes):
    attempts = defaultdict(dict)
    by_id = {item["id"]: (i, item) for i, item in enumerate(rows, 1)}
    for path in (folder / "attempts").glob("*.json"):
        record = read_json(path)
        key, attempt = record["id"], record["attempt"]
        if key not in by_id or type(attempt) is not int or attempt < 1:
            raise ValueError(
                f"{path.name}: attempt is not part of the frozen assignment"
            )
        index, item = by_id[key]
        if (
            path.name != attempt_name(index, attempt)
            or attempt in attempts[key]
            or record["request_sha256"] != request_hashes[index - 1]
            or record["content_sha256"] != item["content_sha256"]
        ):
            raise ValueError(
                f"{path.name}: attempt differs from its frozen question or request"
            )
        attempts[key][attempt] = prediction(item, record)
    for key, history in attempts.items():
        if sorted(history) != list(range(1, len(history) + 1)):
            raise ValueError(f"{key}: attempt history has a gap")
    return attempts


def attempt_name(index, attempt):
    return f"{index:08d}.{attempt:06d}.json"


def new_manifest(rows, fingerprint, config):
    bodies = [request_body(item, config) for item in rows]
    return {
        "protocol": PROTOCOL,
        "gold_sha256": fingerprint,
        "assigned": len(rows),
        "split": rows[0]["split"],
        "export_as_of": rows[0]["export_as_of"],
        "config": config,
        "request_sha256": [sha(payload(body)) for body in bodies],
    }, bodies


def open_manifest(folder, rows, fingerprint, config=None):
    path = folder / "manifest.json"
    if path.is_file():
        saved = read_json(path)
        expected, bodies = new_manifest(
            rows, fingerprint, saved["config"] if config is None else config
        )
        if saved != expected:
            raise ValueError(
                "Run manifest differs from the assignment, model configuration or request protocol"
            )
    elif config is not None:
        if folder.exists() and any(folder.iterdir()):
            raise ValueError("Choose an empty directory for a new clinical run")
        expected, bodies = new_manifest(rows, fingerprint, config)
        write_new(path, payload(expected))
    else:
        raise ValueError("Run directory has no manifest")
    return expected, bodies


async def attempt(client, item, body, number, prompt_hash, deadline_s):
    attempt_started = datetime.now(timezone.utc).isoformat()
    start = time.perf_counter()
    completion = failure = detail = None
    try:
        completion = await asyncio.wait_for(
            stream_completion(client, body), timeout=deadline_s
        )
    except (asyncio.TimeoutError, httpx.TimeoutException):
        failure = "timeout"
    except httpx.HTTPStatusError as error:
        failure, detail = "request_error", error.response.status_code
    except (
        httpx.RequestError,
        ValueError,
        RuntimeError,
        AttributeError,
        TypeError,
    ) as error:
        failure, detail = "request_error", type(error).__name__
    return {
        "id": item["id"],
        "content_sha256": item["content_sha256"],
        "attempt": number,
        "request_sha256": prompt_hash,
        "started_utc": attempt_started,
        "latency_s": round(time.perf_counter() - start, 6),
        "failure": failure,
        "failure_detail": detail,
        "completion": completion,
    }


async def run(folder, rows, fingerprint, config, client, retry_failed=False):
    manifest, bodies = open_manifest(folder, rows, fingerprint, config)
    hashes = manifest["request_sha256"]
    histories = attempts_from_disk(folder, rows, hashes)
    workers = asyncio.Semaphore(config["concurrency"])
    completed = Counter()
    started = time.perf_counter()

    async def run_one(i, item, body, request_hash, number):
        async with workers:
            record = await attempt(
                client, item, body, number, request_hash, config["timeout_s"]
            )
            observed = prediction(item, record)
            write_new(folder / "attempts" / attempt_name(i, number), payload(record))
            completed[observed["response_type"]] += 1

    jobs = []
    for i, (item, body, request_hash) in enumerate(
        zip(rows, bodies, hashes, strict=True), 1
    ):
        history = histories[item["id"]]
        previous = len(history)
        if previous == 0 or (
            retry_failed and history[previous]["response_type"] in TECHNICAL
        ):
            jobs.append(run_one(i, item, body, request_hash, previous + 1))
    await asyncio.gather(*jobs)
    elapsed = time.perf_counter() - started
    return {
        "assigned": len(rows),
        "attempted": len(jobs),
        "outcomes_this_session": dict(completed),
        "elapsed_s": elapsed,
        "requests_per_second": len(jobs) / elapsed if jobs else None,
    }


def export_predictions(folder, rows, fingerprint):
    manifest, _ = open_manifest(folder, rows, fingerprint)
    histories = attempts_from_disk(folder, rows, manifest["request_sha256"])
    return [
        histories[item["id"]][max(histories[item["id"]])]
        for item in rows
        if histories.get(item["id"])
    ]


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="action", required=True)
    for action in ("run", "predictions"):
        sub = subparsers.add_parser(action)
        sub.add_argument("--gold", type=Path, required=True)
        sub.add_argument("--expected-gold-sha256", required=True)
        sub.add_argument("--run-dir", type=Path, required=True)
        if action == "predictions":
            sub.add_argument("--out", type=Path)
        else:
            sub.add_argument("--url", default="http://127.0.0.1:8080")
            sub.add_argument("--model", required=True)
            sub.add_argument("--model-revision")
            sub.add_argument(
                "--api-key-env",
                help="Name of an environment variable with the bearer key",
            )
            sub.add_argument(
                "--format", choices=("schema", "json", "prompt"), default="schema"
            )
            sub.add_argument("--max-tokens", type=int, default=512)
            sub.add_argument("--concurrency", type=int, default=1)
            sub.add_argument(
                "--timeout-s",
                type=float,
                default=120,
                help="Per-request wall-time deadline",
            )
            sub.add_argument("--retry-failed", action="store_true")
    args = parser.parse_args(argv)
    try:
        rows, fingerprint = assignment(args.gold, args.expected_gold_sha256)
        if args.action == "predictions":
            data = b"".join(
                payload(row)
                for row in export_predictions(args.run_dir, rows, fingerprint)
            )
            if args.out:
                if args.out.resolve().is_relative_to(
                    (args.run_dir / "attempts").resolve()
                ):
                    raise ValueError(
                        "Keep prediction exports separate from the per-attempt journal"
                    )
                write_new(args.out, data)
            else:
                print(data.decode("utf-8"), end="")
            return
        url = httpx.URL(args.url)
        if (
            url.scheme not in {"http", "https"}
            or not url.host
            or url.userinfo
            or url.query
            or url.fragment
            or not has_text(args.model)
            or args.max_tokens < 1
            or args.concurrency < 1
            or not math.isfinite(args.timeout_s)
            or args.timeout_s <= 0
        ):
            raise ValueError(
                "Use an HTTP(S) base URL without credentials, positive limits and a model name"
            )
        headers = {}
        if args.api_key_env:
            key = os.environ.get(args.api_key_env)
            if not has_text(key):
                raise ValueError(
                    "The named bearer key environment variable is missing or empty"
                )
            headers["Authorization"] = "Bearer " + key
        config = {
            "url": str(url).rstrip("/"),
            "model": args.model,
            "model_revision": args.model_revision,
            "max_tokens": args.max_tokens,
            "concurrency": args.concurrency,
            "timeout_s": args.timeout_s,
            "format": args.format,
        }

        async def execute():
            async with httpx.AsyncClient(
                base_url=config["url"],
                timeout=args.timeout_s,
                headers=headers,
                trust_env=False,
            ) as client:
                return await run(
                    args.run_dir, rows, fingerprint, config, client, args.retry_failed
                )

        print(json.dumps(asyncio.run(execute()), ensure_ascii=False))
    except (KeyError, ValueError, TypeError, OSError, httpx.InvalidURL) as error:
        parser.exit(1, f"{error}\n")


if __name__ == "__main__":
    main()
