"""Extract an unscored question ledger from verified MOEX archive files.

Invoke python -m medbench.moex_items --help. All page numbers are one-based
PDF pages. Unresolved papers retain source text by page.
"""
from __future__ import annotations

import argparse
import contextlib
import csv
import gzip
import hashlib
import json
import os
import re
import tempfile
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path
from statistics import median

from .twmed import DEPENDS, FIGURE, HEADER_ROW, parse_questions, pdf_rows, sha256_file


VERSION = 10
MC_HEADING = re.compile(r"^[甲乙丙丁一二三四壹貳參肆][、.．]\s*測驗(?:式)?題")
ESSAY_HEADING = re.compile(r"^[甲乙丙丁一二三四壹貳參肆][、.．]\s*(?:申論|問答)(?:式)?題(?:部分)?")
ESSAY_NUMBER = re.compile(r"^([一二三四五六七八九十]+)[、．.]\s*(.*)")
NUMBER = re.compile(r"(?:第)?(\d{1,3})(?:題)?")


def compact(text):
    return re.sub(r"\s+", "", unicodedata.normalize("NFKC", text))


def scoring_rule(original, corrected, note, mode):
    """Describe only rules stated by the grid or its item-specific note."""
    key = compact(corrected or original or "")
    note = compact(note).strip("。.;；,，")
    unresolved = {"kind": "unresolved"}
    if note:
        if re.fullmatch(r"(?:本題)?(?:一律給分|送分)", note):
            return {"kind": "all_credit"}
        includes = re.fullmatch(r"(?:選答之)?選項(?:中)?(?:包含|包括|含)([A-E])(?:選項)?者[,，]?(?:均|皆)?(?:給予|給|得)(?:該題)?(?:全部分數|全分|滿分)", note)
        if includes and mode == "multiple":
            return {"kind": "conditional_credit", "includes_for_full_credit": [includes[1]],
                    "other_responses": "requires_review"}
        if re.search(r"未作答|不給分|除.+外|其餘|其余|部分給分|酌予|倒扣", note):
            return {"kind": "conditional_credit"}
        one = re.fullmatch(r"(?:答案)?(?:更正為|更正為答|改為|答|選)([A-E])(?:者)?(?:給分)?", note)
        if one:
            answer = one.group(1)
            if key and key not in {"#", answer}:
                return unresolved
            changed = (original and compact(original) != answer) or "改為" in note or "更正為" in note
            result = {"kind": "replacement" if changed else "single", "choices": [answer]}
            if mode == "multiple":
                result["other_responses"] = "requires_review"
            return result
        either = re.fullmatch(r"(?:答|選)([A-E]+(?:或[A-E]+)+)(?:者)?(?:均|皆)?(?:給分|予以給分)", note)
        if either and key in {"", "#"}:
            # e.g. 答Ａ或Ｄ或AD者均給分 accepts three distinct response combinations.
            return {"kind": "any_of", "choices": either.group(1).split("或"), "unlisted_combinations": "requires_review"}
        required = re.fullmatch(r"(?:須|必須|應)?(?:同時|全部)(?:選擇|選|答)([A-E](?:(?:及|和|與|、)?[A-E])+)(?:者)?(?:才|始|方)?給分", note)
        if required and key in {"", "#"}:
            return {"kind": "all_of", "choices": list(dict.fromkeys(re.findall(r"[A-E]", required.group(1)))),
                    "partial_credit": "requires_review"}
        return unresolved
    if mode == "multiple" and re.fullmatch(r"[A-E]+", key) and len(set(key)) == len(key):
        return {"kind": "all_of", "choices": list(key), "partial_credit": "requires_review"}
    if mode == "single" and re.fullmatch(r"[A-E]", key):
        changed = corrected and original and compact(original) != key
        return {"kind": "replacement" if changed else "single", "choices": [key]}
    return unresolved


def _word_lines(doc):
    for page in doc:
        lines = []
        for word in sorted(page.get_text("words"), key=lambda w: (w[1], w[0])):
            if not lines or abs(word[1] - lines[-1][0][1]) > 3:
                lines.append([])
            lines[-1].append(word)
        yield page.number + 1, [sorted(line, key=lambda w: w[0]) for line in lines]


