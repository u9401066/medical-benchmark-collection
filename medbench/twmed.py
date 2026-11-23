"""twmed: a Traditional Chinese medical MCQ bank built from Taiwan's national licensing exams (考選部 考畢試題).

Every multiple-choice paper of the medical professions' exams (醫師, 牙醫師, 中醫師, 藥師, 護理師, 助產師, 醫事檢驗師, 醫事放射師,
物理/職能/呼吸/語言治療師, 營養師, 心理師, 聽力師, 驗光人員, 公共衛生師, 牙體技術師, 法醫師) of the chosen years is downloaded from
the Ministry of Examination (questions, answer key and corrected key, as published), parsed, and kept only when the item is
unambiguous as text:

* the official (corrected) answer is exactly one of A-D: items voided (一律給分), with several accepted answers or multi-select
  answers are dropped;
* no image inside the question, and no reference to a figure (如圖, 下圖, 箭頭 ...) - the bank is text only;
* the paper parses completely: question numbers 1..N with N equal to the answer key's count, four options each; otherwise the
  whole paper is left out and logged;
* duplicates (the same paper listed under two categories, or the same question in two papers) are kept once.

Legal basis: exam questions held under law are not subject to copyright in Taiwan (著作權法 第 9 條 第 1 項 第 5 款). The Ministry
asks users to cite the source and keep the data intact: every item keeps its exam, category, subject, number and the URLs of
the original PDFs, and the build log lists every excluded item with its reason.

    medbench twmed-build --years 2024,2025,2026 --out datasets/twmed      # network: ~1 request/s to wwwq.moex.gov.tw
"""
from __future__ import annotations

import gzip
import hashlib
import http.cookiejar
import json
import re
import time
import unicodedata
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

MOEX = "https://wwwq.moex.gov.tw/exam/"
SEARCH = MOEX + "wFrmExamQandASearch.aspx"
FILE = MOEX + "wHandExamQandA_File.ashx?t={t}&code={code}&c={c}&s={s}&q=1"
UA = "Mozilla/5.0 (medqa-bench twmed builder; +https://github.com/u9401066/medqa-bench)"
MEDICAL_EXAM = re.compile(r"醫師|藥師|護理師|醫事|營養師|心理師|治療師|助產|驗光|聽力師|牙|公共衛生師")
EXCLUDED_CATEGORY = re.compile(r"社會工作師|獸醫師")
# dataset name -> profession prefixes (the category name without its exam-level prefix, e.g. 高等考試_醫師(一) -> 醫師(一))
GROUPS: List[Tuple[str, str]] = [
    ("twmed_md", r"^醫師"), ("twmed_dent", r"^牙醫師"), ("twmed_tcm", r"^中醫師"), ("twmed_rx", r"^藥師"),
    ("twmed_rn", r"^(護理師|助產師)"), ("twmed_allied", r"."),
]
FIGURE = re.compile(r"(如|下|上|附|右|左|前)(列|方|述)?[^，。？?、\n]{0,6}(圖|照片|影像|相片|X光片)|圖[（(]?[一二三四五六七八九十0-9]|圖中|圖示|附圖|箭頭|箭號|下表圖")
DEPENDS = re.compile(r"^\s*(承上題|承上|續上題|同上題|承前題)")
HEADER_ROW = re.compile(r"^\s*(代\s*號|頁\s*次)\s*[:：]|請接背面|背面尚有|以下空白|請翻頁")
CIRCLED = {chr(0xE129 + i): chr(0x2460 + i) for i in range(10)}  # Gaaiho papers: PUA glyphs for ①-⑩
# Text set in the Symbol font comes as U+F0xx (0xF000 + the Symbol-encoding byte); Adobe Symbol encoding -> Unicode
_SYM_UPPER = "ΑΒΧΔΕΦΓΗΙϑΚΛΜΝΟΠΘΡΣΤΥςΩΞΨΖ"
_SYM_LOWER = "αβχδεφγηιϕκλμνοπθρστυϖωξψζ"
SYMBOL = {**{0xF041 + i: c for i, c in enumerate(_SYM_UPPER)}, **{0xF061 + i: c for i, c in enumerate(_SYM_LOWER)},
          **{0xF020 + i: chr(0x20 + i) for i in range(0x20)}, 0xF022: "∀", 0xF024: "∃", 0xF027: "∋", 0xF02A: "∗", 0xF02D: "−",
          0xF040: "≅", 0xF05B: "[", 0xF05C: "∴", 0xF05D: "]", 0xF05E: "⊥", 0xF05F: "_", 0xF07B: "{", 0xF07C: "|", 0xF07D: "}",
          0xF07E: "~", 0xF0A2: "′", 0xF0A3: "≤", 0xF0A4: "⁄", 0xF0A5: "∞", 0xF0A6: "ƒ", 0xF0AB: "↔", 0xF0AC: "←", 0xF0AD: "↑",
          0xF0AE: "→", 0xF0AF: "↓", 0xF0B0: "°", 0xF0B1: "±", 0xF0B2: "″", 0xF0B3: "≥", 0xF0B4: "×", 0xF0B5: "∝", 0xF0B6: "∂",
          0xF0B7: "•", 0xF0B8: "÷", 0xF0B9: "≠", 0xF0BA: "≡", 0xF0BB: "≈", 0xF0BC: "…", 0xF0D6: "√", 0xF0D7: "⋅", 0xF0D8: "¬",
          0xF0D9: "∧", 0xF0DA: "∨", 0xF0E5: "∑"}
