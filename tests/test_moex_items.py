import csv
import gzip
import hashlib
import json

import pytest

from medbench import moex_items as ledger
from medbench.twmed import Row


@pytest.mark.parametrize("original,corrected,note,mode,expected", [
    # MOEX 113180/101/0103 Q28: original A, corrected #, official note 第28題一律給分。
    ("A", "#", "一律給分。", "single", {"kind": "all_credit"}),
    ("A", "#", "答Ｂ者給分。", "single", {"kind": "replacement", "choices": ["B"]}),
    ("A", "#", "答Ｂ或Ｃ者均給分。", "single", {"kind": "any_of", "choices": ["B", "C"], "unlisted_combinations": "requires_review"}),
    ("B", "#", "答A或答B者均給分，", "single", {"kind": "any_of", "choices": ["A", "B"], "unlisted_combinations": "requires_review"}),
    # 115020/301/0101 Q66 awards A alone, D alone, and the two together.
    (None, "＃", "答Ａ或Ｄ或AD者均給分，", "single", {"kind": "any_of", "choices": ["A", "D", "AD"], "unlisted_combinations": "requires_review"}),
    ("AB", None, "", "multiple", {"kind": "all_of", "choices": ["A", "B"], "partial_credit": "requires_review"}),
    ("AB", None, "", "single", {"kind": "unresolved"}),
    ("AB", None, "", None, {"kind": "unresolved"}),
    ("B", "#", "除未作答者外，其餘均給分。", "single", {"kind": "conditional_credit"}),
    ("A", "#", "同時選A及B者才給分。", "single", {"kind": "all_of", "choices": ["A", "B"], "partial_credit": "requires_review"}),
    ("AC", "#", "選答之選項中包括Ｃ選項者，均得該題全部分數。", "multiple",
     {"kind": "conditional_credit", "includes_for_full_credit": ["C"], "other_responses": "requires_review"}),
    ("A", "#", "依另函辦理。", "single", {"kind": "unresolved"}),
    ("A", "C", "答B給分。", "single", {"kind": "unresolved"}),
    ("D", "#", "", "single", {"kind": "unresolved"}),
    (None, "C", "", "single", {"kind": "single", "choices": ["C"]}),
])
def test_scoring_rules(original, corrected, note, mode, expected):
    assert ledger.scoring_rule(original, corrected, note, mode) == expected


def test_mixed_sections_kept_on_key_mismatch(monkeypatch):
    rows = [Row(0, 10, 20, "甲、申論題"), Row(0, 30, 20, "一、說明判讀依據。"),
            Row(1, 10, 20, "乙、測驗題"), Row(1, 30, 20, "1. 如圖所示。"),
            Row(1, 55, 20, "A. 甲 B. 乙 C. 丙 D. 丁")]
    monkeypatch.setattr(ledger, "pdf_rows", lambda path: (rows, [(1, 60, 80)], []))
    key = {"counts": {"single": 2}, "entries": {1: {"token": "B", "page": 1}, 2: {"token": "A", "page": 1}},
           "notes": {}, "raw_notes": [], "issues": [], "page_text": {1: "單選題數：2"}}
    monkeypatch.setattr(ledger, "read_key", lambda path: key)
    record = ledger.extract_paper("113001-1-01", {"Q": "q", "S": "s"}, {"Q", "S"})
    essay, objective, unparsed = record["items"]
    assert (essay["section"], essay["pages"], essay["question"]) == ("essay", [1], "說明判讀依據。")
    assert {"image", "refers_to_figure"} <= set(objective["flags"])
    assert objective["pages"] == [2]
    assert unparsed["flags"] == ["unparsed_question"]
    assert all(i["rule"] == {"kind": "unresolved"} for i in record["items"])
    assert record["status"] == "partial" and "S_question_key_mismatch" in record["issues"]
    assert record["source_pages"]["Q"][2].startswith("乙、測驗題")