def read_key(path):
    """Use cell centers so an empty middle cell cannot shift the rest of a row."""
    import pymupdf

    evidence, page_text, issues = {}, {}, []
    with pymupdf.open(path) as doc:
        for page, lines in _word_lines(doc):
            page_text[page] = "\n".join(" ".join(w[4] for w in row) for row in lines)
            for i, row in enumerate(lines[:-1]):
                if compact(row[0][4]) not in {"題號", "題序"}:
                    continue
                answer_row = lines[i + 1]
                if not compact(answer_row[0][4]).startswith("答案"):
                    continue
                cells = []
                for word in row[1:]:
                    num = NUMBER.fullmatch(compact(word[4]))
                    if not num:
                        issues.append("unrecognized_number_grid")
                        break
                    cells.append((int(num.group(1)), (word[0] + word[2]) / 2))
                if not cells or len(cells) != len(row) - 1:
                    continue
                centers = [x for _, x in cells]
                tolerance = median(b - a for a, b in zip(centers, centers[1:])) * 0.47 if len(cells) > 1 else 12
                words = [((word[0] + word[2]) / 2, word[4]) for word in answer_row[1:]]
                first = answer_row[0]
                if first[4].startswith("答案") and first[4][2:].strip():
                    # Some PDFs join the label and first token in a single word.
                    # Its right edge, rather than the center of the combined label, locates the cell.
                    words.insert(0, (first[2], first[4][2:].strip()))
                for x, token in words:
                    n, center = min(cells, key=lambda pair: abs(x - pair[1]))
                    if abs(x - center) > tolerance or n in evidence:
                        issues.append("ambiguous_grid_cell")
                        continue
                    evidence[n] = {"token": token, "page": page}
    norm = compact("\n".join(page_text.values()))
    counts = {mode: re.search(label + r"題數:(\d+)", norm)
              for mode, label in (("single", "單選"), ("multiple", "複選"))}
    counts = {mode: int(m[1]) for mode, m in counts.items() if m}
    if not counts:
        total = re.search(r"題數:(\d+)題", norm)
        if total:
            counts = {"unspecified": int(total[1])}
    expected = sum(counts.values())
    if not expected or set(evidence) != set(range(1, expected + 1)):
        issues.append("incomplete_number_grid")
    notes, raw_notes = {}, []
    for page, content in page_text.items():
        block = re.search(r"備\s*註\s*[:：](.*)", content, re.S)
        if not block:
            continue
        body = re.split(r"標\s*準\s*答\s*案\s*[:：]", block[1])[0].strip()
        if not body:
            continue
        raw_notes.append({"page": page, "text": body})
        matches = list(re.finditer(r"第\s*([0-9０-９]+)\s*題", body))
        if not matches or compact(body[:matches[0].start()]).strip("。.;；") or re.search(r"第[\d\s]+[、及與至~～-]", body):
            issues.append("unassigned_correction_note")
            continue
        for j, match in enumerate(matches):
            n = int(match[1])
            end = matches[j + 1].start() if j + 1 < len(matches) else len(body)
            if n in notes or n not in evidence:
                issues.append("unassigned_correction_note")
            notes[n] = {"page": page, "text": body[match.start():end].strip(), "rule": body[match.end():end].strip()}
    return {"counts": counts, "entries": evidence, "notes": notes, "raw_notes": raw_notes,
            "issues": sorted(set(issues)), "page_text": page_text}


