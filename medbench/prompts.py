"""Zero-shot prompts (one user message, no system prompt, no examples) and final-answer extraction.

Every prompt asks the model to end with a line ``Answer: X`` (the same English token in every language), so one parser
serves all datasets. Only the final answer (``content``) is scored; text inside the reasoning is never used.
"""
from __future__ import annotations

import re
from typing import Any, Dict, Optional

# v1.1 = v1 + a Simplified Chinese template and options beyond D (MedXpertQA has A-J). The prompts of the v1 datasets
# (MedQA-USMLE, MedQA-TWMLE, PubMedQA) are byte-identical to v1.
PROMPT_VERSION = "v1.1"

MCQ_EN = (
    "Answer the following multiple-choice question about medicine. Exactly one option is correct.\n\n"
    "{question}\n\n{options}\n\n"
    "Think it through, then give your final answer on the last line in the form \"Answer: X\", where X is one of {letters}."
)
MCQ_ZH_TW = (
    "請回答以下醫學單選題，只有一個正確選項。\n\n"
    "{question}\n\n{options}\n\n"
    "請先思考，最後一行以「Answer: X」的格式作答，X 為 {letters} 其中之一。"
)
MCQ_ZH_CN = (
    "请回答以下医学单选题，只有一个正确选项。\n\n"
    "{question}\n\n{options}\n\n"
    "请先思考，最后一行以「Answer: X」的格式作答，X 为 {letters} 其中之一。"
)
YESNO_EN = (
    "Read the abstract (without its conclusion) and answer the research question with yes, no or maybe.\n\n"
    "Abstract:\n{context}\n\nQuestion: {question}\n\n"
    "Think it through, then give your final answer on the last line in the form \"Answer: yes\", \"Answer: no\" or \"Answer: maybe\"."
)

TEMPLATES = {"MCQ_EN (MedQA-USMLE, MedMCQA, MMLU, MedXpertQA)": MCQ_EN, "MCQ_ZH_TW (MedQA-TWMLE, TMMLU+, twmed)": MCQ_ZH_TW,
             "MCQ_ZH_CN (MedQA-MCMLE)": MCQ_ZH_CN, "YESNO_EN (PubMedQA)": YESNO_EN}


def build_prompt(item: Dict[str, Any]) -> str:
    if item["kind"] == "yesno":
        return YESNO_EN.format(context=item["context"], question=item["question"])
    letters = list(item["options"])
    opts = "\n".join("%s. %s" % (k, v) for k, v in item["options"].items())
    joined = ", ".join(letters[:-1]) + " or " + letters[-1]
    tpl = MCQ_ZH_CN if item["lang"] == "zh-CN" else MCQ_ZH_TW if item["lang"].startswith("zh") else MCQ_EN
    return tpl.format(question=item["question"], options=opts, letters=joined if tpl is MCQ_EN else "、".join(letters))


_MARK = r"(?i:answer|final answer)|答案|最終答案|最终答案|正確答案|正确答案"
_SEP = r"\s*(?:(?i:is)|:|：|為|为|是)?\s*[*_`\s]*"


_FULLWIDTH = {0xFF08: "(", 0xFF09: ")", **{0xFF21 + i: chr(0x41 + i) for i in range(10)}}  # （）and Ａ-Ｊ


def _strip(text: str) -> str:
    return text.translate(_FULLWIDTH)


def parse_mcq(text: Optional[str], letters: str = "ABCD") -> Optional[str]:
    """Option letter from a final answer; the last explicit 'Answer: X' wins, then weaker patterns.

    Letters must be upper case ("the answer is a beta blocker" is not option A), except a lower-case letter that ends the
    line right after the marker ("Answer: b")."""
    if not text:
        return None
    t = _strip(text)
    L = "[%s]" % letters
    patterns = [
        r"(?:%s)%s\(?(%s)\)?(?![A-Za-z])" % (_MARK, _SEP, L),               # Answer: C / 答案：C / Final answer is (C)
        r"(?:%s)%s\(?(%s)\)?[.。]?\s*$" % (_MARK, _SEP, L.lower()),        # Answer: c   (only at the end of a line)
        r"\\boxed\{\s*\(?(%s)\)?\s*\}" % L,                              # \boxed{C}
        r"(?:(?i:option|choice)|選項|选项|選|选)\s*\(?(%s)\)?(?![A-Za-z])" % L,  # option C / 選項 C / 选项 C
        r"^\s*\**\(?(%s)\)?\**[.)：:]?\s*$" % L,                           # a line that is only "C" / "(C)" / "C."
    ]
    for p in patterns:
        hits = re.findall(p, t, flags=re.MULTILINE)
        if hits:
            return hits[-1].upper()
    return None


def parse_yesno(text: Optional[str]) -> Optional[str]:
    if not text:
        return None
    t = _strip(text)
    hits = re.findall(r"(?:%s)%s((?i:yes|no|maybe))\b" % (_MARK, _SEP), t)
    if hits:
        return hits[-1].lower()
    last = [ln for ln in t.strip().splitlines() if ln.strip()][-1:]
    if last:
        m = re.findall(r"\b(yes|no|maybe)\b", last[0], flags=re.IGNORECASE)
        if len(set(x.lower() for x in m)) == 1:
            return m[-1].lower()
    return None


def parse(item: Dict[str, Any], text: Optional[str]) -> Optional[str]:
    if item["kind"] == "yesno":
        return parse_yesno(text)
    return parse_mcq(text, "".join(item["options"]))
