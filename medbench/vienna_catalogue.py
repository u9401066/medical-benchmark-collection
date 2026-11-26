"""Create a searchable source index from the versioned Vienna medical AI catalogue."""
from __future__ import annotations

import argparse
import csv
import hashlib
from pathlib import Path

SHA256 = "8939c50b42a6b99e122462a538f5938f4dbc8cc86b3fda9f46288323c5def69a"
FIELDS = {"name": "Name (or description if no name available)", "task": "Task", "data_basis": "Data basis",
          "access_at_release": "Accessibility", "licence_at_release": "Data license", "language": "Language",
          "publication": "Link: Source publication(s)", "reference": "Link: Main reference", "dataset": "Link: Dataset"}


def build(folder):
    raw = (folder / "annotated-datasets.tsv").read_bytes()
    if hashlib.sha256(raw).hexdigest() != SHA256:
        raise ValueError("Expected the original Zenodo v0.1.3 file")
    lines = raw.decode("utf-8-sig").splitlines()
    header = lines[0].split("\t")
    start, buffer, count = 2, "", 0
    with (folder / "records.tsv").open("w", encoding="utf-8", newline="") as output:
        writer = csv.DictWriter(output, ["id", "original_lines", *FIELDS], delimiter="\t", lineterminator="\n")
        writer.writeheader()
        for number, line in enumerate(lines[1:], start=2):
            buffer += line
            values = buffer.split("\t")
            if len(values) < len(header):
                # Two unquoted line breaks occur inside fields in the immutable upstream.
                continue
            if len(values) != len(header):
                raise ValueError(f"Unexpected number of columns at source line {start}")
            row = dict(zip(header, values))
            writer.writerow(dict(id=f"vienna-0.1.3-L{start}", original_lines=f"{start}-{number}",
                            **{key: row[column] for key, column in FIELDS.items()}))
            count += 1
            start, buffer = number + 1, ""
    if buffer:
        raise ValueError("Incomplete final record")
    return count


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--folder", type=Path, default=Path("datasets/discovery/vienna"))
    print(build(p.parse_args().folder))