LETTERS = "ABCD"


def group_of(profession: str) -> str:
    for name, pat in GROUPS:
        if re.search(pat, profession):
            return name
    return "twmed_allied"


def profession_of(category: str) -> str:
    return category.split("_", 1)[-1].strip()


# ---------------------------------------------------------------------------------------------------------------- crawling

class Moex:
    """The Ministry of Examination's past-paper search (ASP.NET postbacks), one request per ``delay`` seconds."""

    def __init__(self, delay: float = 1.0):
        self.delay = delay
        self.op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
        self.op.addheaders = [("User-Agent", UA)]
        self._last = 0.0

    def _get(self, url: str, data: Optional[Dict[str, str]] = None) -> bytes:
        for attempt in range(4):
            wait = self.delay - (time.time() - self._last)
            if wait > 0:
                time.sleep(wait)
            self._last = time.time()
            try:
                body = urllib.parse.urlencode(data).encode() if data is not None else None
                with self.op.open(url, body, timeout=60) as r:
                    return r.read()
            except OSError:
                if attempt == 3:
                    raise
                time.sleep(5 * (attempt + 1))
        raise RuntimeError("unreachable")

    @staticmethod
    def _hidden(page: str) -> Dict[str, str]:
        return dict(re.findall(r'<input type="hidden" name="([^"]+)" id="[^"]*" value="([^"]*)"', page))

    def _year_page(self, year: int) -> str:
        page = self._get(SEARCH).decode("utf-8")
        f = self._hidden(page)
        f.update({"ctl00$holderContent$wUctlExamYearStart$ddlExamYear": str(year),
                  "ctl00$holderContent$wUctlExamYearEnd$ddlExamYear": str(year), "ctl00$holderContent$btnYear": "依考試年度設定考試簡稱"})
        return self._get(SEARCH, f).decode("utf-8")

    def exams(self, year: int) -> List[Tuple[str, str]]:
        page = self._year_page(year)
        sel = re.search(r'name="ctl00\$holderContent\$ddlExamCode"[^>]*>(.*?)</select>', page, re.S)
        opts = re.findall(r'<option[^>]*value="(\d+)"[^>]*>([^<]*)</option>', sel.group(1) if sel else "")
        return [(v, unescape(t)) for v, t in opts if MEDICAL_EXAM.search(t)]

    def subjects(self, year: int, code: str) -> List[Dict[str, str]]:
        page = self._year_page(year)  # the exam code must be one of this page's options (event validation)
        f = self._hidden(page)
        f.update({"ctl00$holderContent$wUctlExamYearStart$ddlExamYear": str(year),
                  "ctl00$holderContent$wUctlExamYearEnd$ddlExamYear": str(year),
                  "ctl00$holderContent$ddlExamCode": code, "ctl00$holderContent$btnSearch": "查詢"})
        res = self._get(SEARCH, f).decode("utf-8")
        title = re.search(r'<td style="vertical-align:text-top;">([^<]+)</td>', res)
        cats = dict(re.findall(r'<label for="ctl00_holderContent_chk_%s_(\d+)">([^<]+)</label>' % code, res))
        out = []
        for c, s, name, rest in re.findall(
                r'<label for="ctl00_holderContent_chk_%s_(\d+)_(\d+)" class="exam-title">([^<]+)</label>(.*?)</td>' % code, res, re.S):
            files = "".join(sorted(set(re.findall(r"t=([QSM])&amp;", rest))))
            out.append({"code": code, "exam": unescape(title.group(1)) if title else "", "c": c, "category": unescape(cats.get(c, "")),
                        "s": s, "subject": unescape(name), "files": files})
        return out

    def fetch(self, code: str, c: str, s: str, t: str, cache: Path) -> Optional[Path]:
        path = cache / code / ("%s_%s_%s.pdf" % (c, s, t))
        if path.exists() and path.stat().st_size > 0:
            return path
        data = self._get(FILE.format(t=t, code=code, c=c, s=s))
        if not data.startswith(b"%PDF"):
            return None
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return path


