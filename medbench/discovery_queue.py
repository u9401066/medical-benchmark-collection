"""List publications still awaiting first-pass triage across saved PubMed discovery reports."""

import argparse
import csv
import json
import re
from collections import Counter
from datetime import date
from pathlib import Path

from .benchmark_discovery import write_report

PMID = re.compile(r"[1-9][0-9]*")


def make_queue(snapshots, triage):
    # Preserve the acquisition order so a reviewer can resume at the next unscreened PMID.
    candidates, searches = {}, []
    for path in snapshots:
        report = json.loads(path.read_text(encoding="utf-8"))
        records = report["records"]
        status = report["status"]
        if status not in {"complete", "empty", "partial", "error"}:
            raise ValueError(f"{path}: unknown search status {status!r}")
        if report["records_retrieved"] != len(records):
            raise ValueError(f"{path}: record count does not match the snapshot")
        matches = report["total_matches"]
        if status in {"complete", "empty"} and matches != len(records):
            raise ValueError(f"{path}: complete search has missing records")
        search = {
            k: report[k]
            for k in ("start", "end", "status", "total_matches", "records_retrieved")
        }
        search["source"] = path.name
        searches.append(search)
        seen = set()
        for record in records:
            pmid = record["pmid"]
            if not isinstance(pmid, str) or not PMID.fullmatch(pmid) or pmid in seen:
                raise ValueError(f"{path}: invalid or duplicate PMID {pmid!r}")
            seen.add(pmid)
            candidates[pmid] = record

    screened = {}
    with triage.open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream, delimiter="\t")
        if not {"pmid", "checked_on", "status", "study_url"} <= set(
            reader.fieldnames or ()
        ):
            raise ValueError(f"{triage}: invalid triage table header")
        for row in reader:
            pmid = row["pmid"]
            if (
                not PMID.fullmatch(pmid or "")
                or pmid in screened
                or not (row["status"] or "").strip()
                or not (row["study_url"] or "").strip()
            ):
                raise ValueError(
                    f"{triage}:{reader.line_num}: invalid or duplicate screening record {pmid!r}"
                )
            date.fromisoformat(row["checked_on"])
            screened[pmid] = row["status"]

    pending = [record for pmid, record in candidates.items() if pmid not in screened]
    status_counts = Counter(screened[p] for p in candidates if p in screened)
    return {
        "searches": searches,
        "all_searches_complete": all(
            s["status"] in {"complete", "empty"} for s in searches
        ),
        "unique_candidate_pmids": len(candidates),
        "screened_in_snapshots": sum(status_counts.values()),
        "screened_by_status": dict(sorted(status_counts.items())),
        "screened_outside_snapshots": sorted(screened.keys() - candidates.keys()),
        "remaining": len(pending),
        "pending": pending,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    base = Path("datasets/discovery/pubmed")
    parser.add_argument(
        "--snapshots-dir",
        type=Path,
        default=base,
        help="Directory of archived discovery JSON reports",
    )
    parser.add_argument(
        "--latest",
        type=Path,
        help="Also include this live report after the saved snapshots",
    )
    parser.add_argument("--triage", type=Path, default=base / "triage.tsv")
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    if not args.snapshots_dir.is_dir():
        parser.error(f"Snapshot directory does not exist: {args.snapshots_dir}")
    paths = sorted(args.snapshots_dir.glob("*.json"))
    if args.latest and args.latest.resolve() not in {p.resolve() for p in paths}:
        paths.append(args.latest)
    if not paths:
        parser.error("Provide at least one discovery report")
    if (
        args.out.resolve() in {p.resolve() for p in [args.triage, *paths]}
        or args.out.resolve().parent == args.snapshots_dir.resolve()
    ):
        parser.error(
            "Write the queue outside the directory of source snapshots and keep all inputs intact"
        )
    try:
        queue = make_queue(paths, args.triage)
        write_report(args.out, queue)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        parser.exit(1, f"{exc}\n")
    print(
        f"{queue['screened_in_snapshots']}/{queue['unique_candidate_pmids']} candidate PMIDs screened; {queue['remaining']} pending"
    )
    return 0 if queue["all_searches_complete"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