def test_essay_without_key(monkeypatch):
    rows = [Row(0, 10, 20, "甲、申論題"), Row(0, 30, 20, "1.說明原因。"), Row(1, 10, 20, "2.說明依據。")]
    monkeypatch.setattr(ledger, "pdf_rows", lambda path: (rows, [], []))
    out = ledger.extract_paper("113001-1-01", {"Q": "q"}, {"Q"})
    assert [(item["section"], item["pages"]) for item in out["items"]] == [("essay", [1]), ("essay", [2])]
    assert not out["key_notes"] and all(i["rule"]["kind"] == "unresolved" for i in out["items"])


def test_same_length_wrong_printed_key_withholds_rule(monkeypatch):
    rows = [Row(0, 10, 20, "代號：1201"), Row(0, 20, 20, "本試題為單一選擇題"),
            Row(0, 30, 20, "1. 如圖。"), Row(0, 60, 20, "A. 甲 B. 乙 C. 丙 D. 丁")]
    monkeypatch.setattr(ledger, "pdf_rows", lambda path: (rows, [], []))
    key = {"counts": {"unspecified": 1}, "entries": {1: {"token": "B", "page": 1}}, "notes": {}, "raw_notes": [],
           "issues": [], "page_text": {1: "試題代號：4101"}}
    monkeypatch.setattr(ledger, "read_key", lambda path: key)
    record = ledger.extract_paper("113001-1-01", {"Q": "q", "S": "s"}, {"Q", "S"})
    assert record["issues"] == ["S_printed_paper_code_mismatch"]
    assert record["items"][0]["rule"]["kind"] == "unresolved"
    assert record["items"][0]["key_evidence"]["S"]["token"] == "B"


def test_mixed_paper_code_stops_at_row_boundary(monkeypatch):
    # 112110-103-0301 prints 10310 for the written section, 1103 for the MCQs.
    rows = [Row(0, 10, 20, "代號：10310"), Row(0, 20, 20, "甲、申論題部分"),
            Row(0, 30, 20, "一、說明原因"), Row(1, 10, 20, "乙、測驗題部分：（50分）\t代號：1103"),
            Row(1, 20, 20, "1本試題為單一選擇題"), Row(1, 30, 20, "1. 題幹？"),
            Row(1, 50, 20, "A. 甲 B. 乙 C. 丙 D. 丁")]
    key = {"counts": {"single": 1}, "entries": {1: {"token": "C", "page": 1}},
           "notes": {}, "raw_notes": [], "issues": [], "page_text": {1: "試題代號：1103"}}
    monkeypatch.setattr(ledger, "pdf_rows", lambda path: (rows, [], []))
    monkeypatch.setattr(ledger, "read_key", lambda path: key)
    record = ledger.extract_paper("112110-103-0301", {"Q": "q", "S": "s"}, {"Q", "S"})
    assert record["issues"] == []
    assert record["items"][-1]["rule"] == {"kind": "single", "choices": ["C"]}


def test_pending_corrected_key_blocks_use_of_original(monkeypatch):
    rows = [Row(0, 20, 20, "1. 題幹"), Row(0, 40, 20, "A. 甲 B. 乙 C. 丙 D. 丁")]
    key = {"counts": {"single": 1}, "entries": {1: {"token": "B", "page": 1}}, "notes": {}, "raw_notes": [],
           "issues": [], "page_text": {1: "單選題數：1"}}
    monkeypatch.setattr(ledger, "pdf_rows", lambda path: (rows, [], []))
    monkeypatch.setattr(ledger, "read_key", lambda path: key)
    record = ledger.extract_paper("113001-1-01", {"Q": "q", "S": "s"}, {"Q", "S", "M"})
    assert record["issues"] == ["M_unavailable"]
    assert record["items"][0]["key_evidence"]["S"]["token"] == "B"
    assert record["items"][0]["rule"]["kind"] == "unresolved"
    assert record["separate_correction_notices"] == "not_reconciled"
    corrected_only = ledger.extract_paper("113001-1-01", {"Q": "q", "M": "m"}, {"Q", "S", "M"})
    assert corrected_only["issues"] == ["S_unavailable"] and corrected_only["status"] == "partial"
    assert corrected_only["items"][0]["rule"] == {"kind": "single", "choices": ["B"]}
    assert set(corrected_only["items"][0]["key_evidence"]) == {"M"}


