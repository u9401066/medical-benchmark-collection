"""Cross-check the exam portal against the Ministry's separately published open-data CSV."""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import os
import re
import subprocess
from collections import Counter, defaultdict
from email.parser import Parser
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from . import moex_archive as archive
from .moex_coverage import write
from .moex_index import classify

PAGE = "https://data.gov.tw/dataset/170565"
RESOURCE = "https://wwwc.moex.gov.tw/main/Exam/wHandExamQandA_CSV.ashx"
QUALITY = "https://quality.data.gov.tw/dq_download_csv.php?nid=170565&md5_url=f0d4bb47aa99f42907d8ffddf68af69c"
DELIVERY = {"origin": RESOURCE, "government_csv_export": QUALITY}


def register_csv(cache, path, header_path, source):
    """Seal a completed HTTP transfer; the quality portal can stream its CSV without Content-Length."""
    responses = [s for s in re.split(r"\r?\n\r?\n", header_path.read_text(encoding="latin1")) if s.startswith("HTTP/")]
    if not responses or responses[-1].splitlines()[0].split()[1] != "200":
        raise ValueError("Expected a completed HTTP 200 transfer")
    head = Parser().parsestr("\n".join(responses[-1].splitlines()[1:]))
    if head.get_content_type() not in {"application/octet-stream", "text/csv", "application/csv"}:
        raise ValueError("Official endpoint did not return a CSV")
    raw = path.read_bytes()
    length = head.get("Content-Length")
    if length is not None and len(raw) != int(length):
        raise ValueError("Open data CSV length differs from the official response")
    if not length and source == "origin":
        raise ValueError("Publisher CSV did not declare its expected size")
    rows = 0
    for row in csv_rows(raw):
        if None in row or None in row.values() or not row["考試年度"].isdigit():
            raise ValueError(f"Malformed open-data record {rows + 1}")
        rows += 1
    if not rows:
        raise ValueError("CSV contains no records")
    digest = hashlib.sha256(raw).hexdigest()
    cache.mkdir(parents=True, exist_ok=True)
    archive.atomic(cache / (digest + ".csv"), raw)
    metadata = {"catalog": PAGE, "resource": RESOURCE, "delivery": source, "download_url": DELIVERY[source],
                "bytes": len(raw), "sha256": digest, "http_date": head.get("Date"), "http_content_length": length,
                "retrieved_at": archive.now(), "csv_rows": rows}
    archive.atomic(cache / "latest.json", (json.dumps(metadata, indent=2) + "\n").encode())
    return metadata


def download(cache, source="origin"):
    """Use system TLS verification. Allow a slow but progressing publisher transfer to finish."""
    cache.mkdir(parents=True, exist_ok=True)
    partial = cache / f"transfer-{os.getpid()}.partial"
    headers = cache / f"transfer-{os.getpid()}.headers"
    args = ["curl", "--silent", "--show-error", "--fail", "--connect-timeout", "35", "--speed-limit", "1",
            "--speed-time", "240", "--retry", "5", "--retry-all-errors", "--retry-delay", "8", "--dump-header", str(headers),
            "--output", str(partial), DELIVERY[source]]
    subprocess.run(args, check=True)
    metadata = register_csv(cache, partial, headers, source)
    partial.unlink()
    return metadata


def csv_rows(raw):
    reader = csv.DictReader(io.StringIO(raw.decode("utf-8-sig"), newline=""), strict=True)
    required = {"考試年度", "考試代碼", "類科代碼", "科目全名", "試題型態", "試題網址", "測驗式試題答案網址", "備註", "類科組別", "節次"}
    if not required.issubset(reader.fieldnames or []):
        raise ValueError("Missing expected MOEX open-data columns")
    return reader


def resolve(row, subjects):
    keys = set()
    urls = [row["試題網址"].strip(), row["測驗式試題答案網址"].strip()]
    for url in filter(None, urls):
        if not archive.official(url):
            continue
        query = parse_qs(urlsplit(url).query)
        if not all(len(query.get(k, [])) == 1 for k in ("code", "c", "s")):
            continue
        keys.add(tuple(query[k][0] for k in ("code", "c", "s")))
    if len(keys) != 1:
        return None, "conflicting_keys" if keys else "no_keyed_link"
    key = keys.pop()
    if key[:2] != (row["考試代碼"], row["類科代碼"]):
        return None, "row_link_disagreement"
    return key, "matched" if key in subjects else "csv_only"