def _practical_item(rows, paper_id):
    """Recognize the one-task practical form with separate instructions and a scoring rubric."""
    markers = [re.compile(pattern) for pattern in (
        r"^題\s*目\s*[:：]", r"^一[、.]\s*注意事項\s*[:：]?\s*$",
        r"^二[、.]\s*評分標準\s*[:：]?\s*$")]
    indices = [[i for i, row in enumerate(rows) if pattern.match(row.text.strip())] for pattern in markers]
    if any(len(hits) != 1 for hits in indices):
        return None
    start, notes, scoring = (hits[0] for hits in indices)
    if not start < notes < scoring < len(rows) - 1:
        return None
    if any(re.match(r"^[三四五六七八九十]+[、.]", row.text.strip()) for row in rows[start:]):
        return None
    def lines(section):
        return "\n".join(row.text.strip() for row in section)
    def pages(section):
        return sorted({row.page + 1 for row in section})
    return {"id": f"{paper_id}-practical-001", "section": "practical", "number": 1,
            "pages": pages(rows[start:]), "start_y_pt": round(rows[start].y, 2),
            "question": markers[0].sub("", lines(rows[start:notes]), count=1).strip(),
            "instructions": lines(rows[notes:scoring]), "flags": ["requires_performance"],
            "rule": {"kind": "published_rubric", "source_role": "Q", "pages": pages(rows[scoring:]),
                     "start_y_pt": round(rows[scoring].y, 2), "text": lines(rows[scoring:])}}


def _essay_items(rows, prefix, confirmed, images, graphics):
    items = []
    starts = []
    for row in rows:
        line = row.text.strip()
        if HEADER_ROW.search(line):
            continue
        m = ESSAY_NUMBER.match(line)
        if confirmed and not m:
            numbered = re.match(r"^(\d{1,2})[.．](?!\d)\s*(.*)", line)
            if numbered and int(numbered[1]) == len(items) + 1:
                m = numbered
        if m and not ESSAY_HEADING.match(line) and not MC_HEADING.match(line):
            items.append({"id": f"{prefix}-essay-{m[1]}", "section": "essay" if confirmed else "unclassified_written",
                          "number_label": m[1], "pages": [row.page + 1], "question": m[2], "rule": {"kind": "unresolved"},
                          "flags": []})
            starts.append((row.page, row.y))
        elif items:
            item = items[-1]
            item["question"] += "\n" + line
            if item["pages"][-1] != row.page + 1:
                item["pages"].append(row.page + 1)
    if len({item["id"] for item in items}) != len(items):
        return []
    for index, item in enumerate(items):
        end = starts[index + 1] if index + 1 < len(starts) else (rows[-1].page, rows[-1].y + 2)
        if FIGURE.search(item["question"]):
            item["flags"].append("refers_to_figure")
        for boxes, flag in ((images, "image"), (graphics, "table or formula")):
            if any(starts[index] <= (p, (top + bottom) / 2) < end for p, top, bottom in boxes):
                item["flags"].append(flag)
    return items