def unescape(s: str) -> str:
    import html

    return html.unescape(s).strip()


# ---------------------------------------------------------------------------------------------------------------- parsing

@dataclass
class Row:
    page: int
    y: float
    x: float
    text: str


def _clean(t: str) -> str:
    t = "".join(CIRCLED.get(ch, ch) for ch in t)
    t = t.replace("\xa0", " ").replace("\u3000", " ")
    return t


Box = Tuple[int, float, float]  # page, y0, y1


def pdf_rows(path: Path) -> Tuple[List[Row], List[Box], List[Box]]:
    """Visual rows (spans whose vertical extents overlap, left to right, a tab where there is a gap; superscripts as ^x), image
    boxes, and vector graphics that carry meaning in a question: table rules and fraction bars (horizontal lines >= 15 pt that are
    not page-wide, vertical lines >= 10 pt)."""
    import pymupdf

    rows: List[Row] = []
    images: List[Box] = []
    graphics: List[Box] = []
    with pymupdf.open(str(path)) as doc:
        for pno, page in enumerate(doc):
            spans = []
            for b in page.get_text("dict")["blocks"]:
                if b["type"] != 0:
                    continue
                for line in b["lines"]:
                    for sp in line["spans"]:
                        if sp["text"].strip():
                            # vertical extent from the baseline and font size: some glyphs (e.g. ×) report a box several lines tall
                            x0, _, x1, _ = sp["bbox"]
                            base, size = sp["origin"][1], sp["size"]
                            text = sp["text"].translate(SYMBOL) if "symbol" in sp.get("font", "").lower() else sp["text"]
                            spans.append({"x0": x0, "x1": x1, "y0": base - 0.9 * size, "y1": base + 0.25 * size, "size": size,
                                          "base": base, "text": text})
            spans.sort(key=lambda s: s["y0"])
            groups: List[List[Dict[str, Any]]] = []
            for sp in spans:
                c = (sp["y0"] + sp["y1"]) / 2
                g = groups[-1] if groups else None
                if g is not None:
                    gy0, gy1 = min(s["y0"] for s in g), max(s["y1"] for s in g)
                    if gy0 - 1 <= c <= gy1 + 1 or sp["y0"] - 1 <= (gy0 + gy1) / 2 <= sp["y1"] + 1:
                        g.append(sp)
                        continue
                groups.append([sp])
            rows += [_row(pno, g) for g in groups]
            for im in page.get_image_info():
                images.append((pno, im["bbox"][1], im["bbox"][3]))
            for d in page.get_drawings():
                r = d["rect"]
                if (r.height <= 2 and 15 <= r.width < 0.6 * page.rect.width) or (r.width <= 2 and 10 <= r.height < 0.3 * page.rect.height):
                    graphics.append((pno, r.y0, r.y1))
    rows.sort(key=lambda r: (r.page, round(r.y), r.x))
    return rows, images, graphics


def _row(pno: int, spans: List[Dict[str, Any]]) -> Row:
    spans = sorted(spans, key=lambda s: s["x0"])
    big = max(s["size"] for s in spans)

    def raised(s: Dict[str, Any], o: Optional[Dict[str, Any]]) -> bool:
        """s is smaller than its touching neighbour o and sits above o's baseline: a superscript (10^-4, ^14C)."""
        if o is None or s["size"] >= 0.9 * o["size"] or s["base"] >= o["base"] - 1.5:
            return False
        return min(abs(s["x0"] - o["x1"]), abs(o["x0"] - s["x1"])) < 2.5

    text, end = "", None
    for i, s in enumerate(spans):
        if end is not None and s["x0"] - end > 6:
            text += "\t"
        t = s["text"]
        prev = spans[i - 1] if i > 0 else None
        nxt = spans[i + 1] if i + 1 < len(spans) else None
        if t.strip() and (raised(s, prev) or raised(s, nxt)):
            t = "^" + t.strip()
        text += t
        end = s["x1"]
    main = [s for s in spans if s["size"] >= 0.9 * big]
    return Row(pno, min(s["y0"] for s in main), min(s["x0"] for s in spans), _clean(text))


