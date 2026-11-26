"""Prepare the MMLU authors' public anatomy val/test CSV for the batch-prompt experiment."""

import argparse
import csv
import hashlib
import io
import json
from pathlib import Path
import sys
import tarfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from medbench.moex_archive import atomic  # noqa: E402

MEMBERS = {
    "val": (14, "09e9959486ebf3643e4ecbf173a77b029c6f08665ab8f89daf99399956f26b8e"),
    "test": (135, "966dfd5c4579885ebdb8c05d6754ae5834f672632586d8595be3c0f9360e6f4e"),
}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "input", type=Path, help="Official data.tar or the extracted anatomy CSV"
    )
    parser.add_argument("--split", required=True, choices=MEMBERS)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    if args.out.resolve() == args.input.resolve():
        parser.error("Choose an output path distinct from the source")
    if args.input.suffix.lower() == ".csv":
        raw = args.input.read_bytes()
    else:
        with tarfile.open(args.input) as archive:
            member = archive.getmember(f"data/{args.split}/anatomy_{args.split}.csv")
            if not member.isfile():
                parser.error("Expected an ordinary CSV member")
            with archive.extractfile(member) as stream:
                raw = stream.read()
    expected_count, expected_sha = MEMBERS[args.split]
    if hashlib.sha256(raw).hexdigest() != expected_sha:
        parser.error("Anatomy member SHA-256 differs from the audited version")
    records = []
    for index, row in enumerate(
        csv.reader(io.StringIO(raw.decode("utf-8"), newline="")), 1
    ):
        if len(row) != 6 or row[-1] not in {"A", "B", "C", "D"}:
            parser.error(f"Unexpected MCQ format at row {index}")
        records.append(
            {
                "id": f"anatomy-{args.split}-{index:03d}",
                "kind": "mcq",
                "question": row[0],
                "options": dict(zip("ABCD", row[1:5])),
                "answer": row[5],
                "meta": {"subject": "anatomy"},
            }
        )
    if len(records) != expected_count:
        parser.error("Unexpected number of anatomy questions")
    atomic(
        args.out,
        "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in records).encode(),
    )
    print(f"{args.split}: {len(records)} questions; source SHA-256 {expected_sha}")


if __name__ == "__main__":
    main()
