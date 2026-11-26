"""Inventory attachments on older, standalone MOEX exam pages and compare their actual bytes."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import defaultdict
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import quote, urljoin, urlsplit
from urllib.request import Request

from . import moex_archive as archive
from .moex_coverage import write


class Attachments(HTMLParser):
    def __init__(self):
        super().__init__()
        self.current = None
        self.links = []

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            fields = dict(attrs)
            self.current = [fields.get("href") or "", fields.get("title") or "", ""]

    def handle_data(self, data):
        if self.current is not None:
            self.current[2] += data

    def handle_endtag(self, tag):
        if tag == "a" and self.current is not None:
            self.links.append(self.current)
            self.current = None


def listing(body, page_url):
    charset = re.search(br"charset\s*=\s*[\"']?([\w-]+)", body[:3000], re.I)
    encoding = charset[1].decode("ascii") if charset else "utf-8-sig"
    if encoding.lower() in {"big5", "big-5"}:
        encoding = "cp950"
    parsed = Attachments()
    parsed.feed(body.decode(encoding))
    rows = []
    for href, title, label in parsed.links:
        label = label.strip()
        if not re.search(r"試題|答案|更正|送分", label + title):
            continue
        source = urljoin(page_url, quote(href.strip(), safe="/%():?=&.+,-_")) if href.strip() else ""
        if source and (not archive.official(source) or not re.search(r"\.(pdf|docx?|zip|rtf)$", urlsplit(source).path, re.I)):
            continue
        role = ("A" if "所有測驗題標準答案" in label else "M" if "更正" in label + title
                else "S" if "答案" in label else "Q" if "試題" in label else "other")
        rows.append(dict(asset_type=role, label=label, title=title.strip(), source_url=source))
    return rows


def export(cache, manifest, exam_manifest, out):
    official = defaultdict(set)
    for path in (manifest, exam_manifest):
        for r in archive.read_tsv(path) if path.is_file() else ():
            if r["status"] == "verified" and r["sha256"]:
                official[r["exam_code"], r["asset_type"], r["sha256"]].add(r["paper_id"] or r["exam_code"])
    sources = []
    links = []
    for meta_path in sorted((cache / "legacy-pages").glob("*.json")):
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        body = (cache / meta["local_path"]).read_bytes()
        if hashlib.sha256(body).hexdigest() != meta["sha256"]:
            raise ValueError("Source page hash mismatch: " + meta["url"])
        records = listing(body, meta["url"])
        sources.append({**meta, "file_links": sum(bool(r["source_url"]) for r in records),
                        "empty_links": sum(not r["source_url"] for r in records)})
        for seq, record in enumerate(records, 1):
            url = record["source_url"]
            receipt = archive.cached(cache, url, verify=True) if url else {}
            digest = receipt.get("sha256", "")
            matches = official[meta["exam_code"], record["asset_type"], digest] if digest else set()
            links.append({**record, "exam_code": meta["exam_code"], "page_sha256": meta["sha256"], "link_number": seq,
                          "status": receipt.get("status") or ("pending" if url else "empty_href"),
                          "format": receipt.get("format", ""), "sha256": digest, "local_path": receipt.get("local_path", ""),
                          "matching_official_ids_by_sha256": "|".join(sorted(matches))})
    write(out / "pages.tsv", ["exam_code", "url", "sha256", "retrieved_at", "local_path", "file_links", "empty_links"], sources)
    write(out / "links.tsv", ["exam_code", "page_sha256", "link_number", "asset_type", "label", "title", "source_url",
                              "status", "format", "sha256", "local_path", "matching_official_ids_by_sha256"], links)
    return {"pages": len(sources), "link_entries": len(links), "verified_links": sum(r["status"] == "verified" for r in links)}


def collect(exam, cache, attachments):
    if not re.fullmatch(r"[0-9]{6}", exam):
        raise ValueError("Expected a six-digit official exam code")
    url = f"https://www.moex.gov.tw/other/{exam}/query.html"
    client = archive.opener()
    with client.open(Request(url, headers={"User-Agent": archive.UA}), timeout=40) as response:
        body = response.read()
    records = listing(body, url)
    if not any(r["source_url"] for r in records):
        raise ValueError("No official exam document links found on " + url)
    digest = hashlib.sha256(body).hexdigest()
    path = Path("legacy-pages", "blobs", digest + ".html")
    archive.atomic(cache / path, body)
    metadata = dict(exam_code=exam, url=url, sha256=digest, retrieved_at=archive.now(), local_path=path.as_posix())
    archive.atomic(cache / "legacy-pages" / (exam + ".json"), json.dumps(metadata).encode())
    if attachments:
        for source in dict.fromkeys(r["source_url"] for r in records if r["source_url"]):
            if archive.cached(cache, source).get("status") != "verified":
                archive.acquire({"source_url": source}, cache, client)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--exam", action="append", default=[], help="confirmed static exam page code, repeatable")
    p.add_argument("--attachments", action="store_true")
    p.add_argument("--cache", type=Path, default=Path("data/moex/archive"))
    p.add_argument("--manifest", type=Path, default=Path("datasets/moex/archive/files.tsv"))
    p.add_argument("--exam-manifest", type=Path, default=Path("datasets/moex/archive/exam-files.tsv"))
    p.add_argument("--out", type=Path, default=Path("datasets/moex/legacy"))
    args = p.parse_args()
    for exam in args.exam:
        collect(exam, args.cache, args.attachments)
    print(json.dumps(export(args.cache, args.manifest, args.exam_manifest, args.out)))


if __name__ == "__main__":
    main()
