"""Archive official paper files by URL and content digest. Run with python -m medbench.moex_archive."""
from __future__ import annotations

import argparse
import csv
import hashlib
import http.client
import io
import json
import os
import ssl
import tempfile
import time
import urllib.error
import urllib.request
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from .twmed import UA

FIELDS = ("paper_id", "asset_id", "asset_sequence", "year_roc", "exam_code", "exam_name", "category_code", "category_name",
          "subject_code", "subject_name", "scope", "asset_type", "asset_role", "source_url",
          "listed_by", "prior_sha256", "status", "format", "sha256", "bytes", "local_path",
          "retrieved_at", "last_attempt_at", "final_url", "retrieval_method", "bundle_sha256",
          "bundle_member", "prior_comparison", "error")
ROLES = {"Q": "question", "S": "answer", "M": "correction"}


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def read_tsv(path):
    with path.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f, delimiter="\t"))


def atomic(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as f:
        tmp = Path(f.name)
        try:
            f.write(data)
        except BaseException:
            f.close()
            tmp.unlink(missing_ok=True)
            raise
    try:
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)


def plan(index, seed):
    """Keep separate associations when the same URL serves more than one paper."""
    rows = {}
    for raw in read_tsv(seed) if seed else ():
        query = parse_qs(urlsplit(raw["url"]).query)
        exam, category, subject = (query[k][0] for k in ("code", "c", "s"))
        paper = "-".join((exam, category, subject))
        seq = query.get("q", [""])[0]
        rows[paper, raw["file"], raw["url"]] = {
            "asset_id": f"moex-{paper}-{raw['file']}-{seq}", "asset_sequence": seq,
            "paper_id": paper, "year_roc": str(int(exam[:3])), "exam_code": exam,
            "category_code": category, "subject_code": subject, "asset_type": raw["file"],
            "asset_role": ROLES[raw["file"]], "source_url": raw["url"], "category_name": raw["category"],
            "subject_name": raw["subject"], "scope": "medical", "listed_by": "twmed-v1",
            "prior_sha256": raw["sha256"]}
    for path in index:
        for raw in read_tsv(path):
            paper = "-".join(raw[k] for k in ("exam_code", "category_code", "subject_code"))
            key = paper, raw["asset_type"], raw["source_url"]
            prior = rows.get(key, {})
            seq = parse_qs(urlsplit(raw["source_url"]).query).get("q", [""])[0]
            rows[key] = {**prior, "asset_sequence": seq, **{k: raw[k] for k in FIELDS if k in raw},
                         "paper_id": paper, "listed_by": "official-index+twmed-v1" if prior.get("prior_sha256") else "official-index"}
    return sorted(rows.values(), key=lambda r: (int(r["year_roc"]), r["paper_id"], r["asset_type"], r["source_url"]))


def exam_plan(folder, scopes):
    exams = {r["exam_code"] for r in read_tsv(folder / "subjects.tsv") if r["scope"] in scopes}
    return [{**raw, "paper_id": "", "listed_by": "official-exam-index"}
            for raw in read_tsv(folder / "exam_assets.tsv") if raw["exam_code"] in exams]


def official(url):
    parsed = urlsplit(url)
    host = (parsed.hostname or "").lower()
    return parsed.scheme == "https" and (host == "moex.gov.tw" or host.endswith(".moex.gov.tw")) and not parsed.username


class OfficialRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if not official(newurl):
            raise ValueError("redirect outside official HTTPS site")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def opener():
    context = ssl.create_default_context()
    # The ministry's legacy chain is accepted by ordinary browser verification.
    # Keep issuer and hostname checks; omit the additional OpenSSL strict-profile rules.
    context.verify_flags &= ~ssl.VERIFY_X509_STRICT
    return urllib.request.build_opener(OfficialRedirect(), urllib.request.HTTPSHandler(context=context))


