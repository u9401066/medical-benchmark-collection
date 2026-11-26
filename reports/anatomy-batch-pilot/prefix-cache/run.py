"""Measure cold and warm token-prefix processing on a private, single-slot llama.cpp server."""

import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import socket
import statistics
import subprocess
import sys
import tempfile
import time

import httpx

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from medbench.json_io import unique_keys  # noqa: E402
from scripts.prefix_cache import context  # noqa: E402

MODEL_SHA = "183715c435899236895da3869489cc30ac241476b4971a20285b1a462818a5b4"
SOURCE_SHA = "208f9eb5252cceef95ab71e7ff17dd530ad9820167078b7483cb6447c6eb8ca8"
BUILD = "b12776-e38ea719b"
TARGETS = (
    "anatomy-test-047",
    "anatomy-test-050",
    "anatomy-test-074",
    "anatomy-test-104",
)
WORDS = {"short": 8, "long": 192}
ARMS = (("short", "cold"), ("long", "warm"), ("short", "warm"), ("long", "cold"))
PARAMS = {
    "id_slot": 0,
    "cache_prompt": True,
    "temperature": 0,
    "seed": 20261126,
    "n_predict": 16,
    "stream": False,
    "grammar": r'root ::= "{\"choice\":\"" [ABCD] "\"}"',
}
SERVER_ARGS = [
    "--alias",
    "qwen2.5-1.5b-local",
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
    "--cache-ram",
    "0",
    "--slots",
    "--no-webui",
]


def sha(value):
    return hashlib.sha256(value).hexdigest()


def encoded(value):
    return json.dumps(
        value,
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
        allow_nan=False,
    ).encode()


def check(value, expected, label):
    if encoded(value) != encoded(expected):
        raise ValueError(f"Mismatch in {label}")


def load_items(path):
    source = path.read_bytes()
    check(sha(source), SOURCE_SHA, "normalized anatomy test source")
    return {row["id"]: row for row in map(json.loads, source.splitlines())}


def messages(items, length, key):
    notes = context(WORDS[length], "fixed-anatomy")
    if key == "primer":
        user = "Calibration item. Which digit represents three? A. 1 B. 2 C. 3 D. 4"
    else:
        row = items[key]
        user = (
            row["question"]
            + "\n"
            + "\n".join(f"{k}. {v}" for k, v in row["options"].items())
        )
    return [
        {
            "role": "system",
            "content": "Select one offered letter. Here is a fixed benchmark header.\n"
            + notes,
        },
        {"role": "user", "content": user},
    ]


def plan():
    jobs = []
    for r in range(4):
        for step in range(4):
            i = (step + r) % 4
            length, state = ARMS[(i + r) % 4]
            jobs.append(
                {"round": r + 1, "id": TARGETS[i], "length": length, "state": state}
            )
    return jobs


