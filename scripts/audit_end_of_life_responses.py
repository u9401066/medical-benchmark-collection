"""Count question, evidence and response records in the fixed BMC Palliative Care attachments."""

import argparse
from collections import Counter
from hashlib import sha256
from io import BytesIO
import json
from pathlib import Path
import re

from docx import Document
from docx.oxml.ns import qn
from docx.table import Table
from docx.text.paragraph import Paragraph


DIGESTS = {
    "questions": "0c192b41dd7e28d7b9dc09a158faddfa7aca5c4686639ced0a8a873b98a33e73",
    "risks": "f242fa89fac57cc3083a5d68f7786b4a7b7dda114e3d1b5eb6a13f63ccf9f03c",
    "responses": "86be772b572ab06e0fa83eccc9df02ed2cbd08e29e4a56dc0beb4d988ce1dd1e",
}


def opened(path, key):
    raw = path.read_bytes()
    if sha256(raw).hexdigest() != DIGESTS[key]:
        raise ValueError(
            f"{path.name}: SHA-256 does not match the fixed publisher attachment"
        )
    return Document(BytesIO(raw))


def table_rows(table):
    return [[cell.text.strip() for cell in row.cells] for row in table.rows]


def question_id(text):
    match = re.fullmatch(r"Q0*([1-9][0-9]*)", text)
    if not match:
        raise ValueError(f"Unexpected question ID {text}")
    return int(match[1])


def question_reference_map(doc):
    question_rows, reference_rows = [table_rows(t)[1:] for t in doc.tables]
    references = {row[0] for row in reference_rows}
    mapping = {
        question_id(row[0]): [ref.strip() for ref in row[5].split(";")]
        for row in question_rows
    }
    if len(mapping) != len(question_rows) or len(references) != len(reference_rows):
        raise ValueError("Question or reference IDs are not unique")
    for key, links in mapping.items():
        if not links or len(set(links)) != len(links) or set(links) - references:
            raise ValueError(f"Invalid reference mapping for Q{key}")
    return mapping, references


def answer_records(doc):
    """Record headers and actual answer text blocks follow one another in document order."""
    records = {}
    pairs = set()
    current = question = None
    marker = content = 0

    def finish():
        if current is None:
            return
        key, qid, model = current
        if marker != 1 or not content or key in records or (qid, model) in pairs:
            raise ValueError(f"{key}: missing answer body or repeated response record")
        records[key] = (qid, model)
        pairs.add((qid, model))

    for element in doc.element.body:
        if element.tag == qn("w:tbl"):
            cells = dict(table_rows(Table(element, doc)))
            if "record_id" not in cells:
                continue
            finish()
            qid = question_id(cells["question_id"])
            record = cells["record_id"]
            if (
                qid != question
                or not record.startswith(f"Q{qid}_")
                or not cells["model"]
            ):
                raise ValueError(
                    f"{record}: response does not match its question heading"
                )
            current = record, qid, cells["model"]
            marker = content = 0
        elif element.tag == qn("w:p"):
            text = Paragraph(element, doc).text.strip()
            heading = re.match(r"^(Q[0-9]+)\.\s", text)
            if heading:
                finish()
                current = None
                question = question_id(heading[1])
            elif current is not None:
                if text == "answer_text:":
                    marker += 1
                elif marker:
                    content += len(text)
    finish()
    return records


def selected_risks(doc, records):
    aliases = {"ChatGPT-5.3 Instant": "GPT-5.3 mini instant"}
    cases = set()
    available = set(records.values())
    for row in table_rows(doc.tables[2])[1:]:
        case = question_id(row[1]), aliases.get(row[0], row[0])
        if case not in available or case in cases:
            raise ValueError(
                f"Unknown or repeated response in the qualitative sample: {case}"
            )
        cases.add(case)
    totals = Counter(model for _, model in cases)
    expected = {
        aliases.get(row[0], row[0]): int(row[1])
        for row in table_rows(doc.tables[1])[1:]
    }
    if totals != expected:
        raise ValueError("Qualitative sample counts do not match the summary table")
    return dict(sorted(totals.items()))


def audit(source_questions, source_risks, source_responses):
    mapping, references = question_reference_map(source_questions)
    records = answer_records(source_responses)
    models = {model for _, model in records.values()}
    if len(models) != 5 or set(records.values()) != {
        (q, m) for q in mapping for m in models
    }:
        raise ValueError(
            "Every question requires exactly one response for each of the five model settings"
        )
    risks = selected_risks(source_risks, records)
    return {
        "source_sha256": DIGESTS,
        "questions": len(mapping),
        "reference_records": len(references),
        "question_reference_links": sum(map(len, mapping.values())),
        "referenced_ids": len({ref for links in mapping.values() for ref in links}),
        "response_records_with_text": len(records),
        "responses_by_model_label": dict(
            sorted(Counter(model for _, model in records.values()).items())
        ),
        "qualitative_examples": sum(risks.values()),
        "qualitative_examples_by_label": risks,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for key in DIGESTS:
        parser.add_argument(key, type=Path)
    args = parser.parse_args()
    try:
        report = audit(*(opened(getattr(args, name), name) for name in DIGESTS))
    except (OSError, ValueError, KeyError) as error:
        parser.exit(1, f"{error}\n")
    print(json.dumps(report, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
