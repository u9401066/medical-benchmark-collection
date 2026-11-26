import pytest
from docx import Document

from scripts.audit_end_of_life_responses import answer_records


def add_response(doc, key, model, body):
    table = doc.add_table(rows=3, cols=2)
    for row, name, value in zip(
        table.rows,
        ("record_id", "question_id", "model"),
        (key, key.split("_", 1)[0], model),
        strict=True,
    ):
        row.cells[0].text = name
        row.cells[1].text = value
    doc.add_paragraph("answer_text:")
    if body:
        doc.add_paragraph(body)


def test_counts_real_answer_blocks_and_checks_the_last_record():
    doc = Document()
    doc.add_paragraph("Q1. A fixture question")
    add_response(doc, "Q1_m1", "model 1", "text")
    doc.add_paragraph("Q2. Another fixture question")
    add_response(doc, "Q2_m2", "model 2", "")
    with pytest.raises(ValueError, match="Q2_m2"):
        answer_records(doc)
    doc.add_paragraph("now present")
    assert answer_records(doc) == {"Q1_m1": (1, "model 1"), "Q2_m2": (2, "model 2")}