@contextmanager
def owned_server(exe, model, port):
    with model.open("rb") as f:
        digest = hashlib.sha256()
        for chunk in iter(lambda: f.read(2_000_000), b""):
            digest.update(chunk)
    check(digest.hexdigest(), MODEL_SHA, "GGUF")
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", port))
    with (
        tempfile.TemporaryDirectory() as slots,
        tempfile.TemporaryFile() as log,
        httpx.Client(
            base_url=f"http://127.0.0.1:{port}", trust_env=False, timeout=120
        ) as client,
    ):
        cmd = [
            str(exe),
            "-m",
            str(model),
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
            *SERVER_ARGS,
            "--slot-save-path",
            slots,
        ]
        process = subprocess.Popen(
            cmd,
            stdout=log,
            stderr=subprocess.STDOUT,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        try:
            for _ in range(160):
                if process.poll() is not None:
                    log.seek(0)
                    raise RuntimeError(
                        "Private server exited: "
                        + log.read()[-1000:].decode(errors="replace")
                    )
                try:
                    if client.get("/health", timeout=2).status_code == 200:
                        break
                except httpx.TransportError:
                    pass
                time.sleep(0.25)
            else:
                raise RuntimeError("Private server failed to start")
            check(
                client.get("/props").raise_for_status().json()["build_info"],
                BUILD,
                "server build",
            )
            check(
                [x["id"] for x in client.get("/slots").raise_for_status().json()],
                [0],
                "private slot",
            )
            yield client
        finally:
            if process.poll() is None:
                process.terminate()
            process.wait(timeout=15)


def post(client, path, body):
    return client.post(path, json=body).raise_for_status().json()


def token_manifest(items, client):
    tokens, entries, overlaps = {}, {}, {}
    for length in WORDS:
        for key in ("primer", *TARGETS):
            name = length + "/" + key
            msg = messages(items, length, key)
            prompt = post(client, "/apply-template", {"messages": msg})["prompt"]
            ids = post(
                client,
                "/tokenize",
                {"content": prompt, "add_special": False, "parse_special": True},
            )["tokens"]
            tokens[name] = ids
            entries[name] = {
                "messages_sha256": sha(encoded(msg)),
                "template_sha256": sha(prompt.encode()),
                "tokens_sha256": sha(encoded(ids)),
                "n_tokens": len(ids),
            }
            if key != "primer":
                primer = tokens[length + "/primer"]
                n = next(i for i, (a, b) in enumerate(zip(primer, ids)) if a != b)
                overlaps[name] = {
                    "length": n,
                    "common_token_ids": ids[:n],
                    "primer_next": primer[n],
                    "target_next": ids[n],
                }
    return tokens, {"inputs": entries, "overlaps": overlaps}


def infer(client, tokens):
    start = time.perf_counter()
    response = post(client, "/completion", {**PARAMS, "prompt": tokens})
    wall_ms = (time.perf_counter() - start) * 1000
    row = {
        k: response[k]
        for k in (
            "id_slot",
            "timings",
            "content",
            "tokens_evaluated",
            "tokens_predicted",
            "tokens_cached",
            "stop_type",
            "truncated",
        )
    }
    return {**row, "content_sha256": sha(row["content"].encode()), "wall_ms": wall_ms}


def run(items, client):
    tokens, manifest = token_manifest(items, client)
    result = {
        "started_utc": datetime.now(timezone.utc).isoformat(),
        "source_sha256": SOURCE_SHA,
        "model_sha256": MODEL_SHA,
        "build": BUILD,
        "server_args": SERVER_ARGS,
        "params": PARAMS,
        "tokens": manifest,
        "trials": [],
    }
    for job in plan():
        length = job["length"]
        before = post(client, "/slots/0?action=erase", {})
        primer = infer(client, tokens[length + "/primer"])
        reset = (
            post(client, "/slots/0?action=erase", {})
            if job["state"] == "cold"
            else None
        )
        target = infer(client, tokens[length + "/" + job["id"]])
        result["trials"].append(
            {
                **job,
                "before_primer": before,
                "primer": primer,
                "before_target": reset,
                "target": target,
            }
        )
        t = target["timings"]
        print(
            job["id"],
            length,
            job["state"],
            t["cache_n"],
            t["prompt_n"],
            t["prompt_ms"],
            flush=True,
        )
    result["summary"] = replay(items, result)
    return result


def verify_call(row, n, max_cache):
    t = row["timings"]
    check(row["id_slot"], 0, "inference slot")
    check(row["truncated"], False, "context capacity")
    check(sha(row["content"].encode()), row["content_sha256"], "output digest")
    check(t["prompt_n"] + t["cache_n"], n, "prefill plus reused tokens")
    check(row["tokens_evaluated"], n, "server prompt length")
    check(t["predicted_n"], row["tokens_predicted"], "generated tokens")
    if not (
        type(t["cache_n"]) is int
        and 0 <= t["cache_n"] <= max_cache
        and type(t["prompt_n"]) is int
        and t["prompt_n"] > 0
        and type(t["predicted_n"]) is int
        and 0 < t["predicted_n"] <= PARAMS["n_predict"]
    ):
        raise ValueError("Invalid cache state or generation count")
    for value in (t["prompt_ms"], t["predicted_ms"], row["wall_ms"]):
        if type(value) not in (int, float) or not math.isfinite(value) or value < 0:
            raise ValueError("Invalid observed timing")


def replay(items, result):
    for k, value in (
        ("source_sha256", SOURCE_SHA),
        ("model_sha256", MODEL_SHA),
        ("build", BUILD),
        ("server_args", SERVER_ARGS),
        ("params", PARAMS),
    ):
        check(result[k], value, k)
    inputs, overlaps = (result["tokens"][k] for k in ("inputs", "overlaps"))
    expected = {length + "/" + k for length in WORDS for k in ("primer", *TARGETS)}
    check(sorted(inputs), sorted(expected), "prompt identities")
    check(
        sorted(overlaps),
        sorted(k for k in expected if not k.endswith("/primer")),
        "token overlaps",
    )
    for name, row in inputs.items():
        length, key = name.split("/")
        check(
            row["messages_sha256"],
            sha(encoded(messages(items, length, key))),
            "source messages",
        )
        if key != "primer":
            o = overlaps[name]
            if (
                o["length"] != len(o["common_token_ids"])
                or o["primer_next"] == o["target_next"]
                or not 0
                < o["length"]
                < min(row["n_tokens"], inputs[length + "/primer"]["n_tokens"])
            ):
                raise ValueError("Invalid token prefix boundary")
    by_arm = {(length, state): [] for length, state in ARMS}
    for job, trial in zip(plan(), result["trials"], strict=True):
        for k, v in job.items():
            check(trial[k], v, "trial order")
        length, state, key = trial["length"], trial["state"], trial["id"]
        for reset in (
            ["before_primer", "before_target"] if state == "cold" else ["before_primer"]
        ):
            erase = trial[reset]
            if (
                erase["id_slot"] != 0
                or type(erase["n_erased"]) is not int
                or erase["n_erased"] < 0
            ):
                raise ValueError("Missing slot erasure")
        if state == "warm":
            check(trial["before_target"], None, "warm-slot retention")
        verify_call(trial["primer"], inputs[length + "/primer"]["n_tokens"], 0)
        name = length + "/" + key
        verify_call(
            trial["target"],
            inputs[name]["n_tokens"],
            0 if state == "cold" else overlaps[name]["length"],
        )
        by_arm[length, state].append(trial["target"])
    summary = {}
    for (length, state), rows in by_arm.items():
        s = {
            k: statistics.median(r["timings"][k] for r in rows)
            for k in ("cache_n", "prompt_n", "prompt_ms", "predicted_n", "predicted_ms")
        }
        s.update(n=len(rows), wall_ms=statistics.median(r["wall_ms"] for r in rows))
        summary[length + "_" + state] = s
    return summary


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--items", required=True, type=Path)
    mode = p.add_mutually_exclusive_group(required=True)
    mode.add_argument("--run", type=Path, help="Write a new result file")
    mode.add_argument(
        "--verify", type=Path, help="Check frozen inputs, counts and arithmetic"
    )
    p.add_argument(
        "--verify-tokens",
        action="store_true",
        help="Also re-tokenize the verified report with the pinned model",
    )
    p.add_argument(
        "--server", type=Path, help="llama.cpp b12776 llama-server executable"
    )
    p.add_argument("--model", type=Path, help="Pinned Qwen2.5 1.5B Q4_K_M GGUF")
    p.add_argument("--port", type=int, default=18140)
    args = p.parse_args()
    if args.verify_tokens and not args.verify:
        p.error("--verify-tokens accompanies --verify")
    if (args.run or args.verify_tokens) and (not args.server or not args.model):
        p.error("Provide both the server executable and the GGUF")
    items = load_items(args.items)
    if args.verify:
        result = json.loads(args.verify.read_bytes(), object_pairs_hook=unique_keys)
        check(result["summary"], replay(items, result), "median summary")
        if args.verify_tokens:
            with owned_server(args.server, args.model, args.port) as client:
                _, manifest = token_manifest(items, client)
                check(result["tokens"], manifest, "exact tokenization")
        print("Verified", len(result["trials"]), "paired-primer trials")
    else:
        if args.run.exists():
            p.error("Choose a new output path")
        with owned_server(args.server, args.model, args.port) as client:
            result = run(items, client)
        args.run.parent.mkdir(parents=True, exist_ok=True)
        with args.run.open("xb") as f:
            f.write(
                (
                    json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False)
                    + "\n"
                ).encode()
            )


if __name__ == "__main__":
    main()
