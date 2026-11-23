"""Benchmark datasets: pinned revisions, SHA-256 checked, normalised to one JSONL item format.

Item format::

    {"id": "medqa_usmle-0001", "dataset": "medqa_usmle", "lang": "en", "kind": "mcq",
     "question": "...", "options": {"A": "...", "B": "...", "C": "...", "D": "..."}, "context": null,
     "answer": "C", "meta": {...}}

``kind`` is ``mcq`` (answer is an option letter, A-D or up to J) or ``yesno`` (answer is yes / no / maybe).
Sources are Hugging Face dataset files at a fixed commit, or a file kept in this repository (the twmed bank, built by
``medbench twmed-build`` from Taiwan's licensing exams). Suites: ``@core`` (the original three), ``@academic``, ``@zh-tw``, ``@all``.
"""
from __future__ import annotations

import csv
import gzip
import hashlib
import json
import re
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Tuple

ROOT = Path(__file__).resolve().parents[1]
HF = "https://huggingface.co/datasets"


@dataclass(frozen=True)
class Source:
    name: str
    title: str
    repo: str        # Hugging Face dataset repo, or "local" for a file in this repository
    revision: str    # git commit of the HF dataset repo (or the bank version for local files)
    files: Tuple[Tuple[str, str], ...]  # (path in the repo, sha256)
    n: int
    lang: str
    kind: str
    license: str
    citation: str
    normalize: Callable[[List[Dict[str, Any]], "Source"], List[Dict[str, Any]]]
    fmt: str = "parquet"  # parquet | jsonl | csv | jsonl.gz (local)

    @property
    def path(self) -> str:
        return self.files[0][0] if len(self.files) == 1 else "%s 等 %d 檔" % (self.files[0][0], len(self.files))

    @property
    def sha256(self) -> str:
        """The file's SHA-256, or for several files the SHA-256 of their concatenated digests."""
        if len(self.files) == 1:
            return self.files[0][1]
        return hashlib.sha256("".join(h for _, h in self.files).encode()).hexdigest()

    def file_url(self, path: str) -> str:
        return "%s/%s/resolve/%s/%s" % (HF, self.repo, self.revision, path)

    @property
    def url(self) -> str:
        return self.file_url(self.files[0][0])

    @property
    def browse_url(self) -> str:
        if self.repo == "local":
            return "https://github.com/u9401066/medqa-bench/tree/main/%s" % self.files[0][0].rsplit("/", 1)[0]
        return "https://huggingface.co/datasets/%s/tree/%s" % (self.repo, self.revision)


def _mcq(rows: List[Dict[str, Any]], src: Source) -> List[Dict[str, Any]]:
    out = []
    for i, r in enumerate(rows):
        opts = {o["key"]: o["value"] for o in r["options"]}
        q = r["question"].strip()
        meta: Dict[str, Any] = {"meta_info": r.get("meta_info")}
        if src.lang == "zh-TW":
            # TWMLE continues some cases across questions ("承上題" = "following the previous question"); the dataset does not
            # keep the link, so these items are scored as given and also reported separately.
            meta["depends_on_previous"] = bool(re.match(r"^\s*(承上題|承上|續上題|同上題)", q))
        out.append({"id": "%s-%04d" % (src.name, i), "dataset": src.name, "lang": src.lang, "kind": "mcq", "question": q,
                    "options": opts, "context": None, "answer": r["answer_idx"], "meta": meta})
    return out


def _pubmedqa(rows: List[Dict[str, Any]], src: Source) -> List[Dict[str, Any]]:
    out = []
    for i, r in enumerate(rows):
        ctx = r["context"]
        parts = []
        for label, text in zip(ctx.get("labels") or [], ctx.get("contexts") or []):
            parts.append("%s: %s" % (label, text) if label else text)
        out.append({"id": "%s-%04d" % (src.name, i), "dataset": src.name, "lang": src.lang, "kind": "yesno",
                    "question": r["question"].strip(), "options": None, "context": "\n".join(parts), "answer": r["final_decision"],
                    "meta": {"pubid": r["pubid"]}})
    return out


def _letter(i: int) -> str:
    return "ABCDEFGHIJ"[i]


def _medmcqa(rows: List[Dict[str, Any]], src: Source) -> List[Dict[str, Any]]:
    return [{"id": "%s-%04d" % (src.name, i), "dataset": src.name, "lang": src.lang, "kind": "mcq", "question": r["question"].strip(),
             "options": {"A": r["opa"].strip(), "B": r["opb"].strip(), "C": r["opc"].strip(), "D": r["opd"].strip()}, "context": None,
             "answer": _letter(int(r["cop"])),
             "meta": {"subject": r.get("subject_name"), "topic": r.get("topic_name"), "choice_type": r.get("choice_type"), "source_id": r.get("id")}}
            for i, r in enumerate(rows)]