def _join(a: str, b: str) -> str:
    a, b = a.rstrip(), b.strip()
    if not a:
        return b
    if a[-1].isascii() and a[-1].isalnum() and b[:1].isascii() and b[:1].isalnum():
        return a + " " + b
    return a + b


def _norm(t: str) -> str:
    t = re.sub(r"[ \t]+", " ", t.replace("\t", " ")).strip()
    return t


@dataclass
class Question:
    n: int
    page: int
    y: float
    text: str = ""
    stem: str = ""
    options: Dict[str, str] = field(default_factory=dict)
    end: Tuple[int, float] = (10 ** 6, 0.0)
    problems: List[str] = field(default_factory=list)


QSTART_DOT = re.compile(r"^\s*(\d{1,3})\s*[.．](?!\d)\s*(.*)$", re.S)
QSTART_TAB = re.compile(r"^\s*(\d{1,3})\t(.*)$", re.S)
QSTART_ANY = re.compile(r"^\s*(\d{1,3})\s*[.．]\s*(.*)$", re.S)


def _pua_markers(rows: List[Row]) -> Dict[str, str]:
    """Gaaiho papers mark options with four consecutive private-use glyphs; find them by frequency at segment starts."""
    from collections import Counter

    c: Counter = Counter()
    for r in rows:
        for seg in r.text.split("\t"):
            seg = seg.lstrip()
            if seg and "\ue000" <= seg[0] <= "\uf8ff":
                c[ord(seg[0])] += 1
    for base, _ in c.most_common():
        if all(c.get(base + i, 0) >= max(3, c[base] // 2) for i in range(4)):
            return {chr(base + i): LETTERS[i] for i in range(4)}
    return {}


def parse_questions(rows: List[Row], images: List[Box], graphics: Iterable[Box] = ()) -> List[Question]:
    """Questions 1..N of the multiple-choice part, each with its stem, options A-D and the problems that exclude it."""
    # the multiple-choice part of a mixed paper starts after its heading (essay questions come first and are numbered too)
    start = 0
    for i, r in enumerate(rows):
        if re.match(r"^\s*[一二三四甲乙丙丁][、.．]\s*測驗(式)?題", r.text):
            start = i + 1
    marks = _pua_markers(rows)
    qs: List[Question] = []
    # the question-number column: where rows like "2." / "3\t" start (numbers may be right-aligned: "10" starts left of "9")
    xs = sorted(r.x for r in rows[start:] if (QSTART_DOT.match(r.text) or QSTART_TAB.match(r.text))
                and 2 <= int((QSTART_DOT.match(r.text) or QSTART_TAB.match(r.text)).group(1)) <= 9)
    from collections import Counter

    votes = Counter(round(x) for x in xs)
    x0: Optional[float] = float(max(votes, key=lambda x: (votes[x], -x))) if votes else None
    for r in rows[start:]:
        if HEADER_ROW.search(r.text):
            continue
        expected = len(qs) + 1
        in_column = x0 is None or x0 - 14 <= r.x <= x0 + 6
        m = QSTART_DOT.match(r.text) or QSTART_TAB.match(r.text)
        if not m and x0 is not None and abs(r.x - x0) < 3:  # "54.1995 年..." / "1.^14C ...": a number right after the dot
            m = QSTART_ANY.match(r.text)
        if m and int(m.group(1)) == expected and in_column:
            if x0 is None:
                x0 = r.x
            if qs:
                qs[-1].end = (r.page, r.y)
            qs.append(Question(expected, r.page, r.y, m.group(2)))
            continue
        if qs:
            qs[-1].text += "\n" + r.text
    graphics = list(graphics)
    for q in qs:
        _split_options(q, marks)
        for boxes, label in ((images, "image"), (graphics, "table or formula")):
            if any((q.page, q.y - 2) <= (pno, (y0 + y1) / 2) < q.end for pno, y0, y1 in boxes):
                q.problems.append(label)
    return qs


def _split_options(q: Question, marks: Dict[str, str]) -> None:
    t = q.text
    for ch, letter in marks.items():
        t = t.replace(ch, "\n%s." % letter)
    pos: Dict[str, List[int]] = {L: [m.start(1) for m in re.finditer(r"(?:^|[\n\t ])(%s)\s?[.．]" % L, t)] for L in LETTERS}
    chosen: List[int] = []
    for L in LETTERS:
        after = chosen[-1] if chosen else -1
        nxt = [p for p in pos[L] if p > after]
        if not nxt:
            q.problems.append("options")
            q.stem = _norm(" ".join(t.split("\n")))
            return
        chosen.append(nxt[0])
    stem_lines = t[:chosen[0]].split("\n")
    stem = ""
    for ln in stem_lines:
        stem = _join(stem, ln)
    q.stem = _norm(stem)
    for i, L in enumerate(LETTERS):
        end = chosen[i + 1] if i + 1 < 4 else len(t)
        body = re.sub(r"^%s\s?[.．]" % L, "", t[chosen[i]:end].strip())
        txt = ""
        for ln in body.split("\n"):
            txt = _join(txt, ln)
        q.options[L] = _norm(txt)
    if not q.stem:
        q.problems.append("empty stem")
    if any(not v for v in q.options.values()):
        q.problems.append("empty option")
    # private-use glyphs, or math set in a font whose glyphs come out as unrelated scripts (Syriac ... Sinhala) or U+FFFD
    if re.search(r"[\ue000-\uf8ff\u0590-\u0dff\ufffd]", q.stem + "".join(q.options.values())):
        q.problems.append("unmapped glyph")


FW = {chr(0xFF21 + i): chr(0x41 + i) for i in range(26)}


def answer_rows(path: Path) -> Tuple[int, List[Tuple[int, str]], str]:
    """(expected count, [(number, answer token)], notes) from an answer or corrected-answer PDF."""
    import pymupdf

    words = []
    with pymupdf.open(str(path)) as doc:
        for pno, page in enumerate(doc):
            for w in page.get_text("words"):
                words.append((pno, w[1], w[0], w[4]))
    words.sort(key=lambda w: (w[0], round(w[1]), w[2]))
    lines: List[List[str]] = []
    last = None
    for pno, y, x, t in words:
        if last is None or pno != last[0] or abs(y - last[1]) > 3:
            lines.append([])
        lines[-1].append(t)
        last = (pno, y)
    text = "\n".join(" ".join(ln) for ln in lines)
    m = re.search(r"(?:單選)?題\s*數\s*[:：]\s*(\d+)", text)
    expected = int(m.group(1)) if m else 0
    pairs: List[Tuple[int, str]] = []
    for i, ln in enumerate(lines):
        head = "".join(ln[:1])
        if head.startswith(("題號", "題序")) and i + 1 < len(lines) and "".join(lines[i + 1][:1]).startswith("答案"):
            nums = [int(n) for n in re.findall(r"\d+", " ".join(ln))]
            toks = [t for t in " ".join(lines[i + 1]).replace("答案", " ").split() if t]
            toks = ["".join(FW.get(ch, ch) for ch in t) for t in toks]
            for n, a in zip(nums, toks):
                pairs.append((n, a))
    notes = ""
    m = re.search(r"備\s*註\s*[:：](.*)", text, re.S)
    if m:
        notes = re.sub(r"\s+", "", m.group(1))
    return expected, pairs, notes


def official_answers(expected: int, pairs: List[Tuple[int, str]], notes: str) -> Tuple[Dict[int, Optional[str]], Dict[int, str]]:
    """{number: single answer or None} and {number: why it has none} after the published corrections."""
    ans: Dict[int, Optional[str]] = {}
    why: Dict[int, str] = {}
    for n, a in pairs:
        a = a.replace("＃", "#")
        if re.fullmatch(r"[A-D]", a):
            ans[n] = a
        elif a == "#":
            ans[n] = None
            why[n] = "corrected"
        else:
            ans[n] = None
            why[n] = "multiple answers (%s)" % a
    for part in re.split(r"(?=第\d+題)", "".join(FW.get(ch, ch) for ch in notes)):  # one note per question number
        m = re.match(r"第(\d+)題", part)
        if not m:
            continue
        n = int(m.group(1))
        single = re.search(r"(?:更正為|改為|答)([A-D])(?![A-D])(?:者)?給分|(?:更正為|改為)([A-D])(?![A-D])", part)
        if "一律給分" in part or "送分" in part or "其餘均給分" in part:
            ans[n], why[n] = None, "voided (一律給分)"
        elif "或" in part or "均給分" in part:
            ans[n], why[n] = None, "several answers accepted"
        elif single:
            ans[n] = single.group(1) or single.group(2)
            why.pop(n, None)
    return ans, why


# ---------------------------------------------------------------------------------------------------------------- build

def _key(text: str) -> str:
    return re.sub(r"[\s\W_]+", "", unicodedata.normalize("NFKC", text)).lower()


def _reason(r: str) -> str:
    if r.startswith("duplicate of"):
        return "duplicate in the bank"
    if r.startswith("also in"):
        return "also in MedQA-TW / TMMLU+"
    return r.split(" (")[0]


def sha256_file(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def known_questions(data_dir: Path) -> Tuple[Dict[str, str], List[Dict[str, str]]]:
    """Normalised question text -> source, for the overlap check: MedQA-TW (all splits) and TMMLU+'s medical subjects (all splits)."""
    import csv

    import pyarrow.parquet as pq

    from .datasets import _BIGBIO, HF, TMMLU_MED, sha256

    known: Dict[str, str] = {}
    refs: List[Dict[str, str]] = []
    raw = data_dir / "raw" / "overlap"
    raw.mkdir(parents=True, exist_ok=True)
    files = [("bigbio/med_qa", _BIGBIO, "med_qa_tw_source/%s-00000-of-00001.parquet" % sp, "MedQA-TW %s" % sp)
             for sp in ("train", "validation", "test")]
    files += [("ikala/tmmluplus", "639a64db464b4661feb91817b9edfe43932bdf18", "data/%s_%s.csv" % (sub, sp), "TMMLU+ %s %s" % (sub, sp))
              for sub, _ in TMMLU_MED for sp in ("dev", "val", "test", "train")]
    for repo, rev, path, label in files:
        local = raw / ("%s__%s" % (repo.replace("/", "_"), path.replace("/", "_")))
        if not local.exists():
            try:
                urllib.request.urlretrieve("%s/%s/resolve/%s/%s" % (HF, repo, rev, path), local)
            except OSError:
                continue  # e.g. a TMMLU+ subject without a train split
        refs.append({"repo": repo, "revision": rev, "path": path, "sha256": sha256(local)})
        if path.endswith(".parquet"):
            qs = [r["question"] for r in pq.read_table(local).to_pylist()]
        else:
            with open(local, encoding="utf-8", newline="") as f:
                qs = [r["question"] for r in csv.DictReader(f)]
        for q in qs:
            known.setdefault(_key(q), label)
    return known, refs


def build(years: Iterable[int], out: Path, cache: Path, known: Optional[Dict[str, str]] = None, delay: float = 1.0,
          log=print, overlap_sources: Optional[List[Dict[str, str]]] = None) -> Dict[str, Any]:
    """Download, parse and filter; writes <out>/twmed-v1.jsonl.gz, sources.tsv and build_log.json. ``known`` maps normalised
    question text -> id of an existing benchmark item (e.g. MedQA-TWMLE); such questions are dropped as overlap."""
    years = list(years)
    moex = Moex(delay)
    items: List[Dict[str, Any]] = []
    excluded: List[Dict[str, Any]] = []
    papers: List[Dict[str, Any]] = []
    sources: List[str] = ["exam\tcategory\tsubject\tfile\turl\tsha256"]
    seen_pdf: Dict[str, str] = {}
    seen_q: Dict[str, str] = {}
    known = known or {}
    for year in years:
        for code, title in moex.exams(year):
            subs = moex.subjects(year, code)
            log("%s %s: %d subjects" % (code, title[:40], len(subs)))
            for sub in subs:
                prof = profession_of(sub["category"])
                rec = {k: sub[k] for k in ("code", "c", "s", "category", "subject")}
                if EXCLUDED_CATEGORY.search(sub["category"]):
                    continue
                if "S" not in sub["files"] or "Q" not in sub["files"]:
                    papers.append({**rec, "status": "no answer key (essay paper)"})
                    continue
                qpdf = moex.fetch(code, sub["c"], sub["s"], "Q", cache)
                kpdf = (moex.fetch(code, sub["c"], sub["s"], "M", cache) if "M" in sub["files"] else None) or \
                    moex.fetch(code, sub["c"], sub["s"], "S", cache)
                if not qpdf or not kpdf:
                    papers.append({**rec, "status": "download failed"})
                    continue
                for t, p in (("Q", qpdf), ("M" if kpdf.name.endswith("_M.pdf") else "S", kpdf)):
                    sources.append("\t".join([code, sub["category"], sub["subject"], t,
                                              FILE.format(t=t, code=code, c=sub["c"], s=sub["s"]), sha256_file(p)]))
                digest = sha256_file(qpdf)
                if digest in seen_pdf:
                    papers.append({**rec, "status": "same paper as %s" % seen_pdf[digest]})
                    continue
                seen_pdf[digest] = "%s/%s/%s" % (code, sub["c"], sub["s"])
                try:
                    rows, images, graphics = pdf_rows(qpdf)
                    qs = parse_questions(rows, images, graphics)
                    expected, pairs, notes = answer_rows(kpdf)
                except Exception as e:  # a broken PDF must not stop the build; it is logged
                    papers.append({**rec, "status": "parse error: %s" % e})
                    continue
                answers, why = official_answers(expected, pairs, notes)
                n_key = expected or len(pairs)
                if not qs or len(qs) != n_key or len(pairs) < n_key:
                    papers.append({**rec, "status": "mismatch: %d questions parsed, %d in the key (%d answers)" % (len(qs), n_key, len(pairs))})
                    continue
                kept = 0
                for q in qs:
                    qid = "%s-%s-%s-%03d" % (code, sub["c"], sub["s"], q.n)
                    reasons = list(q.problems)
                    if answers.get(q.n) is None:
                        reasons.append(why.get(q.n, "no answer"))
                    if FIGURE.search(q.stem + " " + " ".join(q.options.values())):
                        reasons.append("refers to a figure")
                    k = _key(q.stem + "|" + "|".join(q.options[L] for L in LETTERS)) if not q.problems else ""
                    if k and k in seen_q:
                        reasons.append("duplicate of %s" % seen_q[k])
                    if k and _key(q.stem) in known:
                        reasons.append("also in %s" % known[_key(q.stem)])
                    if reasons:
                        excluded.append({"id": qid, "reasons": reasons})
                        continue
                    seen_q[k] = qid
                    kept += 1
                    items.append({
                        "id": qid, "group": group_of(prof), "lang": "zh-TW", "kind": "mcq", "question": q.stem,
                        "options": q.options, "answer": answers[q.n],
                        "meta": {"exam_code": code, "exam": sub["exam"], "year": int(code[:3]) + 1911,
                                 "session": (re.search(r"第([一二三四])次", sub["exam"]) or [None, ""])[1],
                                 "category": sub["category"], "profession": re.sub(r"[（(][一二三][)）]$", "", prof),
                                 "subject": sub["subject"], "number": q.n,
                                 "depends_on_previous": bool(DEPENDS.match(q.stem)),
                                 "source": FILE.format(t="Q", code=code, c=sub["c"], s=sub["s"])},
                    })
                papers.append({**rec, "status": "ok", "questions": len(qs), "kept": kept})
                log("  %s %s %s: %d/%d kept" % (code, sub["category"], sub["subject"][:24], kept, len(qs)))
    out.mkdir(parents=True, exist_ok=True)
    data = "".join(json.dumps(it, ensure_ascii=False, sort_keys=True) + "\n" for it in sorted(items, key=lambda x: x["id"]))
    with gzip.GzipFile(out / "twmed-v1.jsonl.gz", "wb", mtime=0) as f:  # mtime 0: the same items give the same bytes
        f.write(data.encode("utf-8"))
    (out / "sources.tsv").write_text("\n".join(sources) + "\n", encoding="utf-8")
    from collections import Counter

    log_doc = {"years": list(years), "built_at": time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime()),
               "items": len(items), "excluded": len(excluded), "papers_parsed": sum(1 for p in papers if p["status"] == "ok"),
               "by_group": dict(Counter(it["group"] for it in items)),
               "by_year": dict(Counter(str(it["meta"]["year"]) for it in items)),
               "exclusion_reasons": dict(Counter(_reason(r) for e in excluded for r in e["reasons"])),
               "overlap_sources": overlap_sources or [], "papers": papers, "excluded_items": excluded}
    (out / "build_log.json").write_text(json.dumps(log_doc, ensure_ascii=False, indent=1), encoding="utf-8")
    return {k: v for k, v in log_doc.items() if k not in ("papers", "excluded_items")}
