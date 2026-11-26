"""Paired closed-book and supplied-passage Taiwan FIT probe, current prompts only."""

import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import random
import socket
import subprocess
import sys
import time

import httpx

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import run as baseline  # noqa: E402

MODEL_ID = "qwen2.5-1.5b-local"
MODEL_SHA = "183715c435899236895da3869489cc30ac241476b4971a20285b1a462818a5b4"
SERVER_SHA = "57fc2f753ed915737508300de332ef6b038337fb828af8054d8f43c30f1580d1"
RUNTIME = {
    "server_build": "b12776",
    "server_sha256": SERVER_SHA,
    "model_sha256": MODEL_SHA,
    "quantization": "Q4_K_M",
    "ctx_size": 4096,
    "slots": 1,
    "threads": 4,
    "threads_batch": 4,
    "gpu_layers": 0,
}
ARMS = ("closed", "supplied")
ROOT = baseline.ROOT


def official_source():
    draft = json.loads((ROOT / "drafts/mbc-tw-fit-0002.json").read_bytes())
    (source,) = [s for s in draft["evidence"] if s["role"] == "current_program"]
    return {
        k: source[k]
        for k in (
            "url",
            "watch_xpath",
            "source_sha256",
            "passage_sha256",
            "retrieved_on",
        )
    }


def source_from_html(path):
    from lxml import html
    from medbench.evidence_watch import passage_hash

    evidence = official_source()
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != evidence["source_sha256"]:
        raise ValueError("Source snapshot bytes differ from the frozen draft")
    page = html.fromstring(raw.decode("utf-8-sig"))
    xpath = evidence["watch_xpath"]
    if passage_hash(page, xpath) != evidence["passage_sha256"]:
        raise ValueError("Unexpected official passage")
    return {**evidence, "text": " ".join(page.xpath(xpath)[0].text_content().split())}


def validate_source(source):
    if not isinstance(source, dict) or not isinstance(source.get("text"), str):
        raise ValueError("Missing official passage")
    if (
        source != {**official_source(), "text": source["text"]}
        or baseline.sha(source["text"]) != source["passage_sha256"]
    ):
        raise ValueError(
            "Source passage, locator or digest differs from the official evidence"
        )


def assignment(source):
    base = sorted(
        (m["id"], m, q, labels)
        for m, q, labels in baseline.assignment()
        if m["period"] == "current"
    )
    if len(base) != 6 or len({row[0] for row in base}) != 6:
        raise ValueError("Expected six distinct current FIT variants")
    rng = random.Random(baseline.SEED)
    rng.shuffle(base)
    first_arms = ["closed", "supplied"] * 3
    rng.shuffle(first_arms)
    result = []
    for (_, m, question, labels), first in zip(base, first_arms, strict=True):
        for arm in (first, next(a for a in ARMS if a != first)):
            message = question
            if arm == "supplied":
                message = (
                    "衛生福利部國民健康署 / Taiwan Health Promotion Administration\n"
                    + source["url"]
                    + "\n"
                    + source["text"]
                    + "\n\n"
                    + question
                )
            result.append(
                (
                    {**m, "arm": arm, "prompt_sha256": baseline.sha(message)},
                    message,
                    labels,
                )
            )
    return result


def choice_from(raw, finish, labels):
    choice = baseline.parse(raw, finish, labels)
    if choice is None:
        return None
    parsed = json.loads(raw, object_pairs_hook=baseline.unique_keys)
    return choice if set(parsed) == {"choice", "reason"} else None


def expected_choices():
    targets = {}
    for n in (1, 2, 3):
        for v in json.loads((ROOT / f"drafts/mbc-tw-fit-{n:04d}.json").read_bytes())[
            "variants"
        ]:
            update = v["clinical_update"]
            if update["outcome"] == "no_valid_option" and not update["valid_options"]:
                targets[v["id"]] = "no_valid_option"
            elif (
                update["outcome"] == "single_valid_option"
                and len(update["valid_options"]) == 1
            ):
                targets[v["id"]] = update["valid_options"][0]
            else:
                raise ValueError("Unexpected current draft target")
    return targets


def ratio(num, den):
    return {"numerator": num, "denominator": den}


def summary(rows):
    targets = expected_choices()
    pairs = {i: {} for i in targets}
    for r in rows:
        pairs[r["id"]][r["arm"]] = r["choice"]
    groups = {}
    for key, suffix in (
        ("all", None),
        ("no_valid_option", "0001"),
        ("revised_option", "0002"),
        ("stable_interval", "0003"),
    ):
        ids = [
            i
            for i in targets
            if suffix is None or i.startswith(f"mbc-tw-fit-{suffix}-")
        ]
        groups[key] = {
            a: {
                "parsed": ratio(sum(pairs[i][a] is not None for i in ids), len(ids)),
                "draft_match": ratio(
                    sum(pairs[i][a] == targets[i] for i in ids), len(ids)
                ),
            }
            for a in ARMS
        }
    transitions = {
        "both_match": 0,
        "only_closed_matches": 0,
        "only_supplied_matches": 0,
        "neither_matches": 0,
        "unparsed_pair": 0,
    }
    for i, pair in pairs.items():
        if None in pair.values():
            transitions["unparsed_pair"] += 1
        else:
            hit = tuple(pair[a] == targets[i] for a in ARMS)
            transitions[
                {
                    (True, True): "both_match",
                    (True, False): "only_closed_matches",
                    (False, True): "only_supplied_matches",
                    (False, False): "neither_matches",
                }[hit]
            ] += 1
    parsable = [p for p in pairs.values() if None not in p.values()]
    return {
        "case_families": 1,
        "language_variants": len(pairs),
        "requests": len(rows),
        "groups": groups,
        "paired_draft_match": transitions,
        "changed_choice_among_parsed_pairs": ratio(
            sum(p["closed"] != p["supplied"] for p in parsable), len(parsable)
        ),
    }


