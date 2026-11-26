import pytest

from medbench import twmed
from medbench.datasets import SOURCES, SUITES, _medxpertqa, _tmmlu, _twmed, expand
from medbench.twmed import Row


def test_suites_expand_and_multi_file_sources_hash_all_files():
    assert expand(["@core", "medmcqa", "medqa_twmle"]) == ["medqa_usmle", "medqa_twmle", "pubmedqa", "medmcqa"]
    assert set(SUITES["all"]) == set(SOURCES)
    with pytest.raises(KeyError):
        expand(["@nope"])
    mmlu = SOURCES["mmlu_med"]
    assert len(mmlu.files) == 6 and mmlu.sha256 not in {h for _, h in mmlu.files}


def test_twmed_browse_url_points_to_collection():
    assert SOURCES["twmed_md"].browse_url == "https://github.com/u9401066/medical-benchmark-collection/tree/main/datasets/twmed"


def test_medqa_license_reports_both_sources():
    for name in ("medqa_usmle", "medqa_twmle", "medqa_mcmle"):
        assert SOURCES[name].license == "MedQA repository: MIT. BigBio dataset card: unknown."


def test_new_normalisers():
    src = SOURCES["medxpertqa"]
    it = _medxpertqa([{"id": "Text-0", "question": "Which?\nAnswer Choices: (A) x (B) y", "options": {"A": "x", "B": "y"},
                       "label": "B", "medical_task": "Diagnosis", "body_system": "Skeletal", "question_type": "Reasoning"}], src)[0]
    assert it["question"] == "Which?" and it["answer"] == "B" and it["meta"]["medical_task"] == "Diagnosis"
    tm = _tmmlu([{"question": "問", "A": "a", "B": "b", "C": "c", "D": "d", "answer": "C", "_file": "data/pharmacy_test.csv"}],
                SOURCES["tmmlu_med"])[0]
    assert tm["meta"]["subject"] == "pharmacy" and tm["lang"] == "zh-TW"
    rows = [{"id": "115020-301-0101-001", "group": "twmed_md", "question": "q", "options": {}, "answer": "A", "meta": {"year": 2026}},
            {"id": "115020-305-0401-001", "group": "twmed_rx", "question": "q", "options": {}, "answer": "B", "meta": {}}]
    md = _twmed("twmed_md")(rows, SOURCES["twmed_md"])
    assert [r["id"] for r in md] == ["twmed_md-115020-301-0101-001"]


def _q(n, x, y, stem, opts, page=0):
    rows = [Row(page, y, x, "%d.%s" % (n, stem))]
    rows += [Row(page, y + 10 * (i + 1), x + 10, "%s.%s" % (L, o)) for i, (L, o) in enumerate(zip("ABCD", opts))]
    return rows


def test_twmed_parses_dot_numbered_papers_mixed_papers_and_flags_images():
    rows = [Row(0, 5, 20, "一、申論題"), Row(0, 8, 20, "1.請論述。（20分）"), Row(0, 9, 20, "二、測驗題")]
    rows += _q(1, 20, 10, "下列何者正確？", ["甲", "乙", "丙", "丁"])
    rows += [Row(0, 60, 20, "2.1995 年發生的事件，與下列"), Row(0, 65, 35, "3. 型糖尿病有關的敘述何者正確？")]  # not question 3
    rows += [Row(0, 70 + 10 * i, 30, "%s.選項%d" % (L, i)) for i, L in enumerate("ABCD")]
    rows += _q(3, 20, 120, "下列何者為^99mTc 的半衰期？", ["6 小時", "8 天", "1 小時", "2 天"])
    qs = twmed.parse_questions(rows, images=[(0, 72, 74)], graphics=[(0, 125, 125)])
    assert [q.n for q in qs] == [1, 2, 3] and qs[2].problems == ["table or formula"]
    assert qs[0].stem == "下列何者正確？" and qs[0].options == {"A": "甲", "B": "乙", "C": "丙", "D": "丁"} and not qs[0].problems
    assert qs[1].stem.startswith("1995 年") and "3. 型糖尿病" in qs[1].stem and qs[1].problems == ["image"]
    assert qs[2].options["B"] == "8 天"


def test_twmed_parses_glyph_marked_options_two_per_row():
    rows = []
    for n in range(1, 4):
        y = 100 * n
        rows += [Row(0, y, 41, "%d\t第%d題的題幹？" % (n, n)), Row(0, y + 10, 58, "\ue18c甲%d\t\ue18d乙" % n),
                 Row(0, y + 20, 58, "\ue18e丙\t\ue18f丁"), Row(0, y + 30, 33, "代號：1102")]
    qs = twmed.parse_questions(rows, images=[])
    assert len(qs) == 3 and qs[2].options == {"A": "甲3", "B": "乙", "C": "丙", "D": "丁"} and qs[2].stem == "第3題的題幹？"


def test_twmed_row_marks_superscripts():
    spans = [{"x0": 10, "x1": 40, "y0": 0, "y1": 11, "size": 11, "base": 9, "text": "C.1.7×10"},
             {"x0": 40, "x1": 46, "y0": -1, "y1": 4, "size": 5.5, "base": 3, "text": "10"}]
    assert twmed._row(0, spans).text == "C.1.7×10^10"


def test_twmed_official_answers_apply_corrections():
    pairs = [(1, "A"), (2, "#"), (3, "#"), (4, "#"), (5, "AB"), (6, "#"), (7, "#")]
    ans, why = twmed.official_answers(7, pairs, "第2題答Ａ或Ｂ者均給分，第3題一律給分，第4題更正為Ｃ，"
                                                "第6題除未作答者不給分外，其餘均給分，第7題答Ｂ給分。")
    assert ans == {1: "A", 2: None, 3: None, 4: "C", 5: None, 6: None, 7: "B"}
    assert why[2] == "several answers accepted" and why[3].startswith("voided") and 4 not in why and why[5].startswith("multiple")
    assert twmed.group_of(twmed.profession_of("高等考試_醫師(二)")) == "twmed_md"
    assert twmed.group_of(twmed.profession_of("專技高考_助產師")) == "twmed_rn"
    assert twmed.group_of(twmed.profession_of("高等考試_醫事檢驗師")) == "twmed_allied"
