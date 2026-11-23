"""Serving-capacity sweep for an OpenAI-compatible server: per-request decode speed, aggregate throughput and time to first
token at several client concurrencies, plus prefill speed of a long prompt. Uses real benchmark questions, so speculative
decoding behaves as it does in use.

  python scripts/slot_sweep.py --url http://127.0.0.1:8081 --label bonsai --concurrency 1,2,4 --out results/slots/bonsai.json \
      --request '{"chat_template_kwargs":{"reasoning_effort":"medium"}}'
"""
from __future__ import annotations

import argparse
import asyncio
import json
import statistics
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, List

import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from medbench.datasets import load  # noqa: E402
from medbench.prompts import build_prompt  # noqa: E402


def gpu_mem_mib() -> float:
    out = subprocess.run(["nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader,nounits", "-i", "0"], capture_output=True,
                         text=True, timeout=5).stdout
    return float(out.strip() or 0)


async def one(client: httpx.AsyncClient, prompt: str, extra: Dict[str, Any], max_tokens: int) -> Dict[str, Any]:
    body = {"model": "m", "messages": [{"role": "user", "content": prompt}], "stream": True, "max_tokens": max_tokens,
            "stream_options": {"include_usage": True}, **extra}
    t0 = time.time()
    first = None
    usage: Dict[str, Any] = {}
    timings: Dict[str, Any] = {}
    async with client.stream("POST", "/v1/chat/completions", json=body) as r:
        r.raise_for_status()
        async for line in r.aiter_lines():
            if not line.startswith("data: ") or line.startswith("data: [DONE]"):
                continue
            d = json.loads(line[6:])
            if d.get("error"):  # llama-server reports a failed decode inside the stream, after HTTP 200
                raise httpx.HTTPError("server error in stream: %s" % json.dumps(d["error"])[:200])
            for ch in d.get("choices") or []:
                delta = ch.get("delta") or {}
                if first is None and (delta.get("content") or delta.get("reasoning_content")):
                    first = time.time()
            usage = d.get("usage") or usage
            timings = d.get("timings") or timings
    t1 = time.time()
    n = int(usage.get("completion_tokens") or 0)
    return {"latency_s": t1 - t0, "ttft_s": (first - t0) if first else None, "completion_tokens": n,
            "prompt_tokens": usage.get("prompt_tokens"), "decode_tps": (n - 1) / (t1 - first) if first and n > 1 and t1 > first else None,
            "draft_n": timings.get("draft_n"), "draft_accepted": timings.get("draft_n_accepted"),
            "server_prefill_tps": (timings["prompt_n"] / timings["prompt_ms"] * 1000) if timings.get("prompt_ms") else None}


async def level(client, prompts: List[str], conc: int, per_slot: int, extra, max_tokens) -> Dict[str, Any]:
    todo = prompts[: conc * per_slot]
    del prompts[: conc * per_slot]  # every level gets questions not seen before (no prompt-cache hits)
    sem = asyncio.Semaphore(conc)
    peak = {"mib": gpu_mem_mib()}

    async def run(p):
        async with sem:
            r = await one(client, p, extra, max_tokens)
            peak["mib"] = max(peak["mib"], gpu_mem_mib())
            return r

    t0 = time.time()
    rows = await asyncio.gather(*[run(p) for p in todo])
    wall = time.time() - t0
    toks = sum(r["completion_tokens"] for r in rows)
    dec = [r["decode_tps"] for r in rows if r["decode_tps"]]
    dn = sum(r["draft_n"] or 0 for r in rows)
    da = sum(r["draft_accepted"] or 0 for r in rows)
    return {"concurrency": conc, "requests": len(rows), "wall_s": round(wall, 1), "completion_tokens": toks,
            "aggregate_tok_s": round(toks / wall, 1), "decode_tps_median": round(statistics.median(dec), 1) if dec else None,
            "ttft_s_median": round(statistics.median([r["ttft_s"] for r in rows if r["ttft_s"]]), 2),
            "latency_s_median": round(statistics.median([r["latency_s"] for r in rows]), 1),
            "draft_acceptance": round(da / dn, 3) if dn else None, "gpu_mem_peak_mib": peak["mib"]}


def long_prompt(data_dir: Path, target_chars: int) -> str:
    parts, n = [], 0
    for it in load(data_dir, "pubmedqa"):
        parts.append(it["context"])
        n += len(it["context"])
        if n >= target_chars:
            break
    # a unique first line so no earlier prompt (or the shorter size) is reused from the prompt cache
    return "Session %d. Here are several study abstracts.\n\n" % time.time_ns() + "\n\n".join(parts) + "\n\nIn one sentence, what is the first abstract about?"


async def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--url", required=True)
    ap.add_argument("--label", required=True)
    ap.add_argument("--concurrency", default="1,2,4,8")
    ap.add_argument("--per-slot", type=int, default=4, help="requests per concurrent stream at each level")
    ap.add_argument("--max-tokens", type=int, default=1024, help="long enough that most medium-effort answers hit it")
    ap.add_argument("--request", default="{}", help="JSON merged into every request")
    ap.add_argument("--long-chars", default="20000,80000", help="long-prompt sizes (characters) for the prefill measurement")
    ap.add_argument("--data", default=str(ROOT / "data"))
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    extra = json.loads(a.request)
    items = load(Path(a.data), "medqa_usmle")
    prompts = [build_prompt(it) for it in items[1::3]]
    res: Dict[str, Any] = {"label": a.label, "url": a.url, "request": extra, "max_tokens": a.max_tokens, "started": time.time(),
                           "gpu_mem_idle_mib": gpu_mem_mib(), "levels": [], "prefill": []}
    async with httpx.AsyncClient(base_url=a.url.rstrip("/"), timeout=httpx.Timeout(1800, connect=30)) as client:
        await one(client, prompts.pop(), extra, 32)  # warm-up
        def save() -> None:  # after every step, so a server that dies under load still leaves the levels it survived
            res["gpu_mem_after_mib"] = gpu_mem_mib()
            Path(a.out).parent.mkdir(parents=True, exist_ok=True)
            Path(a.out).write_text(json.dumps(res, indent=1))

        try:
            for c in [int(x) for x in a.concurrency.split(",")]:
                r = await level(client, prompts, c, a.per_slot, extra, a.max_tokens)
                print(json.dumps(r), flush=True)
                res["levels"].append(r)
                save()
            for chars in [int(x) for x in a.long_chars.split(",") if x]:
                p = long_prompt(Path(a.data), chars)
                r = await one(client, p, {**extra, "chat_template_kwargs": {**extra.get("chat_template_kwargs", {}), "reasoning_effort": "low"}}, 64)
                r["prompt_chars"] = chars
                print(json.dumps(r), flush=True)
                res["prefill"].append(r)
                save()
        except (httpx.HTTPError, json.JSONDecodeError) as e:
            res["failed"] = "%s: %s" % (type(e).__name__, str(e)[:300])
            print("sweep stopped: %s" % res["failed"], flush=True)
        save()
        if res.get("failed"):
            sys.exit(3)


if __name__ == "__main__":
    asyncio.run(main())
