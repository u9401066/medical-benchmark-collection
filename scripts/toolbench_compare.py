"""Paired comparison of llama-mcp-router tool benchmarks (benchmarks/run_bench.py llm_results.json): first tool call correct.

    python scripts/toolbench_compare.py results/toolbench/bonsai_heldout results/toolbench/inkling-q3kxl_heldout
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from medbench.score import mcnemar_exact, wilson  # noqa: E402


def load(run: Path) -> dict:
    return {sel: {r["id"]: r for r in rows} for sel, rows in json.loads((run / "llm_results.json").read_text()).items()}


def main(argv: list) -> int:
    if len(argv) < 2 or len(argv) % 2:
        print(__doc__, file=sys.stderr)
        return 2
    print("| A | B | selector | n | A correct | B correct | only A | only B | McNemar p | A s/query (median) | B s/query (median) |")
    print("|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|")
    pooled = {}
    for a_dir, b_dir in zip(argv[0::2], argv[1::2]):
        a, b = load(Path(a_dir)), load(Path(b_dir))
        for sel in a:
            if sel not in b:
                continue
            ids = sorted(set(a[sel]) & set(b[sel]))
            xa = [bool(a[sel][i]["ok"]) for i in ids]
            xb = [bool(b[sel][i]["ok"]) for i in ids]
            only_a = sum(1 for x, y in zip(xa, xb) if x and not y)
            only_b = sum(1 for x, y in zip(xa, xb) if y and not x)
            p = pooled.setdefault(sel, [0, 0, 0, 0, 0])
            for k, v in enumerate((len(ids), sum(xa), sum(xb), only_a, only_b)):
                p[k] += v

            def med(run, sel=sel):
                s = sorted(run[sel][i]["s"] for i in ids)
                return s[len(s) // 2]

            def pct(k, n):
                lo, hi = wilson(k, n)
                return "%d (%.1f%%, %.0f–%.0f%%)" % (k, 100 * k / n, 100 * lo, 100 * hi)

            print("| %s | %s | %s | %d | %s | %s | %d | %d | %.3g | %.2f | %.2f |" % (
                Path(a_dir).name, Path(b_dir).name, sel, len(ids), pct(sum(xa), len(ids)), pct(sum(xb), len(ids)),
                only_a, only_b, mcnemar_exact(only_a, only_b), med(a), med(b)))
    if len(argv) > 2:
        for sel, (n, ka, kb, oa, ob) in pooled.items():
            print("| pooled | | %s | %d | %d (%.1f%%) | %d (%.1f%%) | %d | %d | %.3g | | |" % (sel, n, ka, 100 * ka / n, kb, 100 * kb / n, oa, ob,
                                                                                   mcnemar_exact(oa, ob)))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
