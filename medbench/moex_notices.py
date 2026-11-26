"""Collect MOEX bulletin titles, linked notices and original attachments, separately from Q/S/M."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import re
import shutil
import subprocess
import threading
import time
import unicodedata
import zipfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date
from html import unescape
from html.parser import HTMLParser
from io import BytesIO
from pathlib import Path
from urllib.parse import urlencode, urljoin, urlsplit
from xml.etree import ElementTree

from .twmed import MEDICAL_EXAM, SEARCH

ROOT = Path(__file__).resolve().parents[1]
BASE = "https://wwwc.moex.gov.tw/main/"
INDEXES = {
    "exam_bulletins": BASE + "news/wfrmNews.aspx?kind=2&menu_id=41",
    "latest_news": BASE + "news/wfrmNews.aspx?kind=3&menu_id=42",
    "emergency": BASE + "news/wfrmNews.aspx?kind=1&menu_id=5",
    "case_law": BASE + "examlaws/wfrmExamLaws.aspx?kind=7&menu_id=1933",
}
AWARD = re.compile(
    r"試題.{0,8}(疑義|爭議|更正|錯誤|勘誤)|更正.{0,8}(試題|答案)|答案.{0,6}(更正|疑義|勘誤)|標準答案|一律給分|均給分|送分"
)
MEDICAL = re.compile(r"醫師|藥師|護理|醫事|營養|心理|治療|助產|驗光|聽力|公共衛生|法醫")
PROCEDURE = re.compile(r"操作說明|申請程序|應考須知")
HOST = "wwwc.moex.gov.tw"


class Page(HTMLParser):
    def __init__(self, body: bytes):
        super().__init__(convert_charrefs=True)
        self.links = []
        self.hidden = {}
        self.next_button = None
        self.values = {}
        self.link = None
        self.feed(body.decode("utf-8-sig"))

    def handle_starttag(self, tag, attrs):
        args = dict(attrs)
        if tag == "a" and args.get("href"):
            self.link = dict(args, text="")
        if tag == "input" and args.get("name"):
            name, value = args["name"], args.get("value", "")
            if args.get("type") == "hidden":
                self.hidden[name] = value
            if name.endswith("$btnNext") and "disabled" not in args:
                self.next_button = (name, value)
            self.values[name] = value

    def handle_data(self, value):
        if self.link is not None:
            self.link["text"] += value

    def handle_endtag(self, tag):
        if tag == "a" and self.link is not None:
            self.link["text"] = self.link["text"].strip()
            self.links.append(self.link)
            self.link = None


def sha(body):
    return hashlib.sha256(body).hexdigest()


def official(base, href):
    url = urljoin(base, href)
    parts = urlsplit(url)
    if parts.scheme == "https" and parts.hostname == HOST:
        return url
    return None


def list_rows(body, url):
    rows = []
    html = body.decode("utf-8-sig")
    for block in re.findall(r"<tr\b[^>]*>.*?</tr>", html, re.S | re.I):
        for link in Page(block.encode()).links:
            if not link.get("id", "").endswith("_lnkTitle"):
                continue
            target = official(url, link["href"])
            if target:
                published = re.search(r"(?:_lblBeginDate[^>]*>|出刊日期：<span[^>]*>)(\d+)/(\d+)/(\d+)<", block)
                when = (
                    date(int(published[1]) + 1911, int(published[2]), int(published[3])).isoformat()
                    if published
                    else None
                )
                rows.append(dict(title=link["text"], url=target, publication_date=when))
    return rows


def attachment_links(page, url):
    out = []
    for a in page.links:
        if not a.get("id", "").endswith("_lnkFiles"):
            continue
        target = official(url, a["href"])
        if target:
            label = a.get("title") or a["text"]
            out.append((target, label))
    return out


def media(body):
    if body.startswith(b"%PDF-"):
        return "pdf"
    if body.startswith(b"PK"):
        with zipfile.ZipFile(BytesIO(body)) as z:
            if "word/document.xml" in z.namelist():
                return "docx"
            if "mimetype" in z.namelist() and z.read("mimetype") == b"application/vnd.oasis.opendocument.text":
                return "odt"
        return "zip"
    if body.startswith(bytes.fromhex("D0CF11E0A1B11AE1")):
        return "ole"
    return "unknown"


class Cache:
    """Keep verified HTTPS responses locally. Each snapshot is a separate, resumable directory."""

    def __init__(self, path, offline=False):
        self.path = path
        self.path.mkdir(parents=True, exist_ok=True)
        self.last = 0.0
        self.lock = threading.Lock()
        self.offline = offline

    def fetch(self, url, key, form=None):
        parsed = urlsplit(url)
        if parsed.scheme != "https" or not government_host(parsed.hostname):
            raise ValueError("unexpected URL: " + url)
        destination = self.path / key
        if destination.is_file() and destination.stat().st_size:
            return destination.read_bytes()
        if self.offline:
            raise FileNotFoundError("not cached: " + key)
        with self.lock:
            time.sleep(max(0, 1 - (time.monotonic() - self.last)))
            self.last = time.monotonic()
        tmp = destination.with_name(f"{destination.name}.{os.getpid()}-{threading.get_ident()}.part")
        cmd = [
            "curl",
            "--silent",
            "--show-error",
            "--fail",
            "--compressed",
            "--connect-timeout",
            "10",
            "--max-time",
            "600" if key.endswith(".bin") else "180",
            "--speed-limit",
            "40",
            "--speed-time",
            "50",
            "--retry",
            "2",
            "--proto",
            "=https",
            "--output",
            str(tmp),
        ]
        # The lists use ASP.NET form fields, including their current validation token.
        payload = urlencode(form).encode() if form is not None else None
        if payload is not None:
            cmd += ["--data-binary", "@-"]
        subprocess.run(cmd + [url], input=payload, check=True)
        body = tmp.read_bytes()
        if not body:
            raise ValueError("empty response")
        tmp.replace(destination)
        return body


def scan_index(cache, label, url, query, coverage, all_titles=False):
    start = cache.fetch(url, label + ".html")
    page = Page(start)
    listing = start
    tag = label
    fields = {}
    if query or all_titles:
        tag += "-all" if all_titles else "-" + sha(query.encode())[:8]
        fields = {
            "ctl00$holderContent$txtQ_Title": query,
            "ctl00$holderContent$ddlQ_BeginMonth": "",
            "ctl00$holderContent$ddlQ_EndMonth": "",
            "ctl00$holderContent$uctlQ_PageSize$ddlQ_PageSize": "5",
        }
        if label == "weekly":
            fields.pop("ctl00$holderContent$ddlQ_BeginMonth")
            fields.pop("ctl00$holderContent$ddlQ_EndMonth")
            for k in ("ddlQ_Volume", "ddlQ_Collection", "ddlQ_Kind", "txtQ_Author"):
                fields["ctl00$holderContent$" + k] = ""
        listing = cache.fetch(
            url, tag + "-1.html", {**page.hidden, **fields, "ctl00$holderContent$btnQuery": "查詢"}
        )
    found = []
    seen = set()
    page_num = 1
    while True:
        text = listing.decode("utf-8-sig")
        page = Page(listing)
        if "ctl00_holderContent_grd" not in text and not re.search(r"查無(相關)?資料|無符合", text):
            raise ValueError("unexpected listing response for " + tag)
        if query and page.values.get("ctl00$holderContent$txtQ_Title") != query:
            raise ValueError("keyword was not applied")
        rows = list_rows(listing, url)
        batch = tuple(r["url"] for r in rows)
        if batch in seen:
            raise ValueError("repeated page")
        seen.add(batch)
        match = re.search(r"共\s*(?:<[^>]+>\s*)*(\d+)\s*(?:<[^>]+>\s*)*筆", text)
        coverage.append(
            dict(
                channel=label,
                query=query or None,
                page=page_num,
                url=url,
                cache_key=(tag + "-" + str(page_num) + ".html")
                if query or all_titles or page_num > 1
                else label + ".html",
                sha256=sha(listing),
                rows=len(rows),
                reported_total=int(match[1]) if match else None,
            )
        )
        found.extend(rows)
        if not page.next_button:
            break
        page_num += 1
        name, value = page.next_button
        listing = cache.fetch(url, tag + "-" + str(page_num) + ".html", {**page.hidden, **fields, name: value})
    if match and int(match[1]) != len(found):
        raise ValueError("number of rows disagrees with site total")
    return found


def title_in_scope(title, channel):
    if not AWARD.search(title) or PROCEDURE.search(title):
        return False
    if channel == "case_law":
        return bool(MEDICAL.search(title) and not re.search("獸醫|獸醫師", title))
    return True


def extract_docx_paragraphs(body):
    with zipfile.ZipFile(BytesIO(body)) as archive:
        xml = ElementTree.fromstring(archive.read("word/document.xml"))
    ns = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
    return ["".join(t.text or "" for t in p.iter(ns + "t")) for p in xml.iter(ns + "p")]


def save_attachment(cache, parent, url, title):
    key = "attachment-" + sha(url.encode())[:20] + ".bin"
    blob = cache.fetch(url, key)
    fmt = media(blob)
    if fmt == "unknown":
        raise ValueError("attachment has an unsupported signature or returned HTML")
    return dict(
        url=url, parent_url=parent, title=title, media=fmt, bytes=len(blob), sha256=sha(blob), cache_key=key
    )


def annual_exam_codes(directory, years, categories=None):
    """Read annual option lists produced by the MOEX past-paper inventory. Do not synthesize exam codes."""
    coverage = []
    codes = set()
    by_year = {}
    if categories is not None:
        with categories.open(encoding="utf8") as f:
            for row in csv.DictReader(f, delimiter="\t"):
                if row["scope"] == "medical":
                    by_year.setdefault(int(row["year_roc"]) + 1911, set()).add(row["exam_code"])
    for year in years:
        path = directory / ("year-%d.html" % year)
        body = path.read_bytes()
        text = body.decode("utf-8-sig")
        field = re.search(r'<select[^>]+name="ctl00\$holderContent\$ddlExamCode"[^>]*>(.*?)</select>', text, re.S)
        if not field:
            raise ValueError("missing exam-code selector: " + str(path))
        rows = re.findall(r'<option[^>]+value="(\d{6})"[^>]*>([^<]*)</option>', field[1])
        matched = [c for c, t in rows if MEDICAL_EXAM.search(unescape(t))]
        category_matches = by_year.get(year, set())
        if category_matches.difference(c for c, _ in rows):
            raise ValueError("category exam code absent from annual options: " + str(year))
        coverage.append(
            dict(
                year=year,
                source=SEARCH,
                selector="year=" + str(year),
                source_sha256=sha(body),
                exam_options=len(rows),
                title_matches=sorted(set(matched)),
                medical_category_matches=sorted(category_matches),
                matched_codes=sorted(set(matched) | category_matches),
            )
        )
        codes.update(matched)
        codes.update(category_matches)
    return codes, coverage


def collect(cache_dir, out, as_of, exam_codes, annual=None, offline=False):
    cache = Cache(cache_dir, offline)
    coverage, notices, failures = [], {}, []
    for channel, url in INDEXES.items():
        queries = ("試題", "答案", "給分", "送分") if channel == "latest_news" else ("",)
        for query in queries:
            try:
                rows = scan_index(cache, channel, url, query, coverage)
                for row in rows:
                    if title_in_scope(row["title"], channel):
                        notices.setdefault(row["url"], dict(row, channel=channel, listing_url=url))
            except (OSError, ValueError, subprocess.SubprocessError) as e:
                failures.append(dict(url=url, channel=channel, query=query, error=str(e)))

    def examine(code):
        url = BASE + "exam/wFrmExamDetail.aspx?c=" + code
        key = "exam-" + code + ".html"
        try:
            body = cache.fetch(url, key)
            page = Page(body)
            links = [a for a in page.links if a.get("id", "") == "ctl00_holderContent_lnkExam03"]
            if not any(re.search(r"[?&]e=" + code + r"(&|$)", a["href"]) for a in links):
                status = "no_matching_exam_link"
                if b"htmNotFoundPage" in body:
                    status = "official_not_found_redirect"
                elif b"htmErrorPage" in body:
                    status = "official_error_redirect"
                coverage.append(
                    dict(
                        channel="exam_detail",
                        exam_code=code,
                        url=url,
                        cache_key=key,
                        sha256=sha(body),
                        status=status,
                        matched_urls=[],
                    )
                )
                return
            # These exam-specific pages contain individual posts, ordinary instructions and files.
            # Keep decisions and answer changes only; procedural handouts are not award decisions.
            relevant = []
            for link in page.links:
                if "holderContent_repExamList_" not in link.get("id", ""):
                    continue
                title = link["text"] or link.get("title", "")
                if not title_in_scope(title, "exam_detail"):
                    continue
                target = official(url, link["href"])
                if target:
                    relevant.append(target)
                    notices.setdefault(
                        target,
                        dict(
                            url=target,
                            title=title,
                            listing_url=url,
                            publication_date=None,
                            exam_code=code,
                            channel="exam_detail",
                            direct_attachment=link.get("id", "").endswith("_lnkFiles"),
                        ),
                    )
            coverage.append(
                dict(
                    channel="exam_detail",
                    exam_code=code,
                    url=url,
                    cache_key=key,
                    sha256=sha(body),
                    status="exam_verified",
                    links_examined=sum("holderContent_repExamList_" in a.get("id", "") for a in page.links),
                    matched_urls=relevant,
                )
            )
        except (OSError, ValueError, subprocess.SubprocessError) as e:
            failures.append(dict(url=url, channel="exam_detail", exam_code=code, error=str(e)))

    with ThreadPoolExecutor(max_workers=4) as executor:
        list(executor.map(examine, sorted(exam_codes)))
    for url, item in sorted(notices.items()):
        try:
            if item.get("direct_attachment"):
                item["attachments"] = [save_attachment(cache, item["listing_url"], url, item["title"])]
                continue
            key = "notice-" + sha(url.encode())[:20] + ".html"
            body = cache.fetch(url, key)
            if item["title"] not in unescape(re.sub(r"<[^>]*>", "", body.decode("utf-8-sig"))):
                raise ValueError("detail did not contain listed title")
            item.update(cache_key=key, sha256=sha(body), attachments=[])
            for target, label in attachment_links(Page(body), url):
                try:
                    item["attachments"].append(save_attachment(cache, url, target, label))
                except (OSError, ValueError, zipfile.BadZipFile, subprocess.SubprocessError) as e:
                    failures.append(dict(url=target, parent_url=url, error=str(e)))
        except (OSError, ValueError, zipfile.BadZipFile, subprocess.SubprocessError) as e:
            failures.append(dict(url=url, error=str(e)))
        if item["channel"] == "case_law":
            item["title"] = re.sub(r"[\u4e00-\u9fff]○+", "（匿名）", item["title"])
            for attachment in item.get("attachments", []):
                attachment["title"] = re.sub(r"[\u4e00-\u9fff]○+", "（匿名）", attachment["title"])
    out.mkdir(parents=True, exist_ok=True)
    result = dict(
        as_of=as_of,
        annual_sources=annual or [],
        coverage=sorted(
            coverage, key=lambda r: (r["channel"], r.get("exam_code", ""), r.get("query") or "", r.get("page", 0))
        ),
        notices=list(sorted(notices.values(), key=lambda r: r["url"])),
        failures=sorted(failures, key=lambda r: r["url"]),
    )
    (out / "index.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf8")
    write_tables(result, out)
    return result


def write_tsv(path, fields, rows):
    tmp = path.with_name(f"{path.name}.{os.getpid()}.tmp")
    with tmp.open("w", encoding="utf8", newline="") as f:
        writer = csv.DictWriter(f, fields, delimiter="\t", lineterminator="\n", extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    tmp.replace(path)


def write_tables(snapshot, out):
    notices = snapshot["notices"]
    write_tsv(
        out / "notices.tsv",
        ["channel", "title", "publication_date", "listing_url", "url", "sha256", "cache_key"],
        notices,
    )
    files = [a for record in notices for a in record.get("attachments", [])]
    write_tsv(
        out / "attachments.tsv", ["parent_url", "url", "title", "media", "bytes", "sha256", "cache_key"], files
    )
    observed = {r["exam_code"]: r for r in snapshot["coverage"] if r["channel"] == "exam_detail"}
    annual = []
    for year in snapshot["annual_sources"]:
        codes = year["matched_codes"]
        available = [observed[c] for c in codes if c in observed]
        verified = [r for r in available if r["status"] == "exam_verified"]
        annual.append(
            dict(
                year=year["year"],
                archive_exams=year["exam_options"],
                targeted=len(codes),
                responses=len(available),
                verified_exam_pages=len(verified),
                official_not_found=sum(r["status"] == "official_not_found_redirect" for r in available),
                other_unverified=len(available)
                - len(verified)
                - sum(r["status"] == "official_not_found_redirect" for r in available),
                pending=len(codes) - len(available),
                matched_links=sum(len(r["matched_urls"]) for r in verified),
            )
        )
    write_tsv(
        out / "coverage.tsv",
        [
            "year",
            "archive_exams",
            "targeted",
            "responses",
            "verified_exam_pages",
            "official_not_found",
            "other_unverified",
            "pending",
            "matched_links",
        ],
        annual,
    )


def verify_decision_sources(directory, decisions, offline=False):
    """Verify recorded evidence against original bytes. A changed official site needs a new review."""
    specs = json.loads(decisions.read_text(encoding="utf8"))
    cache = Cache(directory, offline)
    checked = 0
    mismatches = []

    def check(source, key):
        nonlocal checked
        body = cache.fetch(source["url"], key)
        if sha(body) != source["sha256"]:
            mismatches.append(source["url"])
        checked += 1

    for source in specs["source_documents"].values():
        check(source, source.get("cache_key") or "notice-" + sha(source["url"].encode())[:20] + ".html")
        for artifact in source.get("attachments", []):
            check(artifact, "attachment-" + sha(artifact["url"].encode())[:20] + ".bin")
    for record in specs["boundary_items"] + specs["clinical_items"]:
        for field in ("original_asset", "corrected_asset"):
            asset = record.get(field)
            if asset:
                exam, category, subject, kind = asset["asset_id"].split("-")[1:5]
                check(asset, "-".join([exam, category, subject, kind]) + ".pdf")
    return checked, mismatches


def weekly_index(cache, out):
    """Search the ministry's separately maintained digitized print archive by its actual title fields."""
    url = BASE + "ExamWeekly/wfrmExamWeekly.aspx?menu_id=922"
    seed = cache.fetch(url, "weekly.html")
    count = re.search(r'lblCount"[^>]*>(\d+)', seed.decode("utf8"))
    logs = []
    papers = {}
    errors = []
    for term in ("試題疑義", "更正答案", "答案更正", "試題更正", "給分", "送分"):
        try:
            found = scan_index(cache, "weekly", url, term, logs)
        except (OSError, ValueError, subprocess.SubprocessError) as e:
            errors.append(dict(query=term, error=str(e)))
            continue
        for row in found:
            record = papers.setdefault(row["url"], dict(row, terms=[], parent_url=url))
            record["terms"].append(term)
    for target, record in papers.items():
        try:
            file = save_attachment(cache, url, target, record["title"])
            record.update(
                sha256=file["sha256"], bytes=file["bytes"], media=file["media"], cache_key=file["cache_key"]
            )
        except (OSError, ValueError, subprocess.SubprocessError) as e:
            errors.append(dict(url=target, error=str(e)))
    out.mkdir(parents=True, exist_ok=True)
    result = dict(
        as_of=cache.path.name,
        parent_url=url,
        parent_sha256=sha(seed),
        unfiltered_total=int(count[1]) if count else None,
        scope="title_keyword_search",
        pages=logs,
        matches=sorted(papers.values(), key=lambda r: r["url"]),
        gaps=errors,
    )
    (out / "weekly.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf8")
    return result