def verify(report):
    source = report["source"]
    validate_source(source)
    if json.dumps(report["runtime"], sort_keys=True) != json.dumps(
        RUNTIME, sort_keys=True
    ) or json.dumps(report["parameters"], sort_keys=True) != json.dumps(
        baseline.parameters_for(MODEL_ID, True), sort_keys=True
    ):
        raise ValueError("Unexpected runtime or inference parameters")
    expected = assignment(source)
    for (metadata, _, labels), r in zip(expected, report["responses"], strict=True):
        if any(r.get(k) != v for k, v in metadata.items()):
            raise ValueError("Wrong prompt, arm, period, draft or execution order")
        if (
            baseline.sha(r["raw"]) != r["response_sha256"]
            or choice_from(r["raw"], r["finish_reason"], labels) != r["choice"]
        ):
            raise ValueError("Response bytes or choice differ")
        usage = r["usage"]
        if (
            not isinstance(usage, dict)
            or not all(
                type(usage.get(k)) is int and usage[k] >= 0
                for k in ("prompt_tokens", "completion_tokens", "total_tokens")
            )
            or usage["prompt_tokens"] + usage["completion_tokens"]
            != usage["total_tokens"]
        ):
            raise ValueError("Inconsistent reported token counts")
    if report["summary"] != summary(report["responses"]):
        raise ValueError("Reported denominators or draft matches differ")


def fingerprint(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


@contextmanager
def local_server(server, model):
    if fingerprint(server) != SERVER_SHA or fingerprint(model) != MODEL_SHA:
        raise ValueError(
            "Expected original b12776 Windows CPU binary and Qwen2.5 Q4_K_M model"
        )
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    args = [
        str(server),
        "-m",
        str(model),
        "--alias",
        MODEL_ID,
        "--host",
        "127.0.0.1",
        "--port",
        str(port),
        "--ctx-size",
        "4096",
        "--parallel",
        "1",
        "--threads",
        "4",
        "--threads-batch",
        "4",
        "--n-gpu-layers",
        "0",
        "--no-webui",
    ]
    with subprocess.Popen(
        args,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    ) as proc:
        try:
            with httpx.Client(
                base_url=f"http://127.0.0.1:{port}", trust_env=False, timeout=120
            ) as client:
                for _ in range(120):
                    if proc.poll() is not None:
                        raise RuntimeError(f"Local server exited ({proc.returncode})")
                    try:
                        resp = client.get("/v1/models", timeout=2)
                        if resp.is_success and any(
                            x["id"] == MODEL_ID for x in resp.json()["data"]
                        ):
                            break
                    except httpx.TransportError:
                        pass
                    time.sleep(0.5)
                else:
                    raise RuntimeError("New loopback server did not become ready")
                yield client
        finally:
            if proc.poll() is None:
                proc.terminate()
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()


def main():
    p = argparse.ArgumentParser(description=__doc__)
    mode = p.add_mutually_exclusive_group(required=True)
    mode.add_argument("--verify", type=Path)
    mode.add_argument("--run", type=Path)
    source_input = p.add_mutually_exclusive_group()
    source_input.add_argument(
        "--html", type=Path, help="Original HTML snapshot from the dated draft"
    )
    source_input.add_argument(
        "--source-report",
        type=Path,
        help="Use only the pinned passage from a prior report",
    )
    p.add_argument(
        "--server",
        type=Path,
        default=ROOT / "data/batch-pilot/llama-b12776/llama-server.exe",
    )
    p.add_argument(
        "--model-file",
        type=Path,
        default=Path.home() / ".ollama/models/blobs" / ("sha256-" + MODEL_SHA),
    )
    args = p.parse_args()
    if args.verify:
        report = json.loads(
            args.verify.read_bytes(), object_pairs_hook=baseline.unique_keys
        )
        verify(report)
    else:
        if args.run.exists():
            p.error("Choose a new output path to preserve the recorded run")
        if args.source_report:
            source = json.loads(
                args.source_report.read_bytes(), object_pairs_hook=baseline.unique_keys
            )["source"]
            validate_source(source)
        else:
            source = source_from_html(
                args.html or ROOT / "data/temporal-sources/current.html"
            )
        report = {
            "started_utc": datetime.now(timezone.utc).isoformat(),
            "parameters": baseline.parameters_for(MODEL_ID, True),
            "runtime": RUNTIME,
            "source": source,
            "responses": [],
        }
        with local_server(args.server, args.model_file) as client:
            for m, msg, labels in assignment(source):
                res = client.post(
                    "/v1/chat/completions",
                    json={
                        **report["parameters"],
                        "messages": [{"role": "user", "content": msg}],
                    },
                )
                res.raise_for_status()
                obj = res.json()
                if obj["model"] != MODEL_ID:
                    raise ValueError("Server returned another model")
                item = obj["choices"][0]
                raw, finish = item["message"]["content"], item["finish_reason"]
                report["responses"].append(
                    {
                        **m,
                        "raw": raw,
                        "finish_reason": finish,
                        "response_sha256": baseline.sha(raw),
                        "choice": choice_from(raw, finish, labels),
                        "usage": obj["usage"],
                    }
                )
                print(f"{len(report['responses'])}/12 {m['id']} {m['arm']}", flush=True)
        report["finished_utc"] = datetime.now(timezone.utc).isoformat()
        report["summary"] = summary(report["responses"])
        verify(report)
        with args.run.open("x", encoding="utf8", newline="\n") as out:
            out.write(json.dumps(report, indent=2, ensure_ascii=False) + "\n")
    print(json.dumps(report["summary"], ensure_ascii=False))


if __name__ == "__main__":
    main()
