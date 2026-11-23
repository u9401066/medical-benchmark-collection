"""Long-context stress test: N concurrent requests, each with its own long prompt (distinct from the first character, so no
prompt-cache sharing), generating M tokens. Reports whether every request finished and the GPU memory peak.

  python scripts/stress_long.py --url http://127.0.0.1:8091 --n 4 --chars 56000 --max-tokens 512 --out results/slots/stress.json
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent))
from slot_sweep import gpu_mem_mib, long_prompt, one  # noqa: E402


async def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--url", required=True)
    ap.add_argument("--n", type=int, default=4)
    ap.add_argument("--chars", type=int, default=56000)
    ap.add_argument("--max-tokens", type=int, default=512)
    ap.add_argument("--request", default='{"chat_template_kwargs":{"reasoning_effort":"low"}}')
    ap.add_argument("--data", default=str(Path(__file__).resolve().parents[1] / "data"))
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    extra = json.loads(a.request)
    prompts = []
    for i in range(a.n):
        prompts.append(long_prompt(Path(a.data), a.chars).replace("Session ", "Session %d-" % i, 1))
        await asyncio.sleep(0.001)
    peak = {"mib": gpu_mem_mib()}

    async def watch():
        while True:
            peak["mib"] = max(peak["mib"], gpu_mem_mib())
            await asyncio.sleep(0.5)

    res = {"url": a.url, "n": a.n, "chars": a.chars, "max_tokens": a.max_tokens, "started": time.time(), "results": []}
    w = asyncio.create_task(watch())
    async with httpx.AsyncClient(base_url=a.url.rstrip("/"), timeout=httpx.Timeout(1800, connect=30)) as client:
        t0 = time.time()
        rows = await asyncio.gather(*[one(client, p, extra, a.max_tokens) for p in prompts], return_exceptions=True)
        res["wall_s"] = round(time.time() - t0, 1)
    w.cancel()
    for r in rows:
        res["results"].append({"error": "%s: %s" % (type(r).__name__, str(r)[:200])} if isinstance(r, BaseException) else r)
    res["ok"] = all(not isinstance(r, BaseException) for r in rows)
    res["gpu_mem_peak_mib"] = peak["mib"]
    Path(a.out).write_text(json.dumps(res, indent=1))
    print(json.dumps({"ok": res["ok"], "wall_s": res["wall_s"], "gpu_mem_peak_mib": res["gpu_mem_peak_mib"],
                      "prompt_tokens": [r.get("prompt_tokens") for r in res["results"]],
                      "errors": [r["error"] for r in res["results"] if "error" in r]}))
    sys.exit(0 if res["ok"] else 3)


if __name__ == "__main__":
    asyncio.run(main())