def detect(body, content_type, filename):
    if body.lstrip()[:5] == b"%PDF-" and b"%%EOF" in body[-4096:]:
        return "pdf"
    if body.startswith(b"PK\x03\x04"):
        with zipfile.ZipFile(io.BytesIO(body)) as z:
            names = set(z.namelist())
            if "[Content_Types].xml" in names:
                for part, kind in (("word/document.xml", "docx"), ("xl/workbook.xml", "xlsx"), ("ppt/presentation.xml", "pptx")):
                    if part in names:
                        return kind
            return "zip"
    if body.startswith(bytes.fromhex("d0cf11e0a1b11ae1")):
        for kind, mime in (("doc", "msword"), ("xls", "excel"), ("ppt", "powerpoint")):
            if mime in content_type or filename.lower().endswith("." + kind):
                return kind
        return "ole"
    if body.startswith(b"{\\rtf"):
        return "rtf"
    raise ValueError("unsupported document signature (possible HTML response or incomplete download)")


def receipt_path(cache, url):
    digest = hashlib.sha256(url.encode()).hexdigest()
    return cache / "receipts" / digest[:2] / (digest + ".json")


def save_payload(row, cache, body, kind, final_url, extra=None):
    """Store verified source bytes shared by a direct response or an identified official ZIP member."""
    url = row["source_url"]
    digest = hashlib.sha256(body).hexdigest()
    target = Path("blobs", digest[:2], digest + "." + kind)
    existing = cache / target
    if not existing.exists() or hashlib.sha256(existing.read_bytes()).hexdigest() != digest:
        atomic(existing, body)
    result = {"source_url": url, "status": "verified", "format": kind, "sha256": digest,
              "local_path": target.as_posix(), "bytes": len(body), "retrieved_at": now(),
              "final_url": final_url, "retrieval_method": "direct", **(extra or {})}
    path = receipt_path(cache, url)
    version = cache / "versions" / path.stem / (digest + ".json")
    if not version.exists():
        atomic(version, json.dumps(result, ensure_ascii=False).encode())
    atomic(path, json.dumps(result, ensure_ascii=False).encode())
    return result


def acquire(row, cache, client):
    url = row["source_url"]
    path = receipt_path(cache, url)
    if not official(url):
        raise ValueError("URL outside official HTTPS site: " + url)
    try:
        request = urllib.request.Request(url, headers={"User-Agent": UA})
        for attempt in range(3):
            try:
                with client.open(request, timeout=40) as response:
                    body = response.read()
                    kind = detect(body, response.headers.get_content_type(), response.headers.get_filename() or "")
                    final_url = response.geturl()
                break
            except (OSError, http.client.HTTPException) as exc:
                if attempt == 2 or isinstance(exc, urllib.error.HTTPError) and exc.code not in (408, 429, 500, 502, 503, 504):
                    raise
                time.sleep(2 ** (attempt + 1))
        return save_payload(row, cache, body, kind, final_url)
    except (OSError, ValueError, http.client.HTTPException, zipfile.BadZipFile, EOFError) as exc:
        previous = cached(cache, url, verify=True)
        result = previous if previous.get("status") == "verified" else {"source_url": url, "status": "fetch_error"}
        result = {**result, "last_attempt_at": now(), "error": str(exc).replace("\n", " ")[:500]}
    atomic(path, json.dumps(result, ensure_ascii=False).encode())
    return result


def cached(cache, url, verify=False):
    path = receipt_path(cache, url)
    if not path.exists():
        return {}
    result = json.loads(path.read_text(encoding="utf-8"))
    if result.get("status") == "verified":
        blob = cache / result["local_path"]
        if not blob.is_file() or blob.stat().st_size != result["bytes"] or (
                verify and hashlib.sha256(blob.read_bytes()).hexdigest() != result["sha256"]):
            return {"status": "local_file_invalid"}
    return result