class NewsBody(HTMLParser):
    """Read only article content, excluding the navigation bar shared by every page."""

    def __init__(self, body):
        super().__init__(convert_charrefs=True)
        self.parts = []
        self.hrefs = []
        self.images = []
        self.depth = 0
        self.has_article = False
        self.muted = False
        self.feed(body.decode("utf-8-sig"))

    def handle_starttag(self, tag, attrs):
        args = dict(attrs)
        if tag == "div":
            if self.depth:
                self.depth += 1
            elif "news-content" in args.get("class", "").split():
                self.has_article = True
                self.depth = 1
        if self.depth:
            if tag in {"p", "div", "li", "br", "tr"}:
                self.parts.append("\n")
            if tag in {"script", "style"}:
                self.muted = True
            if tag == "a" and args.get("href"):
                self.hrefs.append((args["href"], args.get("title", "")))
            if tag == "img" and args.get("src"):
                self.images.append((args["src"], args.get("alt") or args.get("title", "")))

    def handle_endtag(self, tag):
        if tag == "div" and self.depth:
            self.depth -= 1
        elif tag in {"script", "style"}:
            self.muted = False

    def handle_data(self, value):
        if self.depth and not self.muted:
            self.parts.append(value)


SIGNALS = {
    "challenge": r"(試題|題目)(疑義|爭議|瑕疵|錯誤|勘誤)",
    "key_revision": r"(更正|修正).{0,5}(答案|試題)|答案.{0,5}(更正|修正|勘誤)|改列.{0,3}答案|放寬評閱",
    "award": r"給分|均得分|不予計分|重新計分|重新評閱|送分",
}
FILE_LINK = re.compile(
    r"\.(?:pdf|docx?|odt|od[sp]|xlsx?|pptx?|rtf|txt|zip|jpe?g|png|tif|tiff)(?:[?#]|$)|(?:FileHandler|wHand\w*File)\.ashx",
    re.I,
)