def test_historical_number_column_can_have_space_before_tab(monkeypatch):
    rows = [Row(0, 20, 20, "本試題為單一選擇題"), Row(0, 40, 20, "1 \t題幹一？"),
            Row(0, 50, 30, "A. 甲 B. 乙 C. 丙 D. 丁"), Row(0, 60, 20, "2　\t題幹二？"),
            Row(0, 70, 30, "A. 戊 B. 己 C. 庚 D. 辛")]
    key = {"counts": {"unspecified": 2}, "entries": {1: {"token": "B", "page": 1}, 2: {"token": "#", "page": 1}},
           "notes": {2: {"page": 1, "text": "第2題答C或D者均給分", "rule": "答C或D者均給分"}},
           "raw_notes": [], "issues": [], "page_text": {1: "題數：2題"}}
    monkeypatch.setattr(ledger, "pdf_rows", lambda path: (rows, [], []))
    monkeypatch.setattr(ledger, "read_key", lambda path: key)
    paper = ledger.extract_paper("099130-101-200", {"Q": "q", "M": "m"}, {"Q", "M"})
    assert paper["issues"] == [] and paper["question_instruction_mode"] == "single"
    first, second = paper["items"]
    assert (first["question"], second["question"], second["options"]["D"]) == ("題幹一？", "題幹二？", "辛")
    assert second["rule"] == {"kind": "any_of", "choices": ["C", "D"], "unlisted_combinations": "requires_review"}


@pytest.mark.parametrize(("prefix", "assigned"), [("", True), ("更正紀錄：", True), ("另有條件：", False)])
def test_key_cell_geometry_and_note(tmp_path, prefix, assigned):
    mupdf = pytest.importorskip("pymupdf")
    doc = mupdf.open()
    page = doc.new_page()
    def word(x, y, text):
        page.insert_text((x, y), text, fontname="china-t", fontsize=10)
    word(10, 20, "單選題數：3")
    for x, label in [(10, "題號"), (100, "第1題"), (180, "第2題"), (260, "第3題")]:
        word(x, 40, label)
    word(10, 65, "答案")
    word(110, 65, "Ａ")
    word(270, 65, "＃")
    word(10, 100, "備註：" + prefix + "第3題一律給分。")
    path = tmp_path / "key.pdf"
    doc.save(path)
    doc.close()
    key = ledger.read_key(path)
    assert set(key["entries"]) == {1, 3}
    assert ledger.compact(key["entries"][3]["token"]) == "#"
    if assigned:
        assert key["issues"] == ["incomplete_number_grid"]
        assert ledger.compact(key["notes"][3]["rule"]) == "一律給分。"
    else:
        assert key["issues"] == ["incomplete_number_grid", "unassigned_correction_note"]
        assert not key["notes"]


def test_resume_and_ambiguous_attachments(tmp_path, monkeypatch):
    pytest.importorskip("pymupdf")
    doc = tmp_path / "exam.pdf"
    doc.write_bytes(b"unique PDF fixture")
    sha = hashlib.sha256(doc.read_bytes()).hexdigest()
    rows = [{"paper_id": "113001-1-01", "year_roc": "113", "exam_code": "113001", "asset_type": "Q",
             "subject_name": "醫學", "source_url": f"https://wwwq.moex.gov.tw/exam/?q={q}",
             "sha256": sha, "status": "verified", "format": "pdf", "local_path": doc.name} for q in [1, 2]]
    manifest, out = tmp_path / "files.tsv", tmp_path / "out"
    with manifest.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=rows[0], delimiter="\t")
        writer.writeheader()
        writer.writerows(rows)
    ledger.build(manifest, tmp_path, out)
    shard = out / "113" / "113001.jsonl.gz"
    with gzip.open(shard, "rt", encoding="utf-8") as stream:
        paper = json.load(stream)
    assert len(paper["sources"]) == 2
    assert "Q_ambiguous_attachments" in paper["issues"]
    assert paper["roles_not_listed_in_current_manifest"] == ["M", "S"]
    assert paper["status"] == "unresolved"
    monkeypatch.setattr(ledger, "extract_paper", lambda *args: pytest.fail("resumption repeated extraction"))
    before = shard.read_bytes()
    ledger.build(manifest, tmp_path, out)
    assert shard.read_bytes() == before
