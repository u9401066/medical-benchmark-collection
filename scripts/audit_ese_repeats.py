"""Recompute aggregate counts from the fixed ESE S3 supplementary question bank and response grid."""

import argparse
from collections import Counter
from hashlib import sha256
from io import BytesIO
import json
from pathlib import Path
import re
from xml.etree import ElementTree as ET
from zipfile import ZipFile


QUESTION_SHA256 = "6d089bcdca11a22649d3499d74085ce88abe3c6bc0711ca6a3cad30166f9e801"
GRID_SHA256 = "b14aa9093710fdf7f7e3d72c74329bc3cb11e4ff8113d36fbeffdc455f2465d2"
IDS = {f"{group}{i}" for group, n in (("A", 20), ("B", 30)) for i in range(1, n + 1)}
DAYS = (1, 7, 30)
ACCOUNTS = (1, 2, 3)


def checked_bytes(path, digest):
    raw = path.read_bytes()
    if sha256(raw).hexdigest() != digest:
        raise ValueError(
            f"{path.name}: SHA-256 differs from the publisher file observed on 2026-11-26"
        )
    return raw


def question_totals(raw):
    from docx import Document

    rows = {}
    for row in Document(BytesIO(raw)).tables[0].rows[1:]:
        cells = row.cells
        key = cells[0].text
        match = re.fullmatch(r"([0-9]+)/72\s+\([0-9.]+\)", cells[6].text.strip())
        if key in rows or not match:
            raise ValueError(
                "Invalid or repeated question result in Supplementary Table S1"
            )
        rows[key] = (cells[2].text, int(match[1]))
    if rows.keys() != IDS:
        raise ValueError("Unexpected question IDs in the question bank")
    return rows


def sheet_rows(raw):
    ns = {"s": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
    with ZipFile(BytesIO(raw)) as book:
        strings = ET.fromstring(book.read("xl/sharedStrings.xml"))
        shared = [
            "".join(t.text or "" for t in si.findall(".//s:t", ns)) for si in strings
        ]
        sheet = ET.fromstring(book.read("xl/worksheets/sheet1.xml"))
    for row in sheet.findall(".//s:row", ns):
        cells = {}
        for cell in row.findall("s:c", ns):
            value = cell.findtext("s:v", namespaces=ns)
            if value is None:
                continue
            if cell.get("t") == "s":
                value = shared[int(value)]
            column = re.fullmatch(r"([A-Z]+)[0-9]+", cell.attrib["r"])[1]
            cells[column] = value
        yield int(row.attrib["r"]), cells


def grid(raw):
    rows = iter(sheet_rows(raw))
    row_number, header = next(rows)
    if row_number != 1 or header.get("A") != "QUESTION NO":
        raise ValueError("Unexpected response grid header")
    layout = {}
    for column, value in header.items():
        if column == "A":
            continue
        words = " ".join(value.split()).replace("CHAGTGPT", "CHATGPT")
        match = re.fullmatch(r"Day (1|7|30) (.+)-([123])", words)
        if not match:
            raise ValueError(f"Unexpected model/day/account header in cell {column}1")
        layout[column] = int(match[1]), match[2], int(match[3])
    models = sorted({model for _, model, _ in layout.values()})
    expected = {
        (day, model, account)
        for day in DAYS
        for model in models
        for account in ACCOUNTS
    }
    if len(models) != 8 or len(layout) != 72 or set(layout.values()) != expected:
        raise ValueError(
            "The response grid does not contain all 72 distinct conditions"
        )
    data = {}
    for number, cells in rows:
        if not 2 <= number <= 51:
            continue
        key = cells.get("A")
        if (
            key not in IDS
            or key in data
            or cells.keys() - {"A"} != layout.keys()
            or any(cells[col] not in {"D", "Y"} for col in layout)
        ):
            raise ValueError(
                f"Malformed or duplicate response at spreadsheet row {number}"
            )
        data[key] = {condition: cells[col] == "D" for col, condition in layout.items()}
    if data.keys() != IDS:
        raise ValueError("Unexpected question IDs in the response grid")
    return models, data


def transition(pairs):
    counts = Counter(pairs)
    return {
        "paired": sum(counts.values()),
        "both_correct": counts[True, True],
        "correct_to_incorrect": counts[True, False],
        "incorrect_to_correct": counts[False, True],
        "both_incorrect": counts[False, False],
    }


def audit(question_raw, grid_raw):
    question = question_totals(question_raw)
    models, rows = grid(grid_raw)
    for key, values in rows.items():
        if question[key][1] != sum(values.values()):
            raise ValueError(
                f"{key}: correct count disagrees with Supplementary Table S1"
            )
    return {
        "source_sha256": {
            "question_bank": QUESTION_SHA256,
            "response_grid": GRID_SHA256,
        },
        "questions": len(rows),
        "question_formats": dict(
            sorted(Counter(fmt for fmt, _ in question.values()).items())
        ),
        "reported_correct_counts_matched": len(rows),
        "correct": sum(n for _, n in question.values()),
        "responses": sum(len(v) for v in rows.values()),
        "by_model": {
            model: sum(
                ok
                for row in rows.values()
                for (_, name, _), ok in row.items()
                if name == model
            )
            for model in models
        },
        "same_account_day_change": {
            f"day_1_to_{other}": transition(
                (r[1, model, account], r[other, model, account])
                for r in rows.values()
                for model in models
                for account in ACCOUNTS
            )
            for other in (7, 30)
        },
        "same_day_account_change": {
            f"account_1_to_{other}": transition(
                (r[day, model, 1], r[day, model, other])
                for r in rows.values()
                for model in models
                for day in DAYS
            )
            for other in (2, 3)
        },
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("questions", type=Path)
    parser.add_argument("responses", type=Path)
    args = parser.parse_args()
    try:
        summary = audit(
            checked_bytes(args.questions, QUESTION_SHA256),
            checked_bytes(args.responses, GRID_SHA256),
        )
    except (OSError, KeyError, ValueError) as error:
        parser.exit(1, f"{error}\n")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