def _mmlu(rows: List[Dict[str, Any]], src: Source) -> List[Dict[str, Any]]:
    return [{"id": "%s-%04d" % (src.name, i), "dataset": src.name, "lang": src.lang, "kind": "mcq", "question": r["question"].strip(),
             "options": {_letter(j): str(c).strip() for j, c in enumerate(r["choices"])}, "context": None, "answer": _letter(int(r["answer"])),
             "meta": {"subject": r["subject"]}}
            for i, r in enumerate(rows)]


def _medxpertqa(rows: List[Dict[str, Any]], src: Source) -> List[Dict[str, Any]]:
    out = []
    for i, r in enumerate(rows):
        q = re.split(r"\n\s*Answer Choices:", r["question"])[0].strip()  # the options are also given separately
        out.append({"id": "%s-%04d" % (src.name, i), "dataset": src.name, "lang": src.lang, "kind": "mcq", "question": q,
                    "options": {k: v.strip() for k, v in r["options"].items()}, "context": None, "answer": r["label"],
                    "meta": {"source_id": r["id"], "medical_task": r.get("medical_task"), "body_system": r.get("body_system"),
                             "question_type": r.get("question_type")}})
    return out


def _tmmlu(rows: List[Dict[str, Any]], src: Source) -> List[Dict[str, Any]]:
    return [{"id": "%s-%04d" % (src.name, i), "dataset": src.name, "lang": src.lang, "kind": "mcq", "question": r["question"].strip(),
             "options": {k: r[k].strip() for k in "ABCD"}, "context": None, "answer": r["answer"].strip(),
             "meta": {"subject": r["_file"].rsplit("/", 1)[-1].replace("_test.csv", "")}}
            for i, r in enumerate(rows)]


def _twmed(group: str) -> Callable[[List[Dict[str, Any]], Source], List[Dict[str, Any]]]:
    def norm(rows: List[Dict[str, Any]], src: Source) -> List[Dict[str, Any]]:
        return [{"id": "%s-%s" % (src.name, r["id"]), "dataset": src.name, "lang": "zh-TW", "kind": "mcq", "question": r["question"],
                 "options": r["options"], "context": None, "answer": r["answer"], "meta": r["meta"]}
                for r in rows if r["group"] == group]
    return norm


MMLU_MED = ["anatomy", "clinical_knowledge", "college_biology", "college_medicine", "medical_genetics", "professional_medicine"]
MMLU_SHA = ["cb88f5920b67ab290dd23a825f8e3826d01d8f48d99ad4931a8b0003a952a211", "7bd3de302db35c6e9adb311ef40b2fb15ffe02ada17667119d9fb30fe393a44e",
            "5b6920ddbbb40ee6efd1e6c8814be9fd03d24c9e1e1dbd4b02325e2d454a6a82", "f21b3166975dbc14dff5940df41479bc28853008303c50a070d430fc59468f9c",
            "f5535475f3afc3479697355679f2b615603fe90a58e8e5b6a98e50ccf07171b9", "8c1c18b16c9865bf52b7cd997c4d05346f914441645459fac8c5b2f78d9ebac9"]
TMMLU_MED = [("basic_medical_science", "2eed947dd88cddb58a82b602707f495a44adb01699081e86dee69518eebd1b86"),
             ("pharmacology", "316899a0b69d1bd7bcd74d94bb2dcbe901dc2830034bfbe8009c41dd30ac30ea"),
             ("pharmacy", "ef4620acdfe8ad40747c3989975924c8bb5ba6d7b7f1ed56dbc249b05b350387"),
             ("clinical_psychology", "080ca79b55a4532e858e5d6fdbc6e2cc20c7fee4c3d4bda79e8bc54d872ed375"),
             ("dentistry", "d6e63812f733fd3176b83e70af6206c53d91fd4eeb175e209b819eab826533bd"),
             ("traditional_chinese_medicine_clinical_medicine", "abf62e059e749511ecfe18791f7676f1dc71c1613bcce079a7f1cfab7707eee8"),
             ("optometry", "f5e77bb4334a1f1d311f1c90cabaf48b5c2ec3c2d95367f767b0cfe8153e771f"),
             ("occupational_therapy_for_psychological_disorders", "028f7107b50e16d87be1c4a2ba56455c40c8a63e8a4e945778af626320afc040")]