def signals(content):
    canonical = "".join(unicodedata.normalize("NFKC", content).split())
    return [name for name, pattern in SIGNALS.items() if re.search(pattern, canonical)]


def government_host(host):
    return bool(
        host and (host in {"moex.gov.tw", "exam.gov.tw"} or host.endswith((".moex.gov.tw", ".exam.gov.tw")))
    )


def ocr_engine(data):
    model = data / "chi_tra.traineddata"
    executable = shutil.which("tesseract")
    if not executable and os.name == "nt":
        installed = Path(os.environ.get("ProgramFiles", "C:/Program Files")) / "Tesseract-OCR" / "tesseract.exe"
        if installed.is_file():
            executable = str(installed)
    if not executable or not model.is_file():
        return None
    return (executable, str(data), sha(model.read_bytes()))


def image_text(image, engine):
    executable, data, _ = engine
    result = subprocess.run(
        [executable, "stdin", "stdout", "--tessdata-dir", data, "-l", "chi_tra", "--oem", "1"],
        input=image,
        capture_output=True,
        timeout=90,
        check=True,
    )
    return result.stdout.decode("utf8")


def extract_file(path, engine=None):
    """Yield page/paragraph locators for native text or OCR, without publishing article text."""
    raw = path.read_bytes()
    if raw.startswith(b"%PDF-"):
        import pymupdf

        with pymupdf.open(stream=raw, filetype="pdf") as doc:
            parts = []
            for i, p in enumerate(doc, 1):
                text = p.get_text()
                label = f"page-{i}"
                if not text.strip() and engine and p.get_images():
                    text = image_text(p.get_pixmap(dpi=180, alpha=False).tobytes("png"), engine)
                    label += "-ocr"
                parts.append((label, text))
            return "pdf", parts
    if raw.startswith(b"PK"):
        with zipfile.ZipFile(BytesIO(raw)) as z:
            entries = z.namelist()
            if "word/document.xml" in entries:
                return "docx", [
                    (f"paragraph-{i}", t) for i, t in enumerate(extract_docx_paragraphs(raw), 1) if t.strip()
                ]
            if "content.xml" in entries and "mimetype" in entries:
                root = ElementTree.fromstring(z.read("content.xml"))
                ns = "{urn:oasis:names:tc:opendocument:xmlns:text:1.0}"
                return "opendocument", [
                    (f"paragraph-{i}", "".join(p.itertext())) for i, p in enumerate(root.iter(ns + "p"), 1)
                ]
            if "xl/workbook.xml" in entries or "ppt/presentation.xml" in entries:
                docs = [
                    n
                    for n in entries
                    if n == "xl/sharedStrings.xml"
                    or re.fullmatch(r"xl/worksheets/sheet\d+\.xml|ppt/slides/slide\d+\.xml", n)
                ]
                return "office_xml", [(n, " ".join(ElementTree.fromstring(z.read(n)).itertext())) for n in docs]
            return "zip", []
    if raw.startswith(bytes.fromhex("D0CF11E0A1B11AE1")):
        if shutil.which("antiword"):
            doc = subprocess.run(["antiword", str(path)], capture_output=True, timeout=30)
            if doc.returncode == 0:
                return "doc", [("document", doc.stdout.decode("utf8", errors="replace"))]
        return "legacy_office", []
    if raw.startswith((b"\x89PNG", b"\xff\xd8\xff", b"GIF8", b"II\x2a\x00", b"MM\x00\x2a")):
        return "raster_image", [("image-ocr", image_text(raw, engine))] if engine else []
    return "unsupported", []


