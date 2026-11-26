"""Compare single, concurrent and shared-context MCQ requests on one fixed assignment."""

import argparse
import asyncio
import hashlib
import json
import math
import random
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import httpx

from .json_io import unique_keys
from .moex_archive import atomic


def digest(value):
    return hashlib.sha256(value).hexdigest()


def make_plan(items, sample, size, concurrency, seed):
    if size < 2 or sample < 2 * size or sample % size or concurrency < 1:
        raise ValueError(
            "Use at least two full groups, a group size of at least two and positive concurrency"
        )
    ids = [item["id"] for item in items]
    if len(set(ids)) != len(ids) or len(items) < sample:
        raise ValueError("Need enough items with distinct IDs for the requested sample")
    rng = random.Random(seed)
    selected = rng.sample(ids, sample)
    singles = [[key] for key in selected]
    rotated = selected[1:] + selected[:1]
    conditions = [
        ("single", 1, singles),
        ("single_repeat", 1, singles),
        ("independent", concurrency, singles),
        ("shared", 1, [selected[i : i + size] for i in range(0, sample, size)]),
        ("shared_rotated", 1, [rotated[i : i + size] for i in range(0, sample, size)]),
    ]
    rng.shuffle(conditions)
    return selected, conditions


def prompt(items):
    # Only fields available to an examinee go over the wire.
    questions = [
        {"id": x["id"], "question": x["question"], "options": x["options"]}
        for x in items
    ]
    return (
        "For each medical multiple-choice question, select one of its offered labels. "
        'Reply only with a JSON object of the form {"answers":[{"id":"question ID","answer":"label"}]}. '
        "Include each given ID exactly once.\n"
        + json.dumps(questions, ensure_ascii=False)
    )


def parse_batch(content, items):
    offered = {x["id"]: x["options"] for x in items}
    parsed = dict.fromkeys(offered)
    errors = []
    try:
        obj = json.loads(content, object_pairs_hook=unique_keys)
        if not isinstance(obj, dict) or not isinstance(obj.get("answers"), list):
            raise ValueError("Expected an answers array")
    except (TypeError, ValueError):
        return parsed, ["invalid_json_or_schema"]
    seen = set()
    for row in obj["answers"]:
        if not isinstance(row, dict) or not isinstance(row.get("id"), str):
            errors.append("invalid_record")
            continue
        key = row["id"]
        if key not in offered:
            errors.append("unknown_id")
            continue
        if key in seen:
            parsed[key] = None
            errors.append("duplicate_id")
            continue
        seen.add(key)
        label = row.get("answer")
        if isinstance(label, str) and label in offered[key]:
            parsed[key] = label
        else:
            errors.append("invalid_label")
    errors.extend("missing_id" for _ in offered.keys() - seen)
    return parsed, errors


async def ask(client, model, items, seed, per_item_tokens):
    message = prompt(items)
    body = {
        "model": model,
        "messages": [{"role": "user", "content": message}],
        "temperature": 0,
        "seed": seed,
        "max_tokens": len(items) * per_item_tokens,
        "response_format": {"type": "json_object"},
        "stream": False,
    }
    row = {
        "ids": [x["id"] for x in items],
        "prompt_sha256": digest(message.encode()),
        "max_tokens": body["max_tokens"],
    }
    start = time.perf_counter()
    try:
        response = await client.post("/v1/chat/completions", json=body)
        row["latency_s"] = time.perf_counter() - start
        response.raise_for_status()
        data = response.json()
        choice = data["choices"][0]
        content = choice["message"]["content"]
        if not isinstance(content, str):
            raise ValueError("Expected text content")
        pred, errors = parse_batch(content, items)
        finish = choice.get("finish_reason")
        if finish == "length":
            errors.append("truncated")
        usage = data.get("usage")
        row.update(
            response_sha256=digest(content.encode()),
            finish_reason=finish,
            predictions=pred,
            errors=errors,
            usage={
                k: usage.get(k) if isinstance(usage, dict) else None
                for k in ("prompt_tokens", "completion_tokens")
            },
        )
        return row, content
    except (httpx.HTTPError, ValueError, KeyError, TypeError, IndexError) as exc:
        row.setdefault("latency_s", time.perf_counter() - start)
        row.update(
            predictions=dict.fromkeys(row["ids"]), errors=[type(exc).__name__], usage={}
        )
        return row, None


def summarize(calls, elapsed, gold):
    predictions = {k: v for call in calls for k, v in call["predictions"].items()}
    if predictions.keys() != gold.keys() or sum(len(c["ids"]) for c in calls) != len(
        gold
    ):
        raise ValueError("The condition did not cover the assignment exactly once")
    valid = sum(p is not None for p in predictions.values())
    correct = sum(p == gold[k] for k, p in predictions.items())
    latency = sorted(c["latency_s"] for c in calls)
    summary = {
        "assigned": len(gold),
        "requests": len(calls),
        "parsed": valid,
        "correct_source_key": correct,
        "wall_s": elapsed,
        "parsed_per_hour": 3600 * valid / elapsed,
        "correct_per_hour": 3600 * correct / elapsed,
        "p95_request_s": latency[math.ceil(0.95 * len(latency)) - 1],
        "protocol_events": dict(Counter(e for c in calls for e in c["errors"])),
    }
    for key in ("prompt_tokens", "completion_tokens"):
        counts = [c["usage"].get(key) for c in calls]
        summary[key] = sum(counts) if all(isinstance(n, int) for n in counts) else None
    return predictions, summary