def extract_paper(paper_id, files, listed, subject="", issues=()):
    """Extract from verified local PDFs, keeping incomplete material visible."""
    issues, keys, items = list(issues), {}, []
    rows, images, graphics, page_counts = [], [], [], {}
    for typ in sorted((set(listed) & {"Q", "S", "M"}) - files.keys()):
        issues.append(f"{typ}_unavailable")
    for typ, path in files.items():
        try:
            if typ == "Q":
                if Path(path).is_file():
                    import pymupdf
                    with pymupdf.open(path) as pdf:
                        page_counts["Q"] = pdf.page_count
                        # Scanned historical pages can carry large raster images and no glyphs.
                        # Avoid decoding every bitmap into the text-row parser for these documents.
                        if not any(page.get_text("text").strip() for page in pdf):
                            images = [(page.number, 0, page.rect.height) for page in pdf if page.get_image_info()]
                            continue
                rows, images, graphics = pdf_rows(path)
            elif typ in {"S", "M"}:
                key = keys[typ] = read_key(path)
                page_counts[typ] = len(key["page_text"])
                issues += [f"{typ}_{issue}" for issue in key["issues"]]
                printed = re.search(r"科\s*目\s*名\s*稱\s*[:：][ \t]*([^\n]+)", "\n".join(key["page_text"].values()))
                if printed and subject:
                    name = re.split(r"[(（]試題代號|\t|\s+(?:類科|單選|標準答案|題號)", printed[1])[0]
                    want, got = compact(subject), compact(name)
                    if want and got and not (want in got or got in want):
                        issues.append(f"{typ}_subject_mismatch")
        except (RuntimeError, ValueError, OSError) as error:
            issues.append(f"{typ}_read_error:{type(error).__name__}")
    if not rows:
        issues.append("question_text_unavailable")
    first_mc = next((i for i, row in enumerate(rows) if MC_HEADING.match(row.text.strip())), None)
    first_essay = next((i for i, row in enumerate(rows) if ESSAY_HEADING.match(row.text.strip())), None)
    objective_rows = rows[first_mc + 1:] if first_mc is not None else rows
    practical = _practical_item(rows, paper_id) if first_mc is None and first_essay is None else None
    qs = [] if practical or (first_essay is not None and first_mc is None) else parse_questions(objective_rows, images, graphics)
    header_rows = [r for r in rows if qs and (r.page, r.y) < (qs[0].page, qs[0].y)]
    instructions = compact("".join(r.text for r in header_rows))
    stated_mode = None
    if re.search(r"(?:本試題為|本部分為|本測驗題均為|本題型為)(?:單一選擇題|單選題)", instructions):
        stated_mode = "single"
    elif re.search(r"(?:本試題為|本部分為|本測驗題均為|本題型為)(?:複選題|多重選擇題)", instructions):
        stated_mode = "multiple"
    # The essay and objective sections can print different codes. Keep row
    # boundaries so a digit on the next row cannot become part of the code.
    objective_header = header_rows[first_mc:] if first_mc is not None else header_rows
    q_codes = {match[1] for row in objective_header
               if (match := re.search(r"(?:試題)?代號:(\d{3,6})(?!\d)", compact(row.text)))}
    for typ, key in keys.items():
        k_codes = {m[1] for page_text in key["page_text"].values() for line in page_text.splitlines()
                   if (m := re.search(r"試題代號:(\d{3,6})(?!\d)", compact(line)))}
        if q_codes and k_codes and (len(q_codes) != 1 or q_codes != k_codes):
            issues.append(f"{typ}_printed_paper_code_mismatch")
    if practical:
        items = [practical]
    elif first_essay is not None or not qs or first_mc is not None:
        before = rows[(first_essay + 1 if first_essay is not None else 0):first_mc]
        if first_mc is None and qs and first_essay is not None:
            before = [r for r in before if (r.page, r.y) < (qs[0].page, qs[0].y)]
        items = _essay_items(before, paper_id, first_essay is not None or any("申論" in r.text for r in before[:15]),
                             images, graphics)
        if first_essay is not None and not items:
            issues.append("essay_boundaries_unresolved")
    if not qs and not items:
        issues.append("no_question_boundaries")
    if qs and not keys:
        issues.append("no_verified_key")
    if len(keys) == 2:
        base, revised = keys["S"]["counts"], keys["M"]["counts"]
        modes_given = "unspecified" not in base and "unspecified" not in revised
        if sum(base.values()) != sum(revised.values()) or (modes_given and base != revised):
            issues.append("original_corrected_counts_mismatch")
    numbers = {q.n for q in qs}
    for typ, key in keys.items():
        if numbers != set(key["entries"]):
            issues.append(f"{typ}_question_key_mismatch")
    # A complete corrected grid directly supports its own rules when the original
    # PDF is pending. The reverse would silently miss official corrections.
    blocked = any(issue != "S_unavailable" or "M" not in keys for issue in issues)
    by_num = {q.n: q for q in qs}
    all_numbers = numbers.union(*(key["entries"] for key in keys.values()))
    for n in sorted(all_numbers):
        q = by_num.get(n)
        item = {"id": f"{paper_id}-{n:03d}", "section": "objective", "number": n, "pages": [],
                "question": None, "options": {}, "flags": [], "key_evidence": {}}
        if q:
            start = (q.page, q.y)
            item["pages"] = sorted({r.page + 1 for r in rows if start <= (r.page, r.y) < q.end and not HEADER_ROW.search(r.text)})
            item["start_y_pt"] = round(q.y, 2)
            item.update(question=q.stem, options=q.options, flags=list(q.problems))
            if FIGURE.search(q.text):
                item["flags"].append("refers_to_figure")
            if DEPENDS.match(q.stem):
                item["flags"].append("depends_on_previous")
        else:
            item["flags"].append("unparsed_question")
        for typ, key in keys.items():
            if n in key["entries"]:
                item["key_evidence"][typ] = dict(key["entries"][n])
                if n in key["notes"]:
                    note = key["notes"][n]
                    item["key_evidence"][typ]["note"] = {"page": note["page"], "text": note["text"]}
        typ = "M" if "M" in keys else "S"
        rule = {"kind": "unresolved"}
        if not blocked:
            key = keys[typ]
            original = item["key_evidence"].get("S", {}).get("token")
            corrected = item["key_evidence"].get("M", {}).get("token")
            active = [mode for mode, count in key["counts"].items() if count]
            mode = active[0] if len(active) == 1 else None
            if mode == "unspecified":
                mode = stated_mode
            rule = scoring_rule(original, corrected, key["notes"].get(n, {}).get("rule", ""), mode)
        item["rule"] = rule
        items.append(item)
    out = {"paper_id": paper_id, "status": "unresolved" if not items else "partial" if issues else "extracted",
           "issues": sorted(set(issues)), "items": items,
           "answer_basis": "archived_pdf_snapshot", "separate_correction_notices": "not_reconciled",
           "question_instruction_mode": stated_mode, "source_page_counts": page_counts,
           "key_counts": {typ: key["counts"] for typ, key in keys.items()},
           "key_notes": {typ: key["raw_notes"] for typ, key in keys.items()}}
    if issues or not qs or any(q.problems for q in qs):
        out["source_pages"] = {typ: key["page_text"] for typ, key in keys.items() if key["issues"] or blocked}
        q_pages = {page: [] for page in range(1, page_counts.get("Q", 0) + 1)}
        for row in rows:
            q_pages.setdefault(row.page + 1, []).append(row.text)
        out["source_pages"]["Q"] = {page: "\n".join(lines) for page, lines in q_pages.items()}
        out["image_pages"] = sorted({p + 1 for p, _, _ in images})
    return out