def export(rows, receipts, dest):
    buf = io.StringIO(newline="")
    writer = csv.DictWriter(buf, fieldnames=FIELDS, delimiter="\t", lineterminator="\n")
    writer.writeheader()
    for row in rows:
        entry = {"status": "pending", **row, **receipts.get(row["source_url"], {})}
        if entry.get("sha256") and entry.get("prior_sha256"):
            entry["prior_comparison"] = "matches" if entry["sha256"] == entry["prior_sha256"] else "changed"
        writer.writerow(entry)
    atomic(dest, buf.getvalue().encode())


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--index", type=Path, action="append", help="official assets.tsv; may be repeated")
    p.add_argument("--seed", type=Path, default=Path("datasets/twmed/sources.tsv"))
    p.add_argument("--cache", type=Path, default=Path("data/moex/archive"))
    p.add_argument("--manifest", type=Path, help="defaults to files.tsv or exam-files.tsv inside the cache")
    p.add_argument("--exam-level", type=Path, metavar="INDEX_DIR",
                   help="archive whole-exam answer/accessible packages separately from individual papers")
    p.add_argument("--limit", type=int, help="maximum new requests, 0 to export without downloading")
    p.add_argument("--years", help="restrict requests to comma-separated ROC years or ranges")
    p.add_argument("--paper", action="append", help="restrict requests to selected paper IDs (repeatable)")
    p.add_argument("--official-only", action="store_true", help="request only links absent from the original twmed-v1 manifest")
    p.add_argument("--only-errors", action="store_true", help="retry only failed downloads, refresh errors or invalid local files")
    p.add_argument("--scopes", default="medical", help="comma-separated scope values to download")
    p.add_argument("--delay", type=float, default=1, help="minimum seconds between request starts")
    p.add_argument("--refresh", action="store_true", help="revisit verified sources and preserve content revisions")
    p.add_argument("--verify", action="store_true", help="rehash cached files before reuse")
    a = p.parse_args(argv)
    if a.delay < 0 or a.limit is not None and a.limit < 0:
        p.error("delay and limit must be nonnegative")
    idx = Path("datasets/moex/index/assets.tsv")
    allowed = set(a.scopes.split(","))
    if a.exam_level:
        rows = exam_plan(a.exam_level, allowed)
    else:
        rows = plan(a.index if a.index is not None else ([idx] if idx.exists() else []), a.seed)
        rows = [r for r in rows if r["scope"] in allowed]
    dest = a.manifest or a.cache / ("exam-files.tsv" if a.exam_level else "files.tsv")
    receipts = {url: cached(a.cache, url, a.verify) for url in dict.fromkeys(r["source_url"] for r in rows)}
    years = set()
    for part in a.years.split(",") if a.years else ():
        years.update(range(int(part.split("-")[0]), int(part.split("-")[-1]) + 1))
    # Finish recent papers together so the original key, correction and question can be reviewed together.
    queue = sorted(rows, key=lambda r: (-int(r["year_roc"]), r["paper_id"], r["asset_type"]))
    export(rows, receipts, dest)
    seen = set()
    last = 0.0
    attempted = errors = 0
    client = opener()
    try:
        for row in queue:
            if a.limit is not None and attempted >= a.limit:
                break
            url = row["source_url"]
            if url in seen or years and int(row["year_roc"]) not in years:
                continue
            if a.paper and row["paper_id"] not in a.paper or a.official_only and row.get("prior_sha256"):
                continue
            seen.add(url)
            if a.only_errors and not (receipts[url].get("error") or receipts[url].get("status") == "local_file_invalid"):
                continue
            if receipts[url].get("status") == "verified" and not a.refresh and not a.only_errors:
                continue
            time.sleep(max(0, a.delay - (time.monotonic() - last)))
            last = time.monotonic()
            receipts[url] = acquire(row, a.cache, client)
            attempted += 1
            errors += bool(receipts[url].get("error"))
            if attempted % 50 == 0:
                export(rows, receipts, dest)
                print(f"{attempted} requests, {errors} errors, {row['paper_id']}", flush=True)
            if attempted >= 5 and errors == attempted:
                raise RuntimeError("five consecutive initial downloads failed; inspect manifest before retry")
    finally:
        export(rows, receipts, dest)
    print(f"{len(rows)} listed associations, {attempted} requests, {errors} errors", flush=True)
    return int(errors != 0)


if __name__ == "__main__":
    raise SystemExit(main())
