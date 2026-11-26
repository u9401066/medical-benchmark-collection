"""Independently reconcile the public snapshot, without relying on local originals or the network."""
import csv
import gzip
import json
from collections import Counter
from pathlib import Path

from medbench.moex_coverage import RULES


BASE = Path(__file__).resolve().parents[1] / "datasets" / "moex"


def rows(name):
    with (BASE / name).open(encoding="utf-8", newline="") as stream:
        yield from csv.DictReader(stream, delimiter="\t")


def test_release_counts_match_original_file_entries_and_question_records():
    statistics = {}
    by_year = {}
    for row in rows("coverage/years.tsv"):
        statistics[row["year_roc"]] = row
        by_year[row["year_roc"]] = Counter()
    for row in rows("archive/files.tsv"):
        if row["scope"] != "medical":
            continue
        counts = by_year[row["year_roc"]]
        counts["indexed_files"] += 1
        counts["verified_files"] += row["status"] == "verified"
        if row["status"] == "verified":
            assert len(row["sha256"]) == 64 and int(row["bytes"]) > 0
    for row in rows("coverage/papers.tsv"):
        if row["scope"] in {"medical", "boundary"}:
            by_year[row["year_roc"]][row["scope"] + "_papers"] += 1
    for path in (BASE / "items").glob("*/*.jsonl.gz"):
        with gzip.open(path, "rt", encoding="utf-8") as stream:
            for paper in map(json.loads, stream):
                if paper["paper"]["scope"] != "medical":
                    continue
                counts = by_year[paper["paper"]["year_roc"]]
                item_ids = set()
                for item in paper["items"]:
                    assert item["id"] not in item_ids
                    item_ids.add(item["id"])
                    kind = item["rule"]["kind"]
                    assert kind in RULES
                    counts["rule_" + kind] += 1
                    counts["item_records"] += 1
                    counts["items_with_text"] += bool(item.get("question"))
    assert by_year and all(int(row["stale_item_records"]) == 0 for row in statistics.values())
    required = ["medical_papers", "boundary_papers", "verified_files", "indexed_files",
                "item_records", "items_with_text", *["rule_" + kind for kind in RULES]]
    for year, counts in by_year.items():
        for field in required:
            assert counts[field] == int(statistics[year][field]), (year, field)