TWMED_FILE = ("datasets/twmed/twmed-v1.jsonl.gz", "169fabd030cf24939a33ac89920670b1d819a570f5d56c56668ad7bd35ab580a")
TWMED_N = {"twmed_md": 2872, "twmed_dent": 2645, "twmed_tcm": 2821, "twmed_rx": 2518, "twmed_rn": 3072, "twmed_allied": 18600}
TWMED_TITLES = {"twmed_md": "醫師（一）（二）", "twmed_dent": "牙醫師（一）（二）", "twmed_tcm": "中醫師（一）（二）", "twmed_rx": "藥師（一）（二）",
                "twmed_rn": "護理師、助產師", "twmed_allied": "醫事檢驗、放射、物理／職能／呼吸／語言治療、營養、心理、聽力、驗光、公衛等"}
TWMED_LICENSE = "不受著作權保護（著作權法 §9 I ⑤ 依法令舉行之考試試題）；來源：考選部考畢試題"
TWMED_CITATION = "考選部 考畢試題查詢平臺 https://wwwq.moex.gov.tw/exam/wFrmExamQandASearch.aspx（2024–2026），medqa-bench twmed-v1"


_BIGBIO = "484a6c066fe8e75c83edea0c88b5169316714fcd"
_MEDQA_CITE = "Jin et al., What Disease does this Patient Have? (MedQA), Applied Sciences 2021"

SOURCES: Dict[str, Source] = {s.name: s for s in [
    Source("medqa_usmle", "MedQA-USMLE (4 options), test", "bigbio/med_qa", _BIGBIO,
           (("med_qa_en_4options_source/test-00000-of-00001.parquet", "b50b49fad2642c10ed343c6174d5ab0cb8efad434e7b66465ac471094eb57deb"),),
           1273, "en", "mcq", "MIT (MedQA)", _MEDQA_CITE, _mcq),
    Source("medqa_twmle", "MedQA-TWMLE (Taiwan medical licensing exam, Traditional Chinese), test", "bigbio/med_qa", _BIGBIO,
           (("med_qa_tw_source/test-00000-of-00001.parquet", "9756921fcff39ee482d8e06488b4ff32c26c9b966ac4c67c07f854da583f34b0"),),
           1413, "zh-TW", "mcq", "MIT (MedQA)", _MEDQA_CITE, _mcq),
    Source("pubmedqa", "PubMedQA (expert-labeled, reasoning-required)", "qiaojin/PubMedQA", "9001f2853fb87cab8d220904e0de81ac6973b318",
           (("pqa_labeled/train-00000-of-00001.parquet", "3d56bd1abc11884579ecc3aab9dd3cdfce8b7cf54715daeca93b8022b7be231c"),),
           1000, "en", "yesno", "MIT", "Jin et al., PubMedQA: A Dataset for Biomedical Research Question Answering, EMNLP 2019", _pubmedqa),
    # academic
    Source("medmcqa", "MedMCQA (Indian AIIMS/NEET-PG entrance exams), validation", "openlifescienceai/medmcqa",
           "91c6572c454088bf71b679ad90aa8dffcd0d5868",
           (("data/validation-00000-of-00001.parquet", "b768a1ea34afc9f80d3106d9b21f80fa8a00ec450a1f6cd641af72ca9e591021"),),
           4183, "en", "mcq", "Apache-2.0", "Pal et al., MedMCQA, CHIL 2022", _medmcqa),
    Source("mmlu_med", "MMLU medical subjects (anatomy, clinical knowledge, college biology/medicine, medical genetics, "
           "professional medicine), test", "cais/mmlu", "c30699e8356da336a370243923dbaf21066bb9fe",
           tuple(("%s/test-00000-of-00001.parquet" % sub, h) for sub, h in zip(MMLU_MED, MMLU_SHA)),
           1089, "en", "mcq", "MIT", "Hendrycks et al., Measuring Massive Multitask Language Understanding, ICLR 2021", _mmlu),
    Source("medxpertqa", "MedXpertQA Text (expert-level, 10 options), test", "TsinghuaC3I/MedXpertQA", "7e7c465a68eb2b866926bfa59c8c9d17a8daba65",
           (("Text/test.jsonl", "07ea977f7e326909b51c883b65f6ad7f399fc6db07408ef3630f4e3048ec71b2"),),
           2450, "en", "mcq", "MIT", "Zuo et al., MedXpertQA: Benchmarking Expert-Level Medical Reasoning, ICML 2025", _medxpertqa, "jsonl"),
    Source("medqa_mcmle", "MedQA-MCMLE (mainland China medical licensing exam, Simplified Chinese, 4 options), test", "bigbio/med_qa",
           _BIGBIO, (("med_qa_zh_4options_source/test-00000-of-00001.parquet", "ac9ddd6cf0e45f4ab224f4b1014c5945fbdb1ca67ad6a057ce5b0e4929c7a55c"),),
           3426, "zh-CN", "mcq", "MIT (MedQA)", _MEDQA_CITE, _mcq),
    # Traditional Chinese
    Source("tmmlu_med", "TMMLU+ medical subjects (Taiwan exams: basic medical science, pharmacology, pharmacy, clinical psychology, "
           "dentistry, TCM clinical medicine, optometry, occupational therapy), test", "ikala/tmmluplus",
           "639a64db464b4661feb91817b9edfe43932bdf18", tuple(("data/%s_test.csv" % sub, h) for sub, h in TMMLU_MED),
           4151, "zh-TW", "mcq", "MIT", "Tam et al., An Improved Traditional Chinese Evaluation Suite for Foundation Model (TMMLU+), 2024",
           _tmmlu, "csv"),
] + [Source(name, "twmed %s：考選部專技高考 2024–2026（%s）" % (name, TWMED_TITLES[name]), "local", "twmed-v1", (TWMED_FILE,),
            TWMED_N[name], "zh-TW", "mcq", TWMED_LICENSE, TWMED_CITATION, _twmed(name), "jsonl.gz") for name in TWMED_N]}

