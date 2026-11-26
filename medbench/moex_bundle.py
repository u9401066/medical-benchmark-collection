"""Archive medical papers through the official eight-subject bulk download form."""
from __future__ import annotations

import argparse
import hashlib
import html
import http.cookiejar
import http.client
import io
import json
import re
import time
import urllib.request
import zipfile
from collections import defaultdict
from pathlib import Path, PurePosixPath
from urllib.parse import urlencode

from . import moex_archive as archive
from .moex_index import FORM, label_text
from .twmed import SEARCH, UA, Moex

LINK_LABEL = {"試題": "Q", "答案": "S", "標準答案": "S", "更正答案": "M"}
PREFIX = {"Q": "", "S": "ANS", "M": "MOD"}
ZIP_SECTIONS = re.compile(r"<ul\s+class\s*=\s*['\"]link_([123])['\"][^>]*>", re.I)
LINKS = re.compile(r"<a\b[^>]*\bhref\s*=\s*['\"]([^'\"]+)['\"][^>]*>(.*?)</a>", re.I | re.S)
ERRORS = (OSError, ValueError, RuntimeError, http.client.HTTPException, zipfile.BadZipFile, EOFError)


def groups(rows, limit=8):
    """One exam per form, at most eight unique paper IDs and never two matching subject codes."""
    exams = defaultdict(dict)
    for row in rows:
        papers = exams[row["exam_code"]]
        papers.setdefault((row["category_code"], row["subject_code"]), []).append(row)
    for exam in sorted(exams):
        by_code = defaultdict(list)
        for (_, code), paper in sorted(exams[exam].items()):
            by_code[code].append(paper)
        # Each occurrence of a code requires its own batch. Deal consecutive
        # occurrences across the bins so no code collides and loads differ by at most one.
        count = max((len(exams[exam]) + limit - 1) // limit, max(map(len, by_code.values())))
        batches = [[] for _ in range(count)]
        offset = 0
        for code in sorted(by_code):
            for paper in by_code[code]:
                batches[offset % count].extend(paper)
                offset += 1
        yield from batches


def correction_batches(rows, limit):
    """Sample the batches containing the most corrected papers for a given year's pending rows."""
    corrected = {(r["exam_code"], r["category_code"], r["subject_code"]) for r in rows if r["asset_type"] == "M"}
    selected = [r for r in rows if (r["exam_code"], r["category_code"], r["subject_code"]) in corrected]
    batches = list(groups(selected))
    batches.sort(key=lambda batch: (-sum(r["asset_type"] == "M" for r in batch), -len(batch)))
    return batches[:limit]


def decoded_name(info):
    if info.flag_bits & 0x800:
        return info.filename
    return info.filename.encode("cp437").decode("cp950")


def match_bundle(z, rows):
    """Only accept explicit links from the matching exam/category/subject block with matching code and role."""
    names = defaultdict(list)
    for info in z.infolist():
        names[decoded_name(info)].append(info)
    indexes = [name for name in names if name.lower().endswith((".html", ".htm"))]
    if len(indexes) != 1 or len(names[indexes[0]]) != 1:
        raise ValueError("ZIP has no unique official HTML index")
    index = indexes[0]
    page = z.read(names[index][0]).decode("utf-8-sig")
    expected = defaultdict(list)
    for r in rows:
        expected[r["exam_name"], r["category_name"], r["subject_name"], r["asset_type"]].append(r)
    parts = ZIP_SECTIONS.split(page)
    identified = defaultdict(list)
    exam = category = ""
    for level, block in zip(parts[1::2], parts[2::2]):
        title = re.search(r"<div>(.*?)</div>", block, re.I | re.S)
        if not title:
            continue
        name = label_text(title[1])
        if level == "1":
            exam, category = name, ""
        elif level == "2":
            category = name
        else:
            for href, text in LINKS.findall(block):
                kind = LINK_LABEL.get(label_text(text))
                candidates = expected.get((exam, category, name, kind), [])
                if len(candidates) != 1 or kind is None:
                    continue
                row = candidates[0]
                filename = html.unescape(href)
                # The HTML links to a basename in the same folder, never an extracted filesystem path.
                if PurePosixPath(filename).name != filename or "\\" in filename:
                    continue
                prefix = row["exam_code"] + "_" + PREFIX[kind] + row["subject_code"] + "_"
                member = str(PurePosixPath(index).parent / filename)
                if filename.startswith(prefix) and len(names.get(member, [])) == 1:
                    identified[row["source_url"]].append((member, names[member][0]))
    # A malformed bundle may repeat a label/link or reuse a member in two subject rows.
    unique = {url: matches[0] for url, matches in identified.items() if len(matches) == 1}
    member_counts = defaultdict(int)
    for name, _ in unique.values():
        member_counts[name] += 1
    return {url: value for url, value in unique.items() if member_counts[value[0]] == 1}


def bundle_path(cache, sha):
    return cache / "bundles" / sha[:2] / (sha + ".zip")


def archived(cache, url):
    receipt = archive.cached(cache, url)
    if receipt.get("status") != "verified":
        return False
    if receipt.get("retrieval_method") == "official_bundle":
        sha = receipt.get("bundle_sha256", "")
        return bool(re.fullmatch(r"[0-9a-f]{64}", sha)) and bundle_path(cache, sha).is_file()
    return True


class Forms:
    def __init__(self, delay):
        self.client = archive.opener()
        self.client.add_handler(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
        self.client.addheaders = [("User-Agent", UA)]
        self.delay = max(1.0, delay)
        self.last_request = 0.0
        self.exam = None
        self.fields = {}
        self.page = ""

    def wait(self):
        time.sleep(max(0.0, self.last_request + self.delay - time.monotonic()))
        self.last_request = time.monotonic()

    def download(self, rows):
        code = rows[0]["exam_code"]
        year = str(int(rows[0]["year_roc"]) + 1911)
        url = SEARCH + "?" + urlencode({"e": code, "y": year})
        if self.exam != code:
            self.wait()
            with self.client.open(url, timeout=90) as response:
                self.page = response.read().decode("utf-8-sig")
            self.fields = {k: html.unescape(v) for k, v in Moex._hidden(self.page).items()}
            self.exam = code
        f = {**self.fields, FORM + "wUctlExamYearStart$ddlExamYear": year,
             FORM + "wUctlExamYearEnd$ddlExamYear": year, FORM + "ddlExamCode": code,
             FORM + "hidStatus": "1", FORM + "ibtnDownLoad": "試題打包"}
        for r in rows:
            name = FORM + "chk_" + "_".join([code, r["category_code"], r["subject_code"]])
            if f'name="{name}"' not in self.page:
                raise ValueError("selected subject missing from official form: " + name)
            f[name] = "on"
        self.wait()
        with self.client.open(url, urlencode(f).encode(), timeout=120) as response:
            return response.read(), response.geturl()


def fetch_batch(rows, cache, forms):
    receipt_rows = {}
    bundle_error = ""
    try:
        body, final = forms.download(rows)
        bundle_sha = hashlib.sha256(body).hexdigest()
        with zipfile.ZipFile(io.BytesIO(body)) as z:
            matches = match_bundle(z, rows)
            if matches:
                original = bundle_path(cache, bundle_sha)
                if not original.is_file() or hashlib.sha256(original.read_bytes()).hexdigest() != bundle_sha:
                    archive.atomic(original, body)
            for r in rows:
                match = matches.get(r["source_url"])
                if not match:
                    continue
                member, info = match
                payload = z.read(info)
                kind = archive.detect(payload, "", member)
                if r.get("prior_sha256") and hashlib.sha256(payload).hexdigest() != r["prior_sha256"]:
                    # Reconfirm a changed authoritative version by its individual official URL.
                    continue
                receipt_rows[r["source_url"]] = archive.save_payload(
                    r, cache, payload, kind, final, {"retrieval_method": "official_bundle",
                                                     "bundle_sha256": bundle_sha, "bundle_member": member})
    except ERRORS as exc:
        forms.exam = None
        bundle_error = str(exc)
    for r in rows:
        if r["source_url"] not in receipt_rows:
            forms.wait()
            receipt_rows[r["source_url"]] = archive.acquire(r, cache, forms.client)
    return receipt_rows, bundle_error


def listed_year(path, year):
    """A discrepancy in printed subject totals is distinct from an exam page still in transit."""
    if not path.is_file():
        return False
    for row in archive.read_tsv(path):
        if int(row["year_roc"]) == year:
            accounted = row.get("accounted_exams") or row["parsed_exams"]
            return bool(row["menu_exams"]) and int(row["menu_exams"]) == int(accounted) and bool(row["official_subjects"])
    return False


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--index", type=Path, default=Path("datasets/moex/index/assets.tsv"))
    p.add_argument("--cache", type=Path, default=Path("data/moex/archive"))
    p.add_argument("--seed", type=Path, default=Path("datasets/twmed/sources.tsv"), help="existing individual file digests, if available")
    p.add_argument("--years", required=True, help="ROC range, e.g. 81-112")
    p.add_argument("--scopes", default="medical")
    p.add_argument("--max-batches", type=int, help="stop after this many bundle requests")
    p.add_argument("--correction-batches-per-year", type=int, metavar="N",
                   help="sample up to N batches of papers with a pending official correction in each year")
    p.add_argument("--delay", type=float, default=1.0)
    p.add_argument("--wait-for-index", action="store_true",
                   help="process years oldest first as coverage.tsv becomes available, waiting up to three hours per year")
    args = p.parse_args(argv)
    bounds = [int(s) for s in args.years.split("-")]
    if len(bounds) not in (1, 2) or bounds[-1] < bounds[0]:
        p.error("--years must be a single year or an ascending range")
    if args.correction_batches_per_year is not None and args.correction_batches_per_year < 1:
        p.error("--correction-batches-per-year must be a positive integer")
    selected = set(args.scopes.split(","))
    known = {r["url"]: r["sha256"] for r in archive.read_tsv(args.seed)} if args.seed.is_file() else {}
    forms = Forms(args.delay)
    errors = attempts = 0
    for year in range(bounds[0], bounds[-1]+1):
        if args.wait_for_index:
            coverage = args.index.with_name("coverage.tsv")
            started = time.monotonic()
            while not listed_year(coverage, year):
                if time.monotonic() - started > 10800:
                    raise RuntimeError(f"official index for ROC year {year} incomplete; rerun after index collection")
                print(f"Waiting for official index for ROC year {year}", flush=True)
                time.sleep(60)
        rows = archive.plan([args.index], None)
        pending = [r for r in rows if int(r["year_roc"]) == year and r["scope"] in selected
                   and not archived(args.cache, r["source_url"])]
        for r in pending:
            r["prior_sha256"] = known.get(r["source_url"], "")
        batches = correction_batches(pending, args.correction_batches_per_year) if args.correction_batches_per_year else groups(pending)
        for batch in batches:
            # Other queues can finish an overlapping paper after this year's plan was loaded.
            batch = [r for r in batch if not archived(args.cache, r["source_url"])]
            if not batch:
                continue
            if args.max_batches is not None and attempts >= args.max_batches:
                return int(errors != 0)
            receipts, error = fetch_batch(batch, args.cache, forms)
            attempts += 1
            failures = sum(r.get("status") != "verified" for r in receipts.values())
            errors += failures
            print(json.dumps({"batch": attempts, "exam_code": batch[0]["exam_code"], "assets": len(receipts),
                              "bundled": sum(r.get("retrieval_method") == "official_bundle" for r in receipts.values()),
                              "errors": failures, "bundle_error": error}, ensure_ascii=False), flush=True)
            if attempts == 1 and failures == len(receipts):
                return 1
    return int(errors != 0)


if __name__ == "__main__":
    raise SystemExit(main())
