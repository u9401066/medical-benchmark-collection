"""Index source locations and identical question texts in the pinned YNHHQA release."""

import argparse
import hashlib
import os
import re
from collections import defaultdict
from pathlib import Path
from tempfile import NamedTemporaryFile


SOURCE_SHA256 = "fd9e6d8e2c99de7d1230a1dd76e26b5db8152cf94dcb3a05520c5ee8975fa003"
DEFAULT_OUTPUT = Path("datasets/discovery/ehrnavigator/questions.tsv")
HEADER = "source_line\tquestion_number\tquestion_start_byte\tquestion_end_byte\tduplicate_group\tquestion_sha256"


def build_index(raw):
    raw.decode("utf-8")
    locations = []
    numbers_by_text = defaultdict(list)
    seen_numbers = set()
    offset = 0
    for line_number, line in enumerate(raw.splitlines(keepends=True), 1):
        content = line.removesuffix(b"\n").removesuffix(b"\r")
        match = re.fullmatch(rb"([1-9][0-9]*)\. (.+)", content)
        if not match:
            raise ValueError(f"Missing numbered question on source line {line_number}")
        number = int(match[1])
        if number in seen_numbers:
            raise ValueError(f"Repeated source question number {number}")
        seen_numbers.add(number)
        text = match[2]
        start, end = offset + match.start(2), offset + match.end(2)
        locations.append((line_number, number, start, end, text))
        numbers_by_text[text].append(number)
        offset += len(line)

    lines = [HEADER]
    for line_number, number, start, end, text in locations:
        members = numbers_by_text[text]
        group = str(min(members)) if len(members) > 1 else ""
        digest = hashlib.sha256(text).hexdigest()
        lines.append(f"{line_number}\t{number}\t{start}\t{end}\t{group}\t{digest}")
    return ("\n".join(lines) + "\n").encode("ascii"), len(locations), len(numbers_by_text)


def prepare(source, output, check=False):
    if source.resolve() == output.resolve():
        raise ValueError("Output must differ from source")
    raw = source.read_bytes()
    if hashlib.sha256(raw).hexdigest() != SOURCE_SHA256:
        raise ValueError("SHA-256 differs from the pinned YNHHQA.txt release")
    index, count, distinct = build_index(raw)
    if (count, distinct) != (100, 99):
        raise ValueError("Unexpected YNHHQA question counts")
    if check:
        # Git checkouts may have translated the TSV's line endings.
        if output.read_text(encoding="ascii") != index.decode("ascii"):
            raise ValueError("Published TSV differs from the reconstructed index")
    else:
        output.parent.mkdir(parents=True, exist_ok=True)
        with NamedTemporaryFile(dir=output.parent, delete=False) as stream:
            temp = Path(stream.name)
        try:
            temp.write_bytes(index)
            os.replace(temp, output)
        finally:
            temp.unlink(missing_ok=True)
    return count, distinct


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path, help="YNHHQA.txt from the pinned author commit")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--check", action="store_true", help="Validate the existing index")
    args = parser.parse_args()
    try:
        count, distinct = prepare(args.source, args.out, args.check)
    except (OSError, ValueError) as error:
        parser.exit(1, f"{error}\n")
    print(f"{count} numbered questions; {distinct} distinct question texts")