def _encoded(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _read_shard(path):
    if not path.exists():
        return {}
    with gzip.open(path, "rt", encoding="utf-8") as stream:
        return {record["paper_id"]: record for record in map(json.loads, stream)}


@contextlib.contextmanager
def _shard_lock(cache, path):
    """Serialize the short final merge for batches sharing an archive cache."""
    lock = cache / ".item-locks" / (hashlib.sha256(str(path.resolve()).encode()).hexdigest() + ".lock")
    lock.parent.mkdir(parents=True, exist_ok=True)
    with lock.open("a+b") as stream:
        if os.name == "nt":
            import msvcrt
            if not stream.tell():
                stream.write(b"0")
                stream.flush()
            stream.seek(0)
            msvcrt.locking(stream.fileno(), msvcrt.LK_LOCK, 1)
            try:
                yield
            finally:
                stream.seek(0)
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl
            fcntl.flock(stream.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(stream.fileno(), fcntl.LOCK_UN)


def _write_shard(path, records):
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as tmp:
        temp_path = Path(tmp.name)
    try:
        with temp_path.open("wb") as stream, gzip.GzipFile(filename="", fileobj=stream, mode="wb", mtime=0) as compressed:
            for pid in sorted(records):
                compressed.write(_encoded(records[pid]) + b"\n")
        os.replace(temp_path, path)
    finally:
        temp_path.unlink(missing_ok=True)


def prune_empty_placeholders(out, cache):
    """Outstanding downloads belong in the manifest. Retain any paper with evidence or items."""
    for shard in out.glob("*/*.jsonl.gz"):
        with _shard_lock(cache, shard):
            records = _read_shard(shard)
            keep = {pid: r for pid, r in records.items()
                    if r["items"] or any(s.get("status") == "verified" for s in r["sources"])}
            if len(keep) == len(records):
                continue
            if keep:
                _write_shard(shard, keep)
            else:
                shard.unlink()


def _sources(rows, cache):
    by_role, files, refs, issues = defaultdict(list), {}, [], []
    for row in sorted(rows, key=lambda r: (r["asset_type"], r["source_url"])):
        typ = row["asset_type"]
        ref = {k: row[k] for k in ("asset_type", "source_url", "sha256", "status", "listed_by", "asset_id", "asset_sequence",
                                   "prior_sha256", "prior_comparison", "retrieved_at")
               if row.get(k)}
        refs.append(ref)
        by_role[typ].append(row)
    for typ in sorted({"Q", "S", "M"} & by_role.keys()):
        assets = by_role[typ]
        if len(assets) != 1:
            issues.append(f"{typ}_ambiguous_attachments")
            continue
        row = assets[0]
        if row["status"] != "verified":
            continue
        if row.get("format", "pdf").lower() != "pdf":
            issues.append(f"{typ}_unsupported_format")
            continue
        path = (cache / row["local_path"]).resolve()
        if not path.is_relative_to(cache) or not path.is_file() or sha256_file(path) != row["sha256"]:
            issues.append(f"{typ}_cache_integrity_error")
        else:
            files[typ] = path
    return by_role, files, refs, issues


def build(manifest, cache, out, years=None, paper_ids=None, limit=None):
    import pymupdf

    cache = cache.resolve()
    papers = defaultdict(list)
    with manifest.open(encoding="utf-8-sig", newline="") as stream:
        for row in csv.DictReader(stream, delimiter="\t"):
            if (not years or row["year_roc"] in years) and (not paper_ids or row["paper_id"] in paper_ids):
                papers[row["paper_id"]].append(row)
    by_exam = defaultdict(list)
    for pid in sorted(papers)[:limit]:
        row = papers[pid][0]
        if not (row["exam_code"].isdigit() and row["year_roc"].isdigit()):
            raise ValueError(f"Unexpected exam/year identifier for {pid}")
        by_exam[(row["year_roc"], row["exam_code"])].append(pid)
    summary = Counter()
    for (year, exam), exam_papers in sorted(by_exam.items()):
        path = out / year / f"{exam}.jsonl.gz"
        records = _read_shard(path)
        updates = {}
        for pid in exam_papers:
            rows = papers[pid]
            row = rows[0]
            listed, files, refs, issues = _sources(rows, cache)
            meta = {k: row.get(k, "") for k in ("year_roc", "exam_code", "exam_name", "category_code",
                                                 "category_name", "subject_code", "subject_name", "scope")}
            provenance = {"version": VERSION, "pymupdf": pymupdf.VersionBind, "paper": meta, "sources": refs,
                          "roles_not_listed_in_current_manifest": sorted({"Q", "S", "M"} - listed.keys())}
            signature = hashlib.sha256(_encoded([provenance, issues])).hexdigest()
            previous = records.get(pid, {})
            if previous.get("input_sha256") != signature:
                record = extract_paper(pid, files, listed, row["subject_name"], issues)
                records[pid] = {**provenance, **record, "input_sha256": signature}
                updates[pid] = records[pid]
            record = records[pid]
            summary["papers"] += 1
            summary["paper_" + record["status"]] += 1
            summary["items"] += len(record["items"])
            summary.update("rule_" + item["rule"]["kind"] for item in record["items"])
        if updates:
            with _shard_lock(cache, path):
                latest = _read_shard(path)
                latest.update(updates)
                _write_shard(path, latest)
    return dict(sorted(summary.items()))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=Path("datasets/moex/archive/files.tsv"))
    parser.add_argument("--cache", type=Path, default=Path("data/moex/archive"))
    parser.add_argument("--out", type=Path, default=Path("datasets/moex/items"))
    parser.add_argument("--year", action="append", help="ROC year, repeatable")
    parser.add_argument("--paper", action="append", help="Exact paper ID, repeatable")
    parser.add_argument("--limit", type=int, help="First N matching papers in stable ID order")
    args = parser.parse_args()
    if args.limit is not None and args.limit < 0:
        parser.error("--limit must be nonnegative")
    print(json.dumps(build(args.manifest, args.cache, args.out, args.year, args.paper, args.limit), sort_keys=True))


if __name__ == "__main__":
    main()
