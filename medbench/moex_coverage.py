"""Reconcile a published index, download manifest and extracted paper ledger."""
from __future__ import annotations

import argparse
import csv
import gzip
import io
import json
from collections import Counter, defaultdict
from pathlib import Path

from .moex_archive import atomic, read_tsv

RULES = ("single", "replacement", "any_of", "all_of", "all_credit", "conditional_credit", "published_rubric", "unresolved")
COUNTS = ["indexed_files", "verified_files", "failed_files", "files_without_receipt", "changed_from_prior",
          "Q_listed", "Q_verified", "S_listed", "S_verified", "M_listed", "M_verified",
          "item_records", "stale_item_records", "items_with_text", "items_with_original_key", "items_with_corrected_key",
          "ocr_assets", "ocr_draft_pages", "ocr_empty_pages", "ocr_error_pages", "ocr_stale_pages",
          *["rule_" + k for k in RULES]]


def write(path, fields, rows):
    out = io.StringIO(newline="")
    writer = csv.DictWriter(out, fields, delimiter="\t", lineterminator="\n", extrasaction="ignore")
    writer.writeheader()
    writer.writerows(rows)
    atomic(path, out.getvalue().encode("utf-8"))


def paper_id(row):
    return "-".join(row[k] for k in ("exam_code", "category_code", "subject_code"))


def ocr_counts(folder, manifest):
    counts = defaultdict(Counter)
    if folder is None:
        return counts
    sources = {r.get("asset_id"): r for r in manifest if r["asset_type"] == "Q"}
    for path in sorted(folder.glob("*/*.jsonl.gz")):
        with gzip.open(path, "rt", encoding="utf-8") as stream:
            pages = set()
            counted_source = False
            for raw in stream:
                page = json.loads(raw)
                ref, seq = page["source"], page["pdf_page"]
                if seq in pages or page["asset_id"] != path.name.removesuffix(".jsonl.gz"):
                    raise ValueError(f"Ambiguous OCR page identity in {path}")
                source = sources.get(page["asset_id"])
                if not source or source["paper_id"] != ref["paper_id"]:
                    raise ValueError(f"OCR source missing from official inventory in {path}")
                current = counts[source["paper_id"]]
                if source.get("status") != "verified" or source.get("sha256") != ref["sha256"]:
                    current["ocr_stale_pages"] += 1
                else:
                    if not counted_source:
                        current["ocr_assets"] += 1
                        counted_source = True
                    label = {"ocr_draft": "ocr_draft_pages", "no_text_recognized": "ocr_empty_pages", "ocr_error": "ocr_error_pages"}.get(page["status"])
                    if label:
                        current[label] += 1
                pages.add(seq)
    return counts


def ledger_counts(path):
    stats = {}
    for shard in sorted(path.glob("*/*.jsonl.gz")):
        with gzip.open(shard, "rt", encoding="utf-8") as source:
            for line in source:
                paper = json.loads(line)
                pid = paper["paper_id"]
                if pid in stats:
                    raise ValueError(f"duplicate extracted paper {pid}")
                counts = Counter()
                for item in paper["items"]:
                    counts["item_records"] += 1
                    counts["items_with_text"] += bool(item.get("question"))
                    for role, field in (("S", "items_with_original_key"), ("M", "items_with_corrected_key")):
                        counts[field] += bool(item.get("key_evidence", {}).get(role, {}).get("token"))
                    counts["rule_" + item["rule"]["kind"]] += 1
                refs = {(s["asset_type"], s["source_url"], s.get("status", "pending"), s.get("sha256", ""))
                        for s in paper["sources"]}
                stats[pid] = (paper["status"], counts, refs)
    return stats


