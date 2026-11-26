"""Audit aggregate denominators and bilingual pairing in the pinned PMID 43083842 workbook."""

import argparse
import hashlib
import io
import json
from collections import Counter, defaultdict
from pathlib import Path
from xml.etree import ElementTree as ET
from zipfile import ZipFile


SHA256 = "ccf36030a98a901811f1151acb8d923635058b3f34283b1c605f880d5f4c9420"
KEY_VERSION = "summary_workbook_2026-08-26"
INVALID_STATUS = "type_conflict_multi_letter_single_select"
NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
ITEM_FIELDS = {"question_id", "question_format", "answer_key_version"}
RESPONSE_FIELDS = {
    "question_id", "response_id", "model", "language", "response_status",
    "is_evaluable", "is_exact_correct_parseable",
}


def worksheet_rows(book, member, strings, fields):
    """Read selected columns by header, preserving the position of sparse XLSX cells."""
    columns = {}
    with book.open(member) as stream:
        for _, row in ET.iterparse(stream, events=("end",)):
            if row.tag != NS + "row":
                continue
            record = {}
            for cell in row.findall(NS + "c"):
                column = cell.attrib["r"].rstrip("0123456789")
                if columns and column not in columns:
                    continue
                value = cell.findtext(NS + "v", "")
                if cell.get("t") == "s":
                    value = strings[int(value)]
                record[column] = value
            row.clear()
            if columns:
                yield {name: record.get(col, "") for col, name in columns.items()}
            else:
                columns = {col: name for col, name in record.items() if name in fields}
                if len(columns) != len(fields) or set(columns.values()) != fields:
                    raise ValueError(f"Missing or repeated column in {member}")


def summarize(items, responses):
    item_formats = {}
    versions = Counter()
    for row in items:
        question, fmt = row["question_id"], row["question_format"]
        if not question or question in item_formats:
            raise ValueError("Missing or duplicate item ID")
        if fmt not in {"single-select", "multiple-select"} or not row["answer_key_version"]:
            raise ValueError("Unknown question format or missing answer key version")
        item_formats[question] = fmt
        versions[row["answer_key_version"]] += 1

    models = set()
    response_ids = set()
    by_pair = defaultdict(dict)
    groups = defaultdict(Counter)
    statuses = Counter()
    for row in responses:
        question, response_id = row["question_id"], row["response_id"]
        model, language = row["model"], row["language"]
        if question not in item_formats or not response_id or response_id in response_ids:
            raise ValueError("Unmatched item ID or missing or repeated response ID")
        if not model or language not in {"zh", "en"}:
            raise ValueError("Missing model or unexpected language")
        pair = by_pair[question, model]
        if language in pair:
            raise ValueError("Repeated response for an item, model, and language")
        status = row["response_status"]
        flag = row["is_evaluable"]
        score = row["is_exact_correct_parseable"]
        evaluable = status == "valid"
        if evaluable:
            if flag != "1" or score not in {"0", "1"}:
                raise ValueError("Valid response has inconsistent evaluability or correctness")
        elif ((status, flag, score) != (INVALID_STATUS, "0", "")
              or item_formats[question] != "single-select"):
            raise ValueError("Unknown response status or inconsistent excluded response")

        models.add(model)
        response_ids.add(response_id)
        pair[language] = evaluable
        statuses[status] += 1
        group = groups[model, language, item_formats[question]]
        group["responses"] += 1
        group["evaluable"] += evaluable
        group["exact_correct"] += score == "1"

    # Unique language keys plus this coverage check also detect pairs missing on both sides.
    if not models or len(by_pair) != len(item_formats) * len(models):
        raise ValueError("Incomplete item-by-model coverage")
    paired_evaluable = Counter()
    for pair in by_pair.values():
        if pair.keys() != {"en", "zh"}:
            raise ValueError("Incomplete English/Chinese response pair")
        paired_evaluable[sum(pair.values())] += 1

    return {
        "items": len(item_formats),
        "item_formats": dict(sorted(Counter(item_formats.values()).items())),
        "key_versions": dict(versions),
        "models": sorted(models),
        "responses": len(response_ids),
        "response_status": dict(sorted(statuses.items())),
        "item_model_pairs": len(by_pair),
        "pairs_by_evaluable_languages": {str(n): paired_evaluable[n] for n in range(3)},
        "strata": [
            {"model": m, "language": lang, "format": fmt, **counts}
            for (m, lang, fmt), counts in sorted(groups.items())
        ],
    }


def audit(path: Path) -> dict:
    raw = path.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    if digest != SHA256:
        raise ValueError(f"SHA-256 differs from the audited workbook: {digest}")
    # The pinned workbook stores Item_metadata and Response_analysis in members 2 and 3.
    with ZipFile(io.BytesIO(raw)) as book:
        shared_strings = ET.fromstring(book.read("xl/sharedStrings.xml"))
        strings = ["".join(item.itertext()) for item in shared_strings]
        result = summarize(
            worksheet_rows(book, "xl/worksheets/sheet2.xml", strings, ITEM_FIELDS),
            worksheet_rows(book, "xl/worksheets/sheet3.xml", strings, RESPONSE_FIELDS),
        )
    if (result["item_formats"] != {"single-select": 1344, "multiple-select": 300}
            or result["key_versions"] != {KEY_VERSION: 1644}
            or len(result["models"]) != 5 or result["responses"] != 16440
            or result["response_status"] != {"valid": 16426, INVALID_STATUS: 14}):
        raise ValueError("Aggregate denominators differ from the pinned release")
    return {"sha256": digest, **result}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("xlsx", type=Path, help="PMCID PMC13792588.1, Multimedia Appendix 7")
    args = parser.parse_args()
    try:
        result = audit(args.xlsx)
    except (OSError, ValueError) as error:
        parser.exit(1, f"{error}\n")
    print(json.dumps(result, indent=2))
