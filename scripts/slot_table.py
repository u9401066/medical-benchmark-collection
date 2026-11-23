"""Markdown tables from scripts/slot_sweep.py results: per-request decode speed, aggregate throughput, time to first token and
GPU memory at each concurrency, plus long-prompt prefill.

  python scripts/slot_table.py results/slots/bonsai-pq2-mtp-np4.json results/slots/inkling-iq4xs-np4.json ...
"""
from __future__ import annotations

import json
import sys
from pathlib import Path


def main(paths) -> None:
    runs = [json.loads(Path(p).read_text()) for p in paths]
    print("| 設定 | 併發 | 每請求解碼 tok/s（中位） | 總吞吐 tok/s | 首 token s（中位） | 每題延遲 s（中位） | 草稿接受率 | GPU 峰值 MiB |")
    print("|---|---:|---:|---:|---:|---:|---:|---:|")
    for r in runs:
        for lv in r["levels"]:
            acc = "—" if lv.get("draft_acceptance") is None else "%.0f%%" % (100 * lv["draft_acceptance"])
            print("| %s | %d | %.1f | %.1f | %.2f | %.1f | %s | %s |" % (r["label"], lv["concurrency"], lv["decode_tps_median"] or 0,
                  lv["aggregate_tok_s"], lv["ttft_s_median"], lv["latency_s_median"], acc, format(int(lv["gpu_mem_peak_mib"]), ",")))
        if r.get("failed"):
            print("| %s | 下一級 | 伺服器中斷（%s） | | | | | |" % (r["label"], r["failed"][:60]))
    print()
    print("| 設定 | 提示 tokens | prefill tok/s（伺服器） | 首 token s |")
    print("|---|---:|---:|---:|")
    for r in runs:
        for p in r.get("prefill", []):
            print("| %s | %s | %s | %.2f |" % (r["label"], format(p["prompt_tokens"], ","),
                  format(int(p["server_prefill_tps"]), ",") if p.get("server_prefill_tps") else "—", p["ttft_s"] or 0))


if __name__ == "__main__":
    main(sys.argv[1:])
