"""Script and language of Chinese answers: Traditional vs Simplified characters and English share, per run.

For each MedQA-TWMLE item (Traditional Chinese questions) it counts, in the final answer and in the reasoning, the Han
characters that are Simplified-only (OpenCC s2tw, Simplified -> Taiwan standard, changes them), those that are
Traditional-only (tw2s changes them), and Latin letters. Characters used anywhere in the exam's own questions and options
(authentic Taiwanese text, e.g. 床 群 灶 台) and a few one-to-many characters (干 后 里 于 余 ...) are never counted as Simplified. Reported per run: mean Simplified share of the distinct-script characters, the share
of answers with any Simplified-only character (>= 3), and the share of answers written mostly in English.

  python scripts/zh_quality.py results/bonsai27b-pq2-medium results/inkling2mini-iq4xs-medium --out results/zh_quality.json
"""
from __future__ import annotations

import argparse
import gzip
import json
import re
import statistics
from pathlib import Path
from typing import Any, Dict, List

from opencc import OpenCC

S2T, T2S = OpenCC("s2tw"), OpenCC("tw2s")
AMBIGUOUS = set("干后里于余台征准游秘托占岩杰峰唇吃胜夸葱虱踪腭面松系只才几出了借卷")
ALLOWED: set = set()
HAN = re.compile(r"[\u4e00-\u9fff]")
LATIN = re.compile(r"[A-Za-z]")
_cache: Dict[str, str] = {}


def kind(c: str) -> str:
    k = _cache.get(c)
    if k is None:
        if T2S.convert(c) != c:
            k = "trad"
        elif S2T.convert(c) != c and c not in ALLOWED and c not in AMBIGUOUS:
            k = "simp"
        else:
            k = "both"
        _cache[c] = k
    return k


def measure(text: str) -> Dict[str, int]:
    han = HAN.findall(text or "")
    out = {"han": len(han), "simp": 0, "trad": 0, "latin": len(LATIN.findall(text or ""))}
    for c in han:
        k = kind(c)
        if k != "both":
            out[k] += 1
    return out


def raw_rows(run: Path):
    p = run / "raw.jsonl"
    f = open(p, encoding="utf-8") if p.exists() else gzip.open(run / "raw.jsonl.gz", "rt", encoding="utf-8")
    with f:
        for line in f:
            if line.strip():
                yield json.loads(line)


def summarize(ms: List[Dict[str, int]]) -> Dict[str, Any]:
    shares = [m["simp"] / (m["simp"] + m["trad"]) for m in ms if m["simp"] + m["trad"] >= 5]
    return {"n": len(ms),
            "simplified_share_mean": statistics.mean(shares) if shares else None,
            "answers_with_simplified_chars": sum(1 for m in ms if m["simp"] >= 3) / len(ms) if ms else None,
            "answers_mostly_english": sum(1 for m in ms if m["latin"] > m["han"]) / len(ms) if ms else None,
            "han_chars_median": statistics.median([m["han"] for m in ms]) if ms else None}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("runs", nargs="+")
    ap.add_argument("--dataset", default="medqa_twmle")
    ap.add_argument("--out")
    ap.add_argument("--data", default=str(Path(__file__).resolve().parents[1] / "data"))
    a = ap.parse_args()
    with open(Path(a.data) / ("%s.jsonl" % a.dataset), encoding="utf-8") as f:
        for line in f:
            it = json.loads(line)
            ALLOWED.update(HAN.findall(it["question"] + "".join((it.get("options") or {}).values())))
    res = {}
    for r in a.runs:
        run = Path(r)
        label = json.loads((run / "manifest.json").read_text())["config"].get("label", run.name)
        content, reasoning = [], []
        for row in raw_rows(run):
            if not row["id"].startswith(a.dataset):
                continue
            content.append(measure(row.get("content", "")))
            reasoning.append(measure(row.get("reasoning", "")))
        res[label] = {"answer": summarize(content), "reasoning": summarize(reasoning)}
        print(label)
        for part in ("answer", "reasoning"):
            s = res[label][part]
            print("  %-9s n=%d  simplified share %s  with simplified chars %s  mostly English %s  Han chars median %s" % (
                part, s["n"], "%.1f%%" % (100 * s["simplified_share_mean"]) if s["simplified_share_mean"] is not None else "-",
                "%.1f%%" % (100 * s["answers_with_simplified_chars"]), "%.1f%%" % (100 * s["answers_mostly_english"]),
                s["han_chars_median"]))
    if a.out:
        Path(a.out).parent.mkdir(parents=True, exist_ok=True)
        Path(a.out).write_text(json.dumps(res, indent=1, ensure_ascii=False))


if __name__ == "__main__":
    main()
