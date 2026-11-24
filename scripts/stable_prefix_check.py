"""Does a new agent session reuse the prompt cache of another one? (llama-mcp-router v0.14 `stable_prefix`)

Sends the first request of a recorded agent run (scripts/agent_capture_proxy.py) as if it came from different sessions:
the session id in the prompt is replaced by a new one per call, all calls go to the same idle slot with max_tokens 1.

    raw_A, raw_B         the request as DeepSeek Harness sends it: B re-processes everything if the session line breaks reuse
    stable_A/B/E         the same after llama-mcp-router's _stable_prefix (the session-specific system lines moved to the
                         first user message): B and E should re-process only the part after the first user message starts

    ~/llama-mcp-router/.venv/bin/python scripts/stable_prefix_check.py --url http://127.0.0.1:8081 \
        --out results/speed/stable-prefix/result.json

Runs with a Python that has llama-mcp-router (v0.14+) and its dependencies installed, e.g. the router's own venv
(--router-src points at a checkout's src/ if the installed one is older).

Uses one slot for about 30 s (3 full prefills of the first request). Prints and writes prompt_n / cache_n / prompt_ms per call.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.request

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--url", default="http://127.0.0.1:8081")
    ap.add_argument("--trace", default=os.path.join(HERE, "results/speed/agent/trace-xhigh.jsonl"))
    ap.add_argument("--session-id", default="b7c1a5b6e5a54b35953997ee13cbf984", help="session id recorded in the trace")
    ap.add_argument("--router-src", help="llama-mcp-router src/ directory to import from (default: the installed package)")
    ap.add_argument("--effort", default="max")
    ap.add_argument("--out")
    a = ap.parse_args()

    if a.router_src:
        sys.path.insert(0, os.path.expanduser(a.router_src))
    try:
        from llama_mcp_router.proxy import _stable_prefix
    except ImportError as e:
        sys.exit(f"needs llama-mcp-router >= 0.14 and its dependencies ({e}); run it with the router's Python, "
                 "e.g. ~/llama-mcp-router/.venv/bin/python")

    def get(path):
        return json.load(urllib.request.urlopen(a.url + path, timeout=30))

    def post(path, obj):
        req = urllib.request.Request(a.url + path, data=json.dumps(obj).encode(), headers={"Content-Type": "application/json"})
        return json.load(urllib.request.urlopen(req, timeout=600))

    with open(a.trace, encoding="utf-8") as f:
        body = json.loads(f.readline())["body"]

    def variant(sid, stable):
        msgs = json.loads(json.dumps(body["messages"]).replace(a.session_id, sid))
        if stable:
            _stable_prefix(msgs, [sid])
        return msgs

    def idle_slot():
        while True:
            for s in get("/slots"):
                if not s["is_processing"]:
                    return s["id"]
            time.sleep(1)

    def call(msgs, slot):
        t = time.time()
        r = post("/v1/chat/completions", {"messages": msgs, "tools": body["tools"], "reasoning_effort": a.effort,
                                          "max_tokens": 1, "id_slot": slot, "cache_prompt": True})
        tm = r["timings"]
        return {"prompt_n": tm["prompt_n"], "cache_n": tm.get("cache_n"), "prompt_ms": round(tm["prompt_ms"]),
                "wall_s": round(time.time() - t, 2)}

    slot = idle_slot()
    out = {"url": a.url, "slot": slot, "started": time.strftime("%Y-%m-%d %H:%M:%S")}
    out["raw_A"] = call(variant("a" * 32, False), slot)
    out["raw_B"] = call(variant("b" * 32, False), slot)
    out["stable_A"] = call(variant("c" * 32, True), slot)
    out["stable_B"] = call(variant("d" * 32, True), slot)
    out["stable_E"] = call(variant("e" * 32, True), slot)
    print(json.dumps(out, indent=1))
    if a.out:
        os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
        with open(a.out, "w", encoding="utf-8") as f:
            json.dump(out, f, indent=1)


if __name__ == "__main__":
    main()