def fulltext(cache, out, cached_posts=False, engine=None):
    out.mkdir(parents=True, exist_ok=True)
    page_logs = []
    articles = {}
    issues = []
    total = {}
    list_cache = Cache(cache.path, offline=True) if cached_posts else cache
    for label in ("latest_news", "exam_bulletins", "emergency"):
        url = INDEXES[label]
        try:
            rows = scan_index(list_cache, label, url, "", page_logs, all_titles=(label == "latest_news"))
        except (OSError, ValueError, subprocess.SubprocessError) as e:
            # Preserve every successfully verified listing page on partial/offline runs.
            rows = [
                r
                for entry in page_logs
                if entry["channel"] == label
                for r in list_rows((cache.path / entry["cache_key"]).read_bytes(), url)
            ]
            issues.append(dict(channel=label, error=str(e)))
        reported = [
            v["reported_total"] for v in page_logs if v["channel"] == label and v["reported_total"] is not None
        ]
        if not reported and (cache.path / (label + ".html")).exists():
            seed = (cache.path / (label + ".html")).read_text(encoding="utf8")
            count = re.search(r'lblCount"[^>]*>(\d+)', seed)
            if count:
                reported = [int(count[1])]
        total[label] = (
            reported[0]
            if reported
            else (0 if not rows and not any(i["channel"] == label for i in issues) else None)
        )
        for row in rows:
            articles[row["url"]] = dict(row, channel=label, status="pending")

    def inspect_article(url):
        key = "notice-" + sha(url.encode())[:20] + ".html"
        source = articles[url]
        if cached_posts and not (cache.path / key).is_file():
            return dict(source, status="pending"), []
        try:
            raw = cache.fetch(url, key)
            body = NewsBody(raw)
            if not body.has_article:
                return dict(source, status="article_element_missing", sha256=sha(raw), cache_key=key), []
            sentences = "".join(body.parts).strip()
            combined = dict(attachment_links(Page(raw), url))
            for href, title in body.hrefs:
                if FILE_LINK.search(href):
                    target = urljoin(url, href)
                    if urlsplit(target).scheme in ("http", "https"):
                        combined.setdefault(target, title)
            for href, title in body.images:
                target = urljoin(url, href)
                if urlsplit(target).scheme in ("http", "https"):
                    combined.setdefault(target, title)
            links = [dict(url=u, title=t, parent_url=url) for u, t in combined.items()]
            return dict(
                source,
                status="text_scanned" if sentences else "empty_article_body",
                sha256=sha(raw),
                cache_key=key,
                text_characters=len(sentences),
                text_sha256=sha(sentences.encode()),
                signals=",".join(signals(sentences)),
                signal_locators=json.dumps(
                    {
                        f"block-{n}": found
                        for n, t in enumerate((v for v in sentences.splitlines() if v.strip()), 1)
                        if (found := signals(t))
                    },
                    ensure_ascii=False,
                ),
                attachments=len(links),
            ), links
        except (OSError, ValueError, subprocess.SubprocessError) as e:
            return dict(
                source, status="pending" if isinstance(e, FileNotFoundError) else "fetch_error", error=str(e)
            ), []

    related = {}
    for url in articles:
        articles[url].setdefault("signals", "")

    def checkpoint(files):
        ordered = sorted(
            articles.values(), key=lambda x: (x.get("publication_date") or "", x["url"]), reverse=True
        )
        write_tsv(
            out / "articles.tsv",
            [
                "channel",
                "publication_date",
                "title",
                "url",
                "status",
                "sha256",
                "cache_key",
                "text_characters",
                "text_sha256",
                "signals",
                "signal_locators",
                "attachments",
                "error",
            ],
            ordered,
        )
        rows = []
        for parent, url in sorted(related):
            rows.append(dict(related[parent, url], **files.get(url, {"status": "pending"})))
        write_tsv(
            out / "attachments.tsv",
            [
                "parent_url",
                "url",
                "title",
                "status",
                "media",
                "sha256",
                "cache_key",
                "bytes",
                "segments",
                "empty_segments",
                "ocr_segments",
                "signal_locators",
                "error",
            ],
            rows,
        )
        by_channel = {k: sum(a["channel"] == k for a in ordered) for k in total}
        summary = dict(
            as_of=cache.path.name,
            ocr_model_sha256=engine[2] if engine else None,
            reported=total,
            indexed=by_channel,
            unindexed={k: (n - by_channel[k]) if n is not None else None for k, n in total.items()},
            unique_articles=len(ordered),
            bodies_scanned=sum(a["status"] == "text_scanned" for a in ordered),
            bodies_pending=sum(a["status"] not in ("text_scanned", "empty_article_body") for a in ordered),
            empty_bodies=sum(a["status"] == "empty_article_body" for a in ordered),
            article_statuses={
                s: sum(a["status"] == s for a in ordered) for s in sorted({a["status"] for a in ordered})
            },
            attachment_links=len(rows),
            unique_attachment_urls=len({r["url"] for r in rows}),
            attachment_statuses={
                s: len({r["url"] for r in rows if r["status"] == s}) for s in sorted({r["status"] for r in rows})
            },
            listing_pages=page_logs,
            listing_gaps=issues,
        )
        (out / "coverage.json").write_text(
            json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf8"
        )
        return summary

    # Rehydrate cached articles before reporting a new checkpoint on a resumed run.
    for url in articles:
        raw_key = "notice-" + sha(url.encode())[:20] + ".html"
        if (cache.path / raw_key).is_file():
            item, links = inspect_article(url)
            articles[url] = item
            for link in links:
                related[link["parent_url"], link["url"]] = link
    checkpoint({})
    with ThreadPoolExecutor(max_workers=8) as pool:
        tasks = {pool.submit(inspect_article, u): u for u in articles if articles[u]["status"] == "pending"}
        for index, task in enumerate(as_completed(tasks), 1):
            item, links = task.result()
            articles[tasks[task]] = item
            for link in links:
                related[link["parent_url"], link["url"]] = link
            if index % 50 == 0:
                checkpoint({})

    def inspect_file(url):
        parsed = urlsplit(url)
        if parsed.scheme not in ("http", "https") or not government_host(parsed.hostname):
            return dict(status="external_or_http_reference")
        key = "attachment-" + sha(url.encode())[:20] + ".bin"
        result = {}
        try:
            fetch_url = parsed._replace(scheme="https").geturl()
            raw = cache.fetch(fetch_url, key)
            result.update(cache_key=key, sha256=sha(raw), bytes=len(raw))
            extraction_key = sha(
                (
                    "notice-text-v2 "
                    + json.dumps(SIGNALS, sort_keys=True)
                    + result["sha256"]
                    + " "
                    + (engine[2] if engine else "native")
                ).encode()
            )
            extraction = cache.path / ("extract-" + extraction_key + ".json")
            if extraction.is_file():
                return dict(result, **json.loads(extraction.read_text(encoding="utf8")))
            kind, parts = extract_file(cache.path / key, engine)
            empty = sum(not text.strip() for _, text in parts)
            status = "text_scanned" if parts and empty < len(parts) else "no_extractable_text"
            if kind == "pdf" and 0 < empty < len(parts):
                status = "partial_pdf_native_text"
            hits = {loc: terms for loc, content in parts if (terms := signals(content))}
            metadata = dict(
                status=status,
                media=kind,
                segments=len(parts),
                empty_segments=empty,
                ocr_segments=sum(loc.endswith("-ocr") for loc, _ in parts),
                signal_locators=json.dumps(hits, ensure_ascii=False) if hits else "",
            )
            tmp = extraction.with_name(f"{extraction.name}.{os.getpid()}-{threading.get_ident()}.tmp")
            tmp.write_text(json.dumps(metadata, ensure_ascii=False), encoding="utf8")
            tmp.replace(extraction)
            result.update(metadata)
        except (
            OSError,
            ValueError,
            RuntimeError,
            ImportError,
            zipfile.BadZipFile,
            ElementTree.ParseError,
            subprocess.SubprocessError,
        ) as e:
            result.update(
                status="pending" if isinstance(e, FileNotFoundError) else "fetch_or_extraction_error", error=str(e)
            )
        return result

    files = {}
    checkpoint(files)
    with ThreadPoolExecutor(max_workers=4) as pool:
        tasks = {pool.submit(inspect_file, u): u for u in {u for _, u in related}}
        for index, task in enumerate(as_completed(tasks), 1):
            files[tasks[task]] = task.result()
            if index % 25 == 0:
                checkpoint(files)
    return checkpoint(files)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--as-of", type=date.fromisoformat, required=True)
    parser.add_argument("--cache", type=Path, default=ROOT / "data" / "moex-notices")
    parser.add_argument("--out", type=Path, default=ROOT / "datasets" / "moex" / "notices")
    parser.add_argument(
        "--exam-codes", help="comma-separated exam codes. Default: every exam in twmed-v1 sources.tsv"
    )
    parser.add_argument(
        "--year-cache",
        type=Path,
        help="use all medical exams from official year-YYYY.html option lists, 1992–2026",
    )
    parser.add_argument(
        "--category-index",
        type=Path,
        default=ROOT / "datasets/moex/index/categories.tsv",
        help="also include verified human medical categories in exams with generic titles",
    )
    parser.add_argument(
        "--verify-decisions",
        action="store_true",
        help="verify original post/attachment hashes for curated item rulings",
    )
    parser.add_argument(
        "--offline",
        action="store_true",
        help="publish an intermediate inventory from cached responses with explicit gaps",
    )
    parser.add_argument(
        "--weekly",
        action="store_true",
        help="search the digitized 1985–2007 print weekly index and retain linked originals",
    )
    parser.add_argument(
        "--fulltext",
        action="store_true",
        help="index all three general bulletin channels and search every available article/attachment body",
    )
    parser.add_argument(
        "--cached-posts",
        action="store_true",
        help="scan already cached bodies and retrieve their attachments, allowing incremental batches",
    )
    args = parser.parse_args()
    if args.weekly:
        report = weekly_index(Cache(args.cache / args.as_of.isoformat(), args.offline), args.out)
        print(
            "weekly archive",
            report["unfiltered_total"],
            "keyword matches",
            len(report["matches"]),
            "gaps",
            len(report["gaps"]),
        )
        return int(bool(report["gaps"]))
    if args.fulltext:
        summary = fulltext(
            Cache(args.cache / args.as_of.isoformat(), args.offline),
            args.out / "fulltext",
            args.cached_posts,
            ocr_engine(args.cache / "ocr"),
        )
        print(
            summary["bodies_scanned"],
            "article bodies scanned of",
            summary["unique_articles"],
            "unique indexed; files:",
            summary["attachment_statuses"],
        )
        return (
            1
            if summary["listing_gaps"]
            or summary["bodies_scanned"] + summary["empty_bodies"] < summary["unique_articles"]
            or any(s in summary["attachment_statuses"] for s in ("pending", "fetch_or_extraction_error"))
            else 0
        )
    if args.verify_decisions:
        checked, changed = verify_decision_sources(
            args.cache / args.as_of.isoformat(), args.out / "decisions.json", args.offline
        )
        print("verified:", checked - len(changed), "/", checked)
        for url in changed:
            print("different source bytes:", url)
        return 1 if changed else 0
    annual = []
    if args.year_cache:
        codes, annual = annual_exam_codes(args.year_cache, range(1992, args.as_of.year + 1), args.category_index)
    elif args.exam_codes:
        codes = set(args.exam_codes.split(","))
        if any(not re.fullmatch(r"\d{6}", code) for code in codes):
            parser.error("expected six-digit exam codes")
    else:
        with (ROOT / "datasets/twmed/sources.tsv").open(encoding="utf8") as f:
            codes = {r[0] for r in list(csv.reader(f, delimiter="\t"))[1:]}
    result = collect(
        args.cache / args.as_of.isoformat(), args.out, args.as_of.isoformat(), codes, annual, args.offline
    )
    print(
        "index pages:",
        len(result["coverage"]),
        "notices:",
        len(result["notices"]),
        "fetch/parse gaps:",
        len(result["failures"]),
    )
    return 1 if result["failures"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
