"""Check the exact public HTML passages used by date-sensitive draft answers."""

import argparse
import gzip
import hashlib
import io
import json
import re
import time
import zlib
from datetime import date
from http.client import HTTPException
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

from lxml import etree, html

from .moex_archive import atomic


MAX_HTML_BYTES = 8_000_000


def read_html_body(response):
    content = response.read(MAX_HTML_BYTES + 1)
    if len(content) > MAX_HTML_BYTES:
        raise ValueError("Source response exceeds the HTML fetch limit")
    encoding = response.headers.get("Content-Encoding", "identity").strip().lower()
    if encoding in ("", "identity"):
        return content
    if encoding not in ("gzip", "x-gzip"):
        raise ValueError(f"Unsupported source Content-Encoding: {encoding}")
    try:
        with gzip.GzipFile(fileobj=io.BytesIO(content)) as stream:
            decoded = stream.read(MAX_HTML_BYTES + 1)
    except (EOFError, OSError, zlib.error) as exc:
        raise ValueError("Invalid gzip source response") from exc
    if len(decoded) > MAX_HTML_BYTES:
        raise ValueError("Decoded source exceeds the HTML fetch limit")
    return decoded


def fetch(url):
    if urlsplit(url).scheme != "https":
        raise ValueError("Watched sources require an HTTPS URL")
    request = Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (compatible; MedicalBenchmarkCollection/1.0)",
            "Accept-Encoding": "gzip, identity",
        },
    )
    for attempt in range(2):
        try:
            with urlopen(request, timeout=30) as response:
                if urlsplit(response.geturl()).scheme != "https":
                    raise ValueError("Source redirected away from HTTPS")
                return read_html_body(response), response.headers.get_content_charset()
        except (OSError, HTTPException) as error:
            if (
                attempt
                or isinstance(error, HTTPError)
                and error.code not in {502, 503, 504}
            ):
                raise
            time.sleep(1)


def passage_hash(page, xpath):
    nodes = page.xpath(xpath)
    if (
        not isinstance(nodes, list)
        or len(nodes) != 1
        or not isinstance(nodes[0], html.HtmlElement)
    ):
        raise ValueError("The evidence locator must match exactly one HTML element")
    passage = " ".join(nodes[0].text_content().split())
    if not passage:
        raise ValueError("The identified passage is empty")
    return hashlib.sha256(passage.encode("utf-8")).hexdigest()


def check(folder, download=fetch):
    targets = {}
    for path in sorted(folder.glob("*.json")):
        draft = json.loads(path.read_text(encoding="utf-8"))
        for source in draft.get("evidence", []):
            if "watch_xpath" not in source:
                continue
            sha = source["passage_sha256"]
            if (
                not re.fullmatch("[0-9a-f]{64}", sha)
                or not source["watch_xpath"].strip()
            ):
                raise ValueError(f"Invalid passage fingerprint or locator in {path}")
            key = source["url"], source["watch_xpath"], sha
            concept = draft["concept_id"]
            targets.setdefault(key, {})[concept] = draft.get("family_id", concept)

    pages, errors, rows = {}, {}, []
    for (url, xpath, expected), families_by_concept in sorted(targets.items()):
        row = dict(
            url=url,
            watch_xpath=xpath,
            expected_sha256=expected,
            concepts=sorted(families_by_concept),
            family_ids=sorted(set(families_by_concept.values())),
        )
        if url not in pages and url not in errors:
            try:
                body, charset = download(url)
                parser = html.HTMLParser(encoding=charset, no_network=True)
                pages[url] = html.fromstring(body, parser=parser)
            except (
                OSError,
                HTTPException,
                ValueError,
                LookupError,
                etree.LxmlError,
            ) as error:
                errors[url] = str(error)
        try:
            if url in errors:
                raise ValueError(errors[url])
            observed = passage_hash(pages[url], xpath)
            row.update(
                observed_sha256=observed,
                status="unchanged" if expected == observed else "changed",
            )
        except (ValueError, etree.LxmlError) as error:
            row.update(observed_sha256=None, status="unavailable", error=str(error))
        rows.append(row)
    return {"checked_on": date.today().isoformat(), "sources": rows}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--drafts", type=Path, default=Path("drafts"))
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    if not args.drafts.is_dir():
        parser.error(f"Draft folder does not exist: {args.drafts}")
    report = check(args.drafts)
    output = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.out:
        atomic(args.out, output.encode("utf-8"))
    else:
        print(output, end="")
    return int(any(row["status"] != "unchanged" for row in report["sources"]))


if __name__ == "__main__":
    raise SystemExit(main())
