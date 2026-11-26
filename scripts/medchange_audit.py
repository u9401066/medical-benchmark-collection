"""Tabulate the released MedChangeQA label pairs without emitting question text."""

import argparse
import csv
import hashlib
import io
import json
from collections import Counter, defaultdict
from pathlib import Path


SHA256 = "ef1de909a188ab1da96328bbf589ffcf0554f18c9bc2f64b11f0f6e3fa5051d5"
FIELDS = ["", "Question", "Newest Label", "Outdated Label"]
LABELS = ["SUPPORTED", "REFUTED", "NOT ENOUGH INFORMATION"]


def audit(path: Path) -> dict:
    raw = path.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    if digest != SHA256:
        raise ValueError(f"CSV SHA-256 differs from the audited release: {digest}")
    reader = csv.DictReader(io.StringIO(raw.decode("utf-8-sig"), newline=""))
    if reader.fieldnames != FIELDS:
        raise ValueError("Unexpected MedChangeQA CSV header")

    pairs = Counter()
    row_ids = set()
    per_question = defaultdict(list)
    missing = Counter()
    for row in reader:
        for field in FIELDS:
            if not row[field].strip():
                missing[field or "row_id"] += 1
        old, new = row["Outdated Label"], row["Newest Label"]
        if old not in LABELS or new not in LABELS:
            raise ValueError(f"Unexpected or missing label on CSV line {reader.line_num}")
        pairs[old, new] += 1
        row_ids.add(row[""])
        per_question[row["Question"]].append((old, new))

    repeats = [group for group in per_question.values() if len(group) > 1]
    return {
        "sha256": digest,
        "rows": sum(pairs.values()),
        "distinct_row_ids": len(row_ids),
        "distinct_question_strings": len(per_question),
        "repeated_question_strings": len(repeats),
        "rows_with_repeated_question": sum(len(group) for group in repeats),
        "repeated_strings_with_different_new_labels": sum(
            len({new for _, new in group}) > 1 for group in repeats
        ),
        "missing_by_field": {field or "row_id": missing[field or "row_id"] for field in FIELDS},
        "old_to_new": {old: {new: pairs[old, new] for new in LABELS} for old in LABELS},
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("csv", type=Path, help="MedChangeQA.csv from the pinned release")
    args = parser.parse_args()
    try:
        result = audit(args.csv)
    except (OSError, ValueError) as error:
        parser.exit(1, f"{error}\n")
    print(json.dumps(result, indent=2))
