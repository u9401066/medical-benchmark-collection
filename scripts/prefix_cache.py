"""Prompt reuse across turns and conversations on a llama-server (prefix cache and --cache-ram).

Conversation A runs for --turns turns (each turn appends a user message and the model's reply), then --others different
conversations of the same size run, then A gets one more turn. Prints, per request, how many prompt tokens the server read
again (prompt_n) and reused from its cache (cache_n), and the prefill time.

    python scripts/prefix_cache.py --url http://127.0.0.1:8081 --effort none --out results/slots/prefix-inkling.json
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.request

QUESTIONS = ["Summarise the guidance above in three bullet points.", "Which part matters most for an ICU patient?",
             "Give one example question a resident could ask.", "What would you check first?", "Answer in one sentence: why?"]


def post(url: str, body: dict, timeout: float = 900) -> dict:
    req = urllib.request.Request(url + "/v1/chat/completions", json.dumps(body).encode(), {"content-type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)


def context(n_words: int, seed: str) -> str:
    """A long, unique system prompt (~1.3 tokens per word), so conversations never share a prefix by accident."""
    words = ("sedation analgesia delirium ventilation weaning sepsis lactate vasopressor fluid balance renal replacement "
             "anticoagulation nutrition glucose transfusion antibiotics stewardship mobilisation pressure injury").split()
    body = " ".join(words[(i * 7 + len(seed)) % len(words)] for i in range(n_words))
    return "Conversation %s. Reference notes for this conversation:\n%s" % (seed, body)


def turn(url: str, msgs: list, effort: str, max_tokens: int) -> dict:
    body = {"model": "m", "messages": msgs, "max_tokens": max_tokens, "temperature": 0, "chat_template_kwargs": {"reasoning_effort": effort}}
    t0 = time.perf_counter()
    d = post(url, body)
    t = d.get("timings") or {}
    msg = d["choices"][0]["message"]
    msgs.append({"role": "assistant", "content": msg.get("content") or "OK."})
    return {"prompt_n": t.get("prompt_n"), "cache_n": t.get("cache_n"), "prompt_ms": round(t.get("prompt_ms", 0.0), 1),
            "wall_s": round(time.perf_counter() - t0, 2)}


def main(argv: list) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--url", default="http://127.0.0.1:8081")
    ap.add_argument("--words", type=int, default=6000, help="system prompt size in words (~1.3 tokens each)")
    ap.add_argument("--turns", type=int, default=4)
    ap.add_argument("--others", type=int, default=3, help="other conversations between A's last turns")
    ap.add_argument("--effort", default="none", help="reasoning_effort for every request (short answers keep the test fast)")
    ap.add_argument("--max-tokens", type=int, default=64)
    ap.add_argument("--out")
    a = ap.parse_args(argv)
    nonce = str(int(time.time()))
    rows = []

    def record(conv: str, i: int, r: dict) -> None:
        rows.append({"conversation": conv, "turn": i, **r})
        print("%-3s turn %d: read %6s tokens, reused %6s, prefill %8.1f ms, wall %.2f s" % (conv, i, r["prompt_n"], r["cache_n"], r["prompt_ms"], r["wall_s"]))

    a_msgs = [{"role": "system", "content": context(a.words, "A" + nonce)}]
    for i in range(a.turns):
        a_msgs.append({"role": "user", "content": QUESTIONS[i % len(QUESTIONS)]})
        record("A", i + 1, turn(a.url, a_msgs, a.effort, a.max_tokens))
    for k in range(a.others):
        msgs = [{"role": "system", "content": context(a.words, "%s%s" % (chr(66 + k), nonce))}, {"role": "user", "content": QUESTIONS[0]}]
        record(chr(66 + k), 1, turn(a.url, msgs, a.effort, a.max_tokens))
    a_msgs.append({"role": "user", "content": QUESTIONS[a.turns % len(QUESTIONS)]})
    record("A", a.turns + 1, turn(a.url, a_msgs, a.effort, a.max_tokens))
    if a.out:
        with open(a.out, "w") as f:
            json.dump({"url": a.url, "words": a.words, "effort": a.effort, "rows": rows}, f, indent=1)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
