"""Offline replay of a batch-mcq-v1 report. Latency and token counts are reported inputs."""

import argparse
import json
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from medbench import batch_probe as probe  # noqa: E402


def check(actual, expected, field):
    if json.dumps(actual, sort_keys=True, allow_nan=False) != json.dumps(
        expected, sort_keys=True, allow_nan=False
    ):
        raise ValueError(f"Mismatch in {field}")


def exact_text_recoveries(content, items, strict):
    """Post-hoc only. Keep strict ID handling and require both label and verbatim option."""
    try:
        payload = json.loads(content, object_pairs_hook=probe.unique_keys)
    except ValueError:
        return {}
    if not isinstance(payload, dict) or not isinstance(payload.get("answers"), list):
        return {}
    options = {item["id"]: item["options"] for item in items}
    for row in payload["answers"]:
        if not isinstance(row, dict) or not isinstance(row.get("id"), str):
            continue
        key, answer = row["id"], row.get("answer")
        if key not in options or not isinstance(answer, str):
            continue
        label, separator, text = answer.strip().partition(":")
        label = label.strip()
        if (
            separator
            and label in options[key]
            and text.strip() == options[key][label].strip()
        ):
            row["answer"] = label
    relaxed, _ = probe.parse_batch(json.dumps(payload), items)
    return {k: v for k, v in relaxed.items() if strict[k] is None and v is not None}


def verify_call(call, content, items, budget, location):
    ids = [item["id"] for item in items]
    check(call["ids"], ids, f"{location} IDs")
    check(call["max_tokens"], len(ids) * budget, f"{location} token budget")
    check(
        call["prompt_sha256"],
        probe.digest(probe.prompt(items).encode()),
        f"{location} prompt",
    )
    if not math.isfinite(call["latency_s"]) or call["latency_s"] < 0:
        raise ValueError(f"Invalid latency at {location}")
    if content is None:
        check(call["predictions"], dict.fromkeys(ids), f"{location} failed predictions")
        check(call["usage"], {}, f"{location} failed usage")
        if (
            "response_sha256" in call
            or "finish_reason" in call
            or len(call["errors"]) != 1
            or not isinstance(call["errors"][0], str)
            or not call["errors"][0]
        ):
            raise ValueError(f"Inconsistent failed request at {location}")
        return {}
    check(
        call["response_sha256"],
        probe.digest(content.encode()),
        f"{location} raw response",
    )
    strict, errors = probe.parse_batch(content, items)
    if call["finish_reason"] == "length":
        errors.append("truncated")
    check(call["predictions"], strict, f"{location} predictions")
    check(call["errors"], errors, f"{location} protocol errors")
    for key in ("prompt_tokens", "completion_tokens"):
        tokens = call["usage"][key]
        if tokens is not None and (type(tokens) is not int or tokens < 0):
            raise ValueError(f"Invalid {key} at {location}")
    return exact_text_recoveries(content, items, strict)


def verify(source, report, raw):
    check(report["prompt_version"], "batch-mcq-v1", "prompt version")
    check(report["items_sha256"], probe.digest(source), "full split SHA-256")
    pool = [
        json.loads(line, object_pairs_hook=probe.unique_keys)
        for line in source.splitlines()
        if line.strip()
    ]
    subject = report["subject"]
    pool = [
        x
        for x in pool
        if x["kind"] == "mcq"
        and (subject is None or x.get("meta", {}).get("subject") == subject)
    ]
    check(report["eligible"], len(pool), "eligible denominator")
    conditions = report["conditions"]
    selected, plan = probe.make_plan(
        pool,
        len(report["gold"]),
        len(conditions["shared"]["calls"][0]["ids"]),
        conditions["independent"]["client_concurrency"],
        report["seed"],
    )
    by_id = {x["id"]: x for x in pool}
    gold = {k: by_id[k]["answer"] for k in selected}
    if any(label not in by_id[k]["options"] for k, label in gold.items()):
        raise ValueError("Invalid source answer")
    check(report["gold"], gold, "selected source keys")
    names = [name for name, _, _ in plan]
    check(list(conditions), names, "scheduled conditions")
    check(sorted(raw), sorted(names), "raw conditions")
    predictions, sensitivity = {}, {}
    for name, concurrency, groups in plan:
        condition = conditions[name]
        check(condition["client_concurrency"], concurrency, f"{name} concurrency")
        calls = condition["calls"]
        check(len(calls), len(groups), f"{name} requests")
        check(len(raw[name]), len(groups), f"{name} raw responses")
        recovered = {}
        for i, (ids, call, content) in enumerate(
            zip(groups, calls, raw[name], strict=True)
        ):
            recovered.update(
                verify_call(
                    call,
                    content,
                    [by_id[k] for k in ids],
                    report["tokens_per_item"],
                    f"{name}[{i}]",
                )
            )
        wall = condition["summary"]["wall_s"]
        if not math.isfinite(wall) or wall <= 0:
            raise ValueError(f"Invalid wall time at {name}")
        predictions[name], summary = probe.summarize(calls, wall, gold)
        check(condition["summary"], summary, f"{name} summary")
        sensitivity[name] = {
            "recovered": len(recovered),
            "correct_source_key": sum(v == gold[k] for k, v in recovered.items()),
        }
    paired = {
        name: probe.paired(predictions["single"], predictions[name], gold)
        for name in names
        if name != "single"
    }
    check(report["paired_vs_single"], paired, "paired comparisons")
    return sensitivity


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("items", "report", "raw"):
        parser.add_argument(f"--{name}", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        report, raw = (
            json.loads(p.read_bytes(), object_pairs_hook=probe.unique_keys)
            for p in (args.report, args.raw)
        )
        sensitivity = verify(args.items.read_bytes(), report, raw)
    except (
        OSError,
        ValueError,
        KeyError,
        TypeError,
        IndexError,
        AttributeError,
    ) as exc:
        parser.exit(1, f"Verification failed: {exc}\n")
    print(
        f"Verified {len(report['gold'])} assigned / {report['eligible']} eligible items across "
        f"{len(sensitivity)} measured conditions."
    )
    print("Post-hoc sensitivity only, strict_failed_but_exact_label_and_text:")
    print(json.dumps(sensitivity, indent=2))


if __name__ == "__main__":
    main()
