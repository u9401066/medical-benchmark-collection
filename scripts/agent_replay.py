"""Replay a recorded agent run (scripts/agent_capture_proxy.py) against a llama-server and time every model call.

The conversation is replayed as recorded (teacher forcing: each request carries the recorded history, so every server
sees the same prompts and the same prompt-cache opportunities, including the full re-processing a changed tool list
causes). The model generates its own answer to each request at the chosen reasoning effort; its speed is measured, the
answer itself is discarded. A random nonce at the start of the first system message keeps one run from reusing the
prompt cache of an earlier run.

    .venv/bin/python scripts/agent_replay.py --trace results/speed/agent/trace-xhigh.jsonl --url http://127.0.0.1:8091 \
        --requests 1-4 --effort max --out results/speed/agent/<config>.json

Per request: new prompt tokens (prompt_n), reused tokens (cache_n), prefill tok/s, generated tokens and decode tok/s, and
the speculative-decoding acceptance when the server drafts. Summary: totals, aggregate prefill/decode speed and a modeled
task time = recorded prompt tokens / measured prefill speed + recorded output tokens / measured decode speed (the recorded
counts come from <trace>.timings.jsonl, so configurations are compared on the same work).
--parallel N replays N copies at once (N users) with their own nonces.
"""
from __future__ import annotations

import argparse
import copy
import json
import sys
import threading
import time
import urllib.request
import uuid
from typing import Any, Dict, List, Optional


def parse_ranges(spec: str, n: int) -> List[int]:
    if not spec or spec == "all":
        return list(range(1, n + 1))
    out: List[int] = []
    for part in spec.split(","):
        a, _, b = part.partition("-")
        out.extend(range(int(a), int(b or a) + 1))
    return [i for i in out if 1 <= i <= n]


def load(path: str) -> List[Dict[str, Any]]:
    with open(path, encoding="utf-8") as f:
        return [json.loads(l) for l in f if l.strip()]


def with_nonce(body: Dict[str, Any], nonce: str) -> None:
    for m in body.get("messages") or []:
        if m.get("role") in ("system", "developer"):
            c = m.get("content")
            tag = "[run %s]\n" % nonce
            if isinstance(c, str):
                m["content"] = tag + c
            elif isinstance(c, list) and c and isinstance(c[0], dict) and c[0].get("type") == "text":
                c[0]["text"] = tag + c[0]["text"]
            return
    body.setdefault("messages", []).insert(0, {"role": "system", "content": "[run %s]" % nonce})


def call(url: str, body: Dict[str, Any], timeout: float) -> Dict[str, Any]:
    req = urllib.request.Request(url + "/v1/chat/completions", json.dumps(body, ensure_ascii=False).encode("utf-8"),
                                 {"content-type": "application/json"})
    t0 = time.perf_counter()
    first, timings, finish, err = None, None, None, None
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            for raw in r:
                line = raw.decode("utf-8", "replace").strip()
                if not line.startswith("data: {"):
                    continue
                d = json.loads(line[6:])
                ch = (d.get("choices") or [{}])[0] or {}
                delta = ch.get("delta") or {}
                if first is None and (delta.get("content") or delta.get("reasoning_content") or delta.get("tool_calls")):
                    first = time.perf_counter() - t0
                finish = ch.get("finish_reason") or finish
                if isinstance(d.get("timings"), dict):
                    timings = d["timings"]
    except Exception as e:  # noqa: BLE001 - report and go on
        err = "%s: %s" % (type(e).__name__, e)
    return {"wall_s": round(time.perf_counter() - t0, 3), "ttft_s": round(first, 3) if first else None, "finish_reason": finish,
            "timings": timings, "error": err}


def replay(trace: List[Dict[str, Any]], idx: List[int], a: argparse.Namespace, nonce: str) -> List[Dict[str, Any]]:
    rows = []
    for i in idx:
        body = copy.deepcopy(trace[i - 1]["body"])
        for k in ("timings_per_token", "return_progress", "store", "stream_options"):
            body.pop(k, None)
        body["stream"] = True
        if a.effort == "server":
            body.pop("reasoning_effort", None)
        elif a.effort != "keep":
            body["reasoning_effort"] = a.effort
        cap = a.max_tokens
        rec = a.recorded.get(i)
        if a.budget == "recorded" and rec and rec.get("predicted_n"):
            cap = min(cap, max(int(rec["predicted_n"]), 64))
        body.pop("max_completion_tokens", None)
        body["max_tokens"] = cap
        if a.seed is not None:
            body["seed"] = a.seed
        with_nonce(body, nonce)
        res = call(a.url, body, a.timeout)
        t = res.get("timings") or {}
        row = {"i": i, "nonce": nonce, "max_tokens": cap, "prompt_n": t.get("prompt_n"), "cache_n": t.get("cache_n"),
               "prompt_ms": t.get("prompt_ms"), "prefill_tps": round(t["prompt_per_second"], 1) if t.get("prompt_per_second") else None,
               "predicted_n": t.get("predicted_n"), "predicted_ms": t.get("predicted_ms"),
               "decode_tps": round(t["predicted_per_second"], 2) if t.get("predicted_per_second") else None,
               "draft_n": t.get("draft_n"), "draft_n_accepted": t.get("draft_n_accepted"), **res}
        row.pop("timings", None)
        rows.append(row)
        if not a.quiet:
            print("  #%-3d new %6s reused %6s  prefill %7s tok/s  out %5s  decode %6s tok/s%s  %6.1fs%s" % (
                i, row["prompt_n"], row["cache_n"], row["prefill_tps"], row["predicted_n"], row["decode_tps"],
                ("  draft %s/%s" % (row["draft_n_accepted"], row["draft_n"])) if row.get("draft_n") else "", row["wall_s"],
                ("  ERROR " + res["error"]) if res["error"] else ""), flush=True)
        if res["error"]:
            break
    return rows