def build(index, cache, out):
    meta = json.loads((cache / "latest.json").read_text(encoding="utf-8"))
    raw = (cache / (meta["sha256"] + ".csv")).read_bytes()
    if len(raw) != meta["bytes"] or hashlib.sha256(raw).hexdigest() != meta["sha256"]:
        raise ValueError("Open data snapshot size or hash mismatch")
    subjects = {(r["exam_code"], r["category_code"], r["subject_code"]): r for r in archive.read_tsv(index / "subjects.tsv")}
    links = defaultdict(dict)
    for r in archive.read_tsv(index / "assets.tsv"):
        links[r["exam_code"], r["category_code"], r["subject_code"]][r["source_url"]] = r["asset_type"]
    seen = set()
    keyed_rows = 0
    detail = []
    years = defaultdict(Counter)
    exams = defaultdict(Counter)
    names = {}
    paper_types = Counter()
    for number, row in enumerate(csv_rows(raw), 1):
        year = row["考試年度"]
        years[year]["all_csv_rows"] += 1
        key, status = resolve(row, subjects)
        if key:
            seen.add(key)
            keyed_rows += 1
        scope = classify(row["類科組別"], row["科目全名"])
        portal_scope = subjects[key]["scope"] if key in subjects else ""
        exam = year, row["考試代碼"]
        names[exam] = row["考試名稱"]
        exams[exam][scope] += 1
        paper_types[year, scope, row["試題型態"]] += 1
        years[year][scope + "_csv_rows"] += 1
        if scope == "outside" and not portal_scope:
            continue
        if scope == "outside":
            years[year]["outside_matched_to_portal_selection"] += 1
        else:
            years[year][scope + "_" + status] += 1
        urls = [row["試題網址"].strip(), row["測驗式試題答案網址"].strip()]
        registered = links.get(key, {})
        extras = set(registered) - set(urls)
        foreign = [u for u in urls if u and u not in registered]
        detail.append(dict(year_roc=year, csv_record=number, exam_code=row["考試代碼"], category_code=row["類科代碼"],
                           category_name=row["類科組別"], subject_code=key[2] if key else "", subject_name=row["科目全名"],
                           session=row["節次"], scope=scope, portal_scope=portal_scope,
                           portal_category_name=subjects[key]["category_name"] if key in subjects else "",
                           paper_type=row["試題型態"], remark=row["備註"],
                           csv_question_url=urls[0], csv_answer_url=urls[1], mapping=status,
                           extra_portal_roles="|".join(sorted({registered[u] for u in extras})),
                           csv_urls_absent_from_portal="|".join(foreign)))
    portal_only = []
    for key, row in subjects.items():
        year, scope = row["year_roc"], row["scope"]
        if year in years and scope in {"medical", "boundary"} and key not in seen:
            same_exam = (year, row["exam_code"]) in exams
            status = "portal_only" if same_exam else "exam_not_in_csv"
            years[year][scope + "_" + status] += 1
            portal_only.append({**row, "comparison": status})
    numbers = ["all_csv_rows", "outside_csv_rows", "outside_matched_to_portal_selection",
               *[scope + "_" + k for scope in ("medical", "boundary") for k in (
                 "csv_rows", "matched", "csv_only", "row_link_disagreement", "conflicting_keys",
                 "no_keyed_link", "portal_only", "exam_not_in_csv")]]
    write(out / "years.tsv", ["year_roc", *numbers], [dict(year_roc=y, **{n: c[n] for n in numbers})
          for y, c in sorted(years.items(), key=lambda pair: int(pair[0]))])
    write(out / "records.tsv", list(detail[0]) if detail else ["year_roc", "csv_record", "mapping"], detail)
    write(out / "portal-only.tsv", ["year_roc", "exam_code", "category_code", "category_name", "subject_code", "subject_name", "scope", "comparison"], portal_only)
    write(out / "exams.tsv", ["year_roc", "exam_code", "exam_name", "all_csv_rows", "medical", "boundary", "outside", "scope_count"],
          [dict(year_roc=y, exam_code=code, exam_name=names[y, code], all_csv_rows=sum(c.values()),
                medical=c["medical"], boundary=c["boundary"], outside=c["outside"], scope_count=len(c))
           for (y, code), c in sorted(exams.items())])
    write(out / "paper-types.tsv", ["year_roc", "scope", "paper_type", "csv_rows"],
          [dict(year_roc=y, scope=s, paper_type=t, csv_rows=n) for (y, s, t), n in sorted(paper_types.items())])
    index_digest = {name: hashlib.sha256((index / name).read_bytes()).hexdigest() for name in ("subjects.tsv", "assets.tsv", "coverage.tsv")}
    archive.atomic(out / "source.json", (json.dumps({**meta, "catalog_api": "https://data.gov.tw/api/v2/rest/dataset/170565",
                    "csv_rows": sum(c["all_csv_rows"] for c in years.values()), "csv_exam_count": len(exams),
                    "keyed_csv_rows": keyed_rows, "unique_subject_keys": len(seen), "repeat_key_rows": keyed_rows - len(seen),
                    "portal_index_sha256": index_digest},
                   ensure_ascii=False, indent=2) + "\n").encode())


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--fetch", action="store_true")
    p.add_argument("--source", choices=DELIVERY, default="origin", help="publisher or its government's published CSV export")
    p.add_argument("--fetch-only", action="store_true", help="download and seal the CSV without updating reports")
    p.add_argument("--cache", type=Path, default=Path("data/moex/open-data"))
    p.add_argument("--index", type=Path, default=Path("datasets/moex/index"))
    p.add_argument("--out", type=Path, default=Path("datasets/moex/opendata"))
    args = p.parse_args()
    if args.fetch or args.fetch_only:
        download(args.cache, args.source)
    if args.fetch_only:
        return
    build(args.index, args.cache, args.out)


if __name__ == "__main__":
    main()
