import pytest

from medbench.prompts import build_prompt, parse, parse_mcq, parse_yesno

MCQ = {"kind": "mcq", "lang": "en", "question": "Q?", "options": {"A": "a", "B": "b", "C": "c", "D": "d"}}
TW = {"kind": "mcq", "lang": "zh-TW", "question": "問?", "options": {"A": "甲", "B": "乙", "C": "丙", "D": "丁"}}
YN = {"kind": "yesno", "lang": "en", "question": "Does X?", "context": "BACKGROUND: ...", "options": None}


@pytest.mark.parametrize("text,want", [
    ("The best choice is clearly ...\nAnswer: C", "C"),
    ("**Answer: B**", "B"),
    ("Answer: (D) Lisinopril", "D"),
    ("Final answer is A.", "A"),
    ("答案：C", "C"),
    ("最終答案為 B", "B"),
    ("Answer：Ｃ", "C"),
    ("I first thought Answer: A, but on reflection\nAnswer: D", "D"),
    ("The answer is \\boxed{B}", "B"),
    ("Option C is correct.", "C"),
    ("C", "C"),
    ("Answer: E", None),
    ("The answer is a beta blocker such as metoprolol.", None),
    ("Answer: b", "B"),
    ("Answer: c.\n", "C"),
    ("I would choose a different approach", None),
    ("A good answer needs more information.", None),
    ("", None),
    (None, None),
])
def test_parse_mcq(text, want):
    assert parse_mcq(text) == want


@pytest.mark.parametrize("text,want", [
    ("...\nAnswer: yes", "yes"),
    ("**Answer: No**", "no"),
    ("Answer: maybe", "maybe"),
    ("The evidence suggests\nyes", "yes"),
    ("Yes or no? It depends", None),
    ("", None),
])
def test_parse_yesno(text, want):
    assert parse_yesno(text) == want


def test_prompts():
    p = build_prompt(MCQ)
    assert "A. a\nB. b\nC. c\nD. d" in p and 'A, B, C or D' in p and p.rstrip().endswith("C or D.")
    t = build_prompt(TW)
    assert "A. 甲" in t and "A、B、C、D" in t and "Answer: X" in t
    y = build_prompt(YN)
    assert "BACKGROUND: ..." in y and "Does X?" in y and parse(YN, "Answer: Yes") == "yes"
    assert parse(MCQ, "Answer: b") == "B"


def test_v1_prompts_are_unchanged_and_new_languages_and_letters_work():
    import hashlib

    digests = [hashlib.sha256(build_prompt(it).encode()).hexdigest()[:16] for it in (MCQ, TW, YN)]
    assert digests == ["c47980222d0ea223", "9d0e3f8d84ed96de", "52518e521e78dd37"]  # prompt v1 of the core datasets
    cn = build_prompt({"kind": "mcq", "lang": "zh-CN", "question": "问?", "options": {"A": "甲", "B": "乙"}})
    assert cn.startswith("请回答以下医学单选题") and "A、B" in cn
    ten = {"kind": "mcq", "lang": "en", "question": "Q?", "options": {k: k.lower() for k in "ABCDEFGHIJ"}}
    assert "I or J" in build_prompt(ten)
    assert parse(ten, "Answer: J") == "J" and parse(ten, "最终答案为 Ｈ") == "H" and parse(MCQ, "Answer: J") is None