def paired(base, other, gold):
    pairs = [k for k in gold if base[k] is not None and other[k] is not None]
    flips = [k for k in pairs if base[k] != other[k]]
    return {
        "assigned": len(gold),
        "both_parsed": len(pairs),
        "flips": len(flips),
        "flipped_ids": flips,
        "correct_to_wrong": sum(base[k] == gold[k] for k in flips),
        "wrong_to_correct": sum(other[k] == gold[k] for k in flips),
    }


async def run(args):
    raw_items = args.items.read_bytes()
    pool = [json.loads(line) for line in raw_items.splitlines() if line.strip()]
    pool = [
        x
        for x in pool
        if x["kind"] == "mcq"
        and (args.subject is None or x.get("meta", {}).get("subject") == args.subject)
    ]
    selected, conditions = make_plan(
        pool, args.sample, args.pack_size, args.concurrency, args.seed
    )
    items = {x["id"]: x for x in pool}
    gold = {key: items[key]["answer"] for key in selected}
    if any(label not in items[k]["options"] for k, label in gold.items()):
        raise ValueError("A reference label is absent from its question")
    report = {
        "prompt_version": "batch-mcq-v1",
        "started_utc": datetime.now(timezone.utc).isoformat(),
        "model": args.model,
        "items_sha256": digest(raw_items),
        "eligible": len(pool),
        "subject": args.subject,
        "seed": args.seed,
        "temperature": 0,
        "tokens_per_item": args.tokens_per_item,
        "response_format": "json_object",
        "gold": gold,
        "conditions": {},
        "paired_vs_single": {},
    }
    raw, answers = {}, {}
    async with httpx.AsyncClient(
        base_url=args.url.rstrip("/"), timeout=args.timeout, trust_env=False
    ) as client:
        warm = {
            "id": "warmup",
            "question": "Which number is larger?",
            "options": {"A": "3", "B": "4"},
        }
        warm_call, _ = await ask(
            client, args.model, [warm], args.seed, args.tokens_per_item
        )
        if "response_sha256" not in warm_call:
            raise RuntimeError(f"Warm-up request failed: {warm_call['errors']}")
        report["warmup_excluded"] = warm_call
        for name, concurrency, groups in conditions:
            sem = asyncio.Semaphore(concurrency)

            async def one(group):
                async with sem:
                    return await ask(
                        client,
                        args.model,
                        [items[k] for k in group],
                        args.seed,
                        args.tokens_per_item,
                    )

            start = time.perf_counter()
            results = await asyncio.gather(*(one(group) for group in groups))
            elapsed = time.perf_counter() - start
            calls = [row for row, _ in results]
            raw[name] = [content for _, content in results]
            answers[name], summary = summarize(calls, elapsed, gold)
            report["conditions"][name] = {
                "client_concurrency": concurrency,
                "summary": summary,
                "calls": calls,
            }
            print(
                f"{name}: {summary['parsed']}/{len(gold)} parsed, {elapsed:.2f}s",
                flush=True,
            )
    report["paired_vs_single"] = {
        name: paired(answers["single"], pred, gold)
        for name, pred in answers.items()
        if name != "single"
    }
    if args.raw:
        atomic(
            args.raw, (json.dumps(raw, ensure_ascii=False, indent=2) + "\n").encode()
        )
    atomic(args.out, (json.dumps(report, ensure_ascii=False, indent=2) + "\n").encode())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--items", type=Path, required=True, help="Normalized MCQ JSONL"
    )
    parser.add_argument(
        "--subject", help="Optional meta.subject filter before sampling"
    )
    parser.add_argument("--url", required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--sample", type=int, default=12)
    parser.add_argument("--pack-size", type=int, default=2)
    parser.add_argument("--concurrency", type=int, default=2)
    parser.add_argument("--seed", type=int, default=20261126)
    parser.add_argument("--tokens-per-item", type=int, default=64)
    parser.add_argument("--timeout", type=float, default=120)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument(
        "--raw", type=Path, help="Optional local archive of unparsed model responses"
    )
    args = parser.parse_args()
    paths = [p.resolve() for p in (args.items, args.out, args.raw) if p is not None]
    if len(set(paths)) != len(paths) or args.tokens_per_item < 1 or args.timeout <= 0:
        parser.error(
            "Choose distinct file paths, a positive token budget and a positive timeout"
        )
    asyncio.run(run(args))


if __name__ == "__main__":
    main()
