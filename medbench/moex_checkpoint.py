"""Build a local snapshot of MOEX downloads, question records and coverage without network access."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from . import moex_accessible, moex_archive, moex_coverage, moex_items, moex_legacy, moex_rulings


def checkpoint(index, seed, cache, out, decisions):
    archive_dir = out / "archive"
    manifest = archive_dir / "files.tsv"
    rows = moex_archive.plan([index / "assets.tsv"], seed)
    receipts = {url: moex_archive.cached(cache, url, verify=True)
                for url in dict.fromkeys(r["source_url"] for r in rows)}
    moex_archive.export(rows, receipts, manifest)

    exams = moex_archive.exam_plan(index, {"medical", "boundary"})
    exam_receipts = {r["source_url"]: moex_archive.cached(cache, r["source_url"], verify=True) for r in exams}
    moex_archive.export(exams, exam_receipts, archive_dir / "exam-files.tsv")
    moex_accessible.catalog(index, archive_dir / "exam-files.tsv", cache, archive_dir)
    moex_legacy.export(cache, manifest, archive_dir / "exam-files.tsv", out / "legacy")

    # Keep all listed siblings of a downloaded asset, including outstanding originals or corrections.
    # A paper with no downloaded files is already represented in the index and coverage table.
    ready = {r["paper_id"] for r in rows if receipts[r["source_url"]].get("status") == "verified"}
    if ready:
        moex_items.build(manifest, cache, out / "items", paper_ids=ready)
    moex_items.prune_empty_placeholders(out / "items", cache)
    moex_rulings.build(index, manifest, out / "items", decisions, out / "rulings")
    return moex_coverage.build(index, manifest, out / "items", out / "coverage", out / "ocr")


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--index", type=Path, default=Path("datasets/moex/index"))
    p.add_argument("--seed", type=Path, default=Path("datasets/twmed/sources.tsv"))
    p.add_argument("--cache", type=Path, default=Path("data/moex/archive"))
    p.add_argument("--out", type=Path, default=Path("datasets/moex"))
    p.add_argument("--decisions", type=Path, default=Path("datasets/moex/notices/decisions.json"))
    a = p.parse_args()
    print(json.dumps(checkpoint(a.index, a.seed, a.cache, a.out, a.decisions), sort_keys=True))


if __name__ == "__main__":
    main()