def overview(years, out):
    def total(key):
        return sum(int(row.get(key) or 0) for row in years)
    verified = sum(row["status"] == "verified" for row in years)
    text = ["# 考選部醫學考題覆蓋統計", "",
            f"本版有 {len(years)} 個年度、{total('menu_exams'):,} 場選單紀錄。"
            f"其中 {total('parsed_exams'):,} 場取得科目清單，另有 {total('confirmed_empty_exams'):,} 場在官方來源確認未列試題。"
            f"有 {verified} 個年度的場次、類科與科目數均已核對相符。", "",
            f"醫事範圍共 {total('medical_papers'):,} 份卷，已取得 {total('verified_files'):,}／{total('indexed_files'):,} 個逐科附件。"
            f"其中 {total('papers_with_all_listed_files'):,} 份卷已備齊平台列出的逐科附件，{total('items_with_text'):,} 筆題目已抽出題幹。"
            f"另有 {total('boundary_papers'):,} 份邊界卷獨立列帳。", "",
            f"已完成的掃描卷 OCR 草稿有 {total('ocr_draft_pages'):,} 個醫事附件頁，依原始 PDF 與頁碼另存供逐頁核對。[OCR 來源、去重頁數與辨識品質](../ocr/README.md)", "",
            "| 已辨識的官方給分方式 | 題目紀錄數 |", "|---|---:|",
            *[f"| {name} | {total('rule_' + rule):,} |" for rule, name in (
                ("replacement", "改換答案"), ("any_of", "接受多種列明作答"), ("all_of", "指定完整選項組合"),
                ("all_credit", "一律給分"), ("conditional_credit", "附條件給分"), ("published_rubric", "實作評分標準"))], "",
            "前三欄依序核對全年度的場次、類科與科目，格式為「實取／官網顯示」。後段只統計醫事範圍，檔案欄為「已取得／已列載」。每一個題數代表該場、該類科的一筆題目紀錄。", "",
            "| 民國年 | 場次 | 類科 | 科目 | 醫事卷 | 試題 Q | 原答案 S | 更正卷 M | 有題幹 | 一律給分題 |",
            "|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for y in years:
        counts = [f"{y.get('parsed_' + k, '')}/{y['official_' + k]}" if y.get("official_" + k) else "待查"
                  for k in ("exams", "categories", "subjects")]
        docs = [f"{y[k + '_verified']}/{y[k + '_listed']}" for k in "QSM"]
        data = [y["medical_papers"], *docs, y["items_with_text"], y["rule_all_credit"]]
        if not y.get("official_subjects") and not y["medical_papers"]:
            data = ["待查"] * len(data)
        text.append("| " + " | ".join(map(str, [y["year_roc"], *counts, *data])) + " |")
    text.extend(["", "「一律給分題」只包括已抽取且有給分依據的紀錄。已列更正卷的題目中，也有維持原答案的題目。來源有更新或新增附件時，舊的抽取結果列為 stale，待重建後才再納入題數。",
                 "", "[年度明細與差額原因](years.tsv) · [場次及類科統計](groups.tsv) · [逐科清單](papers.tsv) · [欄位與來源](../README.md)", ""])
    atomic(out / "README.md", "\n".join(text).encode())


def build(index, manifest, items, out, ocr=None):
    annual = {r["year_roc"]: r for r in read_tsv(index / "coverage.tsv")}
    subjects = {paper_id(r): r for r in read_tsv(index / "subjects.tsv")}
    assets = defaultdict(dict)
    for r in read_tsv(index / "assets.tsv"):
        assets[paper_id(r)][(r["asset_type"], r["source_url"])] = r
    archived = {}
    source_rows = read_tsv(manifest)
    scanned = ocr_counts(ocr, source_rows)
    for r in source_rows:
        key = (r["asset_type"], r["source_url"])
        pid = r["paper_id"]
        archived[pid, key] = r
        if pid not in subjects:
            subjects[pid] = r
        # A previously observed file can survive a change to the current portal.
        assets[pid].setdefault(key, r)
    ledgers = ledger_counts(items)
    unknown = ledgers.keys() - subjects.keys()
    if unknown:
        raise ValueError(f"extracted papers missing from archive and index: {sorted(unknown)[:5]}")
    papers = []
    totals = defaultdict(Counter)
    groups = defaultdict(Counter)
    for pid, subject in sorted(subjects.items()):
        files = assets[pid]
        counts = Counter(scanned[pid])
        source_refs = set()
        scope, year = subject["scope"], subject["year_roc"]
        for key in files:
            role, _ = key
            receipt = archived.get((pid, key), {})
            status = receipt.get("status", "pending")
            source_refs.add((role, key[1], status, receipt.get("sha256", "")))
            counts["indexed_files"] += 1
            counts[role + "_listed"] += 1
            if status == "verified":
                counts["verified_files"] += 1
                counts[role + "_verified"] += 1
            elif status in {"fetch_error", "local_file_invalid"}:
                counts["failed_files"] += 1
            else:
                counts["files_without_receipt"] += 1
            counts["changed_from_prior"] += receipt.get("prior_comparison") == "changed"
        stage, extraction, ledger_refs = ledgers.get(pid, ("pending", {}, set()))
        if pid in ledgers and ledger_refs != source_refs:
            stage = "stale"
            counts["stale_item_records"] = extraction["item_records"]
        else:
            counts.update(extraction)
        papers.append({**subject, "paper_id": pid, "extraction": stage, **{k: counts[k] for k in COUNTS}})
        counts["papers"] = 1
        counts["papers_with_all_listed_files"] = int(bool(files) and counts["verified_files"] == len(files))
        counts["papers_with_text"] = int(counts["items_with_text"] > 0)
        counts["extraction_" + stage] = 1
        group = (year, subject["exam_code"], subject.get("exam_name", ""), subject["category_code"],
                 subject.get("category_name", ""), scope)
        groups[group].update(counts)
        if scope == "medical":
            totals[year].update(counts)
            totals[year]["medical_papers"] += 1
        elif scope == "boundary":
            totals[year]["boundary_papers"] += 1
    if totals.keys() - annual.keys():
        raise ValueError("archive contains a year absent from the index coverage table")
    stages = ["extraction_" + stage for stage in ("pending", "extracted", "partial", "unresolved", "stale")]
    fields = ["medical_papers", "boundary_papers", "papers_with_all_listed_files", "papers_with_text", *stages, *COUNTS]
    years = []
    for year, base in sorted(annual.items(), key=lambda item: int(item[0])):
        years.append({**base, **{k: totals[year][k] for k in fields}})
    write(out / "years.tsv", [*next(iter(annual.values())).keys(), *fields], years)
    write(out / "papers.tsv", ["year_roc", "exam_code", "exam_name", "category_code", "category_name",
                               "subject_code", "subject_name", "paper_id", "scope", "extraction", *COUNTS], papers)
    group_id = ["year_roc", "exam_code", "exam_name", "category_code", "category_name", "scope"]
    group_counts = ["papers", "papers_with_all_listed_files", "papers_with_text", *stages, *COUNTS]
    write(out / "groups.tsv", [*group_id, *group_counts],
          [{**dict(zip(group_id, group)), **{field: value[field] for field in group_counts}}
           for group, value in sorted(groups.items())])
    overview(years, out)
    return {k: sum(row[k] for row in years) for k in fields}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    root = Path("datasets/moex")
    p.add_argument("--index", type=Path, default=root / "index")
    p.add_argument("--manifest", type=Path, default=root / "archive/files.tsv")
    p.add_argument("--items", type=Path, default=root / "items")
    p.add_argument("--out", type=Path, default=root / "coverage")
    p.add_argument("--ocr", type=Path, help="optional folder of OCR page records for this snapshot")
    a = p.parse_args()
    ocr = a.ocr if a.ocr is not None else (a.items.parent / "ocr")
    print(json.dumps(build(a.index, a.manifest, a.items, a.out, ocr), sort_keys=True))


if __name__ == "__main__":
    main()