def summarize(rows: List[Dict[str, Any]], recorded: Dict[int, Dict[str, Any]], idx: List[int]) -> Dict[str, Any]:
    ok = [r for r in rows if not r["error"] and r["prompt_n"] is not None]
    pn = sum(r["prompt_n"] or 0 for r in ok)
    pms = sum(r["prompt_ms"] or 0 for r in ok)
    gn = sum(r["predicted_n"] or 0 for r in ok)
    gms = sum(r["predicted_ms"] or 0 for r in ok)
    dn = sum(r["draft_n"] or 0 for r in ok)
    da = sum(r["draft_n_accepted"] or 0 for r in ok)
    pp = pn / pms * 1000 if pms else None
    tg = gn / gms * 1000 if gms else None
    rp = sum((recorded.get(i) or {}).get("prompt_n") or 0 for i in idx)
    rg = sum((recorded.get(i) or {}).get("predicted_n") or 0 for i in idx)
    s = {"requests": len(rows), "ok": len(ok), "prompt_tokens": pn, "prefill_s": round(pms / 1000, 1),
         "prefill_tps": round(pp, 1) if pp else None, "output_tokens": gn, "decode_s": round(gms / 1000, 1),
         "decode_tps": round(tg, 2) if tg else None, "wall_s": round(sum(r["wall_s"] for r in rows), 1),
         "recorded_prompt_tokens": rp, "recorded_output_tokens": rg}
    if pp and tg:
        s["modeled_task_s"] = round(rp / pp + rg / tg, 1)
        s["modeled_prefill_share"] = round((rp / pp) / (rp / pp + rg / tg), 3)
    if dn:
        s["draft_acceptance"] = round(da / dn, 3)
    return s


def main(argv: List[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--trace", required=True, help="<out>.jsonl from agent_capture_proxy.py")
    ap.add_argument("--url", default="http://127.0.0.1:8091")
    ap.add_argument("--requests", default="all", help="e.g. 1-4 or 1-4,12 (in order; keep a contiguous run for cache reuse)")
    ap.add_argument("--effort", default="max", help="reasoning_effort to send (max = xhigh = 0.99); 'keep' = as recorded; 'server' = none")
    ap.add_argument("--max-tokens", type=int, default=4096, help="cap per request")
    ap.add_argument("--budget", choices=["recorded", "cap"], default="recorded",
                    help="recorded: min(cap, the recorded output length) so every configuration generates about the same")
    ap.add_argument("--seed", type=int, default=1234)
    ap.add_argument("--parallel", type=int, default=1)
    ap.add_argument("--timeout", type=float, default=1800)
    ap.add_argument("--label", default="")
    ap.add_argument("--out")
    ap.add_argument("--quiet", action="store_true")
    a = ap.parse_args(argv)
    trace = load(a.trace)
    tpath = a.trace[:-len(".jsonl")] + ".timings.jsonl" if a.trace.endswith(".jsonl") else a.trace + ".timings.jsonl"
    try:
        a.recorded = {r["i"]: (r.get("timings") or {}) for r in load(tpath)}
    except OSError:
        a.recorded = {}
    idx = parse_ranges(a.requests, len(trace))
    print("replaying %d of %d requests (%s), effort %s, %d in parallel -> %s" % (len(idx), len(trace), a.requests, a.effort, a.parallel, a.url),
          flush=True)
    t0 = time.perf_counter()
    results: List[Optional[List[Dict[str, Any]]]] = [None] * a.parallel

    def worker(k: int) -> None:
        results[k] = replay(trace, idx, a, uuid.uuid4().hex[:10])

    threads = [threading.Thread(target=worker, args=(k,)) for k in range(a.parallel)]
    for th in threads:
        th.start()
        if a.parallel > 1:
            time.sleep(0.5)
    for th in threads:
        th.join()
    wall = time.perf_counter() - t0
    runs = [r or [] for r in results]
    out = {"label": a.label, "url": a.url, "trace": a.trace, "requests": a.requests, "effort": a.effort, "max_tokens": a.max_tokens,
           "budget": a.budget, "parallel": a.parallel, "wall_s": round(wall, 1), "runs": [summarize(r, a.recorded, idx) for r in runs],
           "rows": runs}
    if a.parallel > 1:
        tot_g = sum(s["output_tokens"] for s in out["runs"])
        tot_p = sum(s["prompt_tokens"] for s in out["runs"])
        out["aggregate"] = {"output_tok_s": round(tot_g / wall, 1), "prompt_tok_s": round(tot_p / wall, 1)}
    for k, s in enumerate(out["runs"]):
        print("run %d: prefill %s tokens in %ss (%s tok/s), decode %s tokens in %ss (%s tok/s)%s, wall %ss, modeled task %ss" % (
            k + 1, s["prompt_tokens"], s["prefill_s"], s["prefill_tps"], s["output_tokens"], s["decode_s"], s["decode_tps"],
            (", draft acceptance %s" % s["draft_acceptance"]) if s.get("draft_acceptance") is not None else "", s["wall_s"],
            s.get("modeled_task_s")), flush=True)
    if out.get("aggregate"):
        print("aggregate over %.1fs: %s output tok/s, %s prompt tok/s" % (wall, out["aggregate"]["output_tok_s"], out["aggregate"]["prompt_tok_s"]))
    if a.out:
        with open(a.out, "w", encoding="utf-8") as f:
            json.dump(out, f, ensure_ascii=False, indent=1)
    return 0 if all(s["ok"] == s["requests"] for s in out["runs"]) else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