DEFAULT_SUITE = ["medqa_usmle", "medqa_twmle", "pubmedqa"]
SUITES: Dict[str, List[str]] = {
    "core": DEFAULT_SUITE,
    "academic": DEFAULT_SUITE + ["medmcqa", "mmlu_med", "medxpertqa", "medqa_mcmle"],
    "zh-tw": ["medqa_twmle", "tmmlu_med"] + list(TWMED_N),
}
SUITES["all"] = list(dict.fromkeys(SUITES["academic"] + SUITES["zh-tw"]))


def expand(names: Iterable[str]) -> List[str]:
    """Dataset names; "@suite" expands to the suite's datasets (order kept, duplicates removed)."""
    out: List[str] = []
    for n in names:
        n = n.strip()
        if not n:
            continue
        if n.startswith("@"):
            if n[1:] not in SUITES:
                raise KeyError("unknown suite %s (have: %s)" % (n, ", ".join("@" + k for k in SUITES)))
            out += SUITES[n[1:]]
        else:
            out.append(n)
    return list(dict.fromkeys(out))


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _read(path: Path, fmt: str) -> List[Dict[str, Any]]:
    if fmt == "parquet":
        import pyarrow.parquet as pq

        return pq.read_table(path).to_pylist()
    if fmt == "csv":
        with open(path, encoding="utf-8", newline="") as f:
            return list(csv.DictReader(f))
    opener = gzip.open if fmt == "jsonl.gz" else open
    with opener(path, "rt", encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def _raw_path(data_dir: Path, src: Source, i: int, path: str) -> Path:
    if src.repo == "local":
        return ROOT / path
    ext = "." + src.fmt
    if len(src.files) == 1:
        return data_dir / "raw" / ("%s%s" % (src.name, ext))  # the original cache name of the single-file sources
    return data_dir / "raw" / src.name / ("%02d-%s" % (i, path.replace("/", "_")))


def prepare(data_dir: Path, names: Iterable[str] = DEFAULT_SUITE) -> Dict[str, Dict[str, Any]]:
    """Download (if needed), verify and normalise; writes <data_dir>/<name>.jsonl. Returns {name: info}."""
    data_dir.mkdir(parents=True, exist_ok=True)
    info = {}
    for name in expand(names):
        src = SOURCES[name]
        rows: List[Dict[str, Any]] = []
        for i, (path, want) in enumerate(src.files):
            raw = _raw_path(data_dir, src, i, path)
            if src.repo != "local" and (not raw.exists() or sha256(raw) != want):
                raw.parent.mkdir(parents=True, exist_ok=True)
                tmp = raw.with_name(raw.name + ".part")
                urllib.request.urlretrieve(src.file_url(path), tmp)
                tmp.rename(raw)
            digest = sha256(raw)
            if digest != want:
                raise RuntimeError("%s: %s sha256 %s does not match the pinned %s" % (name, path, digest, want))
            part = _read(raw, src.fmt)
            if len(src.files) > 1:
                for r in part:
                    r["_file"] = path
            rows += part
        items = src.normalize(rows, src)
        if len(items) != src.n:
            raise RuntimeError("%s: %d items, expected %d" % (name, len(items), src.n))
        out = data_dir / ("%s.jsonl" % name)
        with open(out, "w", encoding="utf-8") as f:
            for it in items:
                f.write(json.dumps(it, ensure_ascii=False) + "\n")
        info[name] = {"title": src.title, "repo": src.repo, "revision": src.revision, "path": src.path, "sha256": src.sha256,
                      "files": [{"path": p, "sha256": h} for p, h in src.files],
                      "n": len(items), "lang": src.lang, "kind": src.kind, "license": src.license, "items_sha256": sha256(out)}
    return info


def load(data_dir: Path, name: str) -> List[Dict[str, Any]]:
    with open(data_dir / ("%s.jsonl" % name), encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]
