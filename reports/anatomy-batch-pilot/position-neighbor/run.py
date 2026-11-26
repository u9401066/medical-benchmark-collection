"""Run or replay the fixed target-position and neighbor crossover on MMLU anatomy."""

import argparse
import asyncio
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import random
import sys

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from medbench import batch_probe as probe  # noqa: E402


SOURCE_SHA = "208f9eb5252cceef95ab71e7ff17dd530ad9820167078b7483cb6447c6eb8ca8"
PLAN_SEED = 2026112606
PARAMETERS = {
    "model": "qwen2.5-1.5b-local",
    "temperature": 0,
    "seed": 20261126,
    "max_tokens": 128,
    "response_format": {"type": "json_object"},
    "stream": False,
}
ARMS = ("single", "single_repeat", "first_a", "second_a", "first_b", "second_b")
PRIMARY = [
    ("single", "single_repeat"),
    ("first_a", "second_a"),
    ("first_b", "second_b"),
    ("first_a", "first_b"),
    ("second_a", "second_b"),
]


def load_items(path):
    data = path.read_bytes()
    if probe.digest(data) != SOURCE_SHA:
        raise ValueError("Expected the full normalized anatomy test split")
    return {
        x["id"]: x
        for x in (
            json.loads(line, object_pairs_hook=probe.unique_keys)
            for line in data.splitlines()
        )
    }


def assignment(items):
    rng = random.Random(PLAN_SEED)
    keys = rng.sample(list(items), 12)
    targets, partners = keys[:6], keys[6:]
    if len(set(keys)) != 12:
        raise ValueError("Need 12 distinct cases")
    arms = list(ARMS)
    rng.shuffle(arms)
    rounds = []
    # A balanced Latin square gives each target each arm once and each round all six arms.
    for round_no, shift in enumerate((0, 1, 5, 2, 4, 3), 1):
        jobs = []
        for i, target in enumerate(targets):
            arm = arms[(i + shift) % 6]
            ids = [target]
            if arm not in ("single", "single_repeat"):
                position, partner = arm.split("_")
                neighbor = partners[i] if partner == "a" else partners[(i + 1) % 6]
                ids = [target, neighbor] if position == "first" else [neighbor, target]
            jobs.append({"round": round_no, "arm": arm, "target": target, "ids": ids})
        rng.shuffle(jobs)
        rounds.extend(jobs)
    return targets, rounds


def summarize(answers, gold):
    arms = {}
    for arm, values in answers.items():
        missing = [k for k in gold if values[k] is None]
        arms[arm] = {
            "assigned": len(gold),
            "parsed": len(gold) - len(missing),
            "correct_source_key": sum(values[k] == gold[k] for k in gold),
            "missing_ids": missing,
        }
    pairs = {}
    for first, second in [*PRIMARY, *(("single", arm) for arm in ARMS[2:])]:
        a, b = answers[first], answers[second]
        stats = probe.paired(a, b, gold)
        stats["wrong_to_wrong"] = (
            stats["flips"] - stats["correct_to_wrong"] - stats["wrong_to_correct"]
        )
        stats["missing_left_only"] = [
            k for k in gold if a[k] is None and b[k] is not None
        ]
        stats["missing_right_only"] = [
            k for k in gold if b[k] is None and a[k] is not None
        ]
        stats["missing_both"] = [k for k in gold if a[k] is None and b[k] is None]
        pairs[f"{first}_vs_{second}"] = stats
    return {"arms": arms, "comparisons": pairs}


def same(actual, expected, label):
    if json.dumps(actual, sort_keys=True, allow_nan=False) != json.dumps(
        expected, sort_keys=True, allow_nan=False
    ):
        raise ValueError(f"Mismatch in {label}")


def replay(items, report):
    targets, plan = assignment(items)
    gold = {k: items[k]["answer"] for k in targets}
    same(report["source_sha256"], SOURCE_SHA, "source")
    same(report["plan_seed"], PLAN_SEED, "plan seed")
    same(report["parameters"], PARAMETERS, "request protocol")
    same(report["target_gold"], gold, "target reference labels")
    same(len(report["calls"]), len(plan), "request count")
    answers = {arm: {} for arm in ARMS}
    for job, call in zip(plan, report["calls"], strict=True):
        for k, value in job.items():
            same(call[k], value, f"assignment {k}")
        group = [items[k] for k in job["ids"]]
        same(call["max_tokens"], PARAMETERS["max_tokens"], "token limit")
        same(
            call["prompt_sha256"], probe.digest(probe.prompt(group).encode()), "prompt"
        )
        raw = call["raw"]
        if raw is None:
            pred = dict.fromkeys(job["ids"])
            if (
                "response_sha256" in call
                or "finish_reason" in call
                or call["usage"] != {}
                or len(call["errors"]) != 1
                or not call["errors"][0]
            ):
                raise ValueError("Inconsistent failed request")
        else:
            same(call["response_sha256"], probe.digest(raw.encode()), "response")
            for token_type in ("prompt_tokens", "completion_tokens"):
                tokens = call["usage"][token_type]
                if tokens is not None and (type(tokens) is not int or tokens < 0):
                    raise ValueError("Invalid recorded token count")
            pred, errors = probe.parse_batch(raw, group)
            if call["finish_reason"] == "length":
                errors.append("truncated")
            same(call["errors"], errors, "protocol errors")
        same(call["predictions"], pred, "parsed labels")
        if not math.isfinite(call["latency_s"]) or call["latency_s"] < 0:
            raise ValueError("Invalid recorded request time")
        answers[job["arm"]][job["target"]] = pred[job["target"]]
    return summarize(answers, gold)


async def run(items, url):
    targets, plan = assignment(items)
    report = {
        "started_utc": datetime.now(timezone.utc).isoformat(),
        "source_sha256": SOURCE_SHA,
        "plan_seed": PLAN_SEED,
        "parameters": PARAMETERS,
        "target_gold": {k: items[k]["answer"] for k in targets},
        "calls": [],
    }
    async with httpx.AsyncClient(
        base_url=url.rstrip("/"), timeout=120, trust_env=False
    ) as client:
        for job in plan:
            group = [items[k] for k in job["ids"]]
            # ask() multiplies the per-item budget by the number of questions.
            call, raw = await probe.ask(
                client,
                PARAMETERS["model"],
                group,
                PARAMETERS["seed"],
                PARAMETERS["max_tokens"] // len(group),
            )
            report["calls"].append({**job, **call, "raw": raw})
            print(f"{len(report['calls']):02d}/{len(plan)} {job['arm']}", flush=True)
    report["summary"] = replay(items, report)
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--items", required=True, type=Path)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--run", type=Path, help="New result file")
    mode.add_argument("--verify", type=Path, help="Replay a result offline")
    parser.add_argument("--url", default="http://127.0.0.1:18139")
    args = parser.parse_args(argv)
    items = load_items(args.items)
    if args.verify:
        report = json.loads(
            args.verify.read_bytes(), object_pairs_hook=probe.unique_keys
        )
        same(report["summary"], replay(items, report), "summary")
        print(
            f"Verified {len(report['calls'])} requests, {len(report['target_gold'])} targets."
        )
    else:
        if args.run.exists():
            parser.error("Choose a new output path")
        report = asyncio.run(run(items, args.url))
        args.run.parent.mkdir(parents=True, exist_ok=True)
        with args.run.open("xb") as stream:
            stream.write(
                (json.dumps(report, ensure_ascii=False, indent=2) + "\n").encode()
            )


if __name__ == "__main__":
    main()
