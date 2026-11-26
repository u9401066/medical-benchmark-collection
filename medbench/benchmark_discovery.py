"""Discover PubMed metadata for medical LLM evaluation papers by inclusive Entrez date."""

from __future__ import annotations

import argparse
from datetime import date, datetime, timedelta, timezone
import http.client
import json
from pathlib import Path
import time
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from .moex_archive import atomic

QUERY = (
    '("large language model*"[tiab] OR LLM[tiab] OR LLMs[tiab] OR ChatGPT[tiab]) '
    'AND (medical[tiab] OR medicine[tiab] OR clinical[tiab] OR healthcare[tiab] OR "health care"[tiab]) '
    'AND (benchmark*[tiab] OR dataset*[tiab] OR "question answering"[tiab] OR rubric*[tiab] '
    "OR ((evaluat*[tiab] OR validat*[tiab]) AND (temporal[tiab] OR outdated[tiab] "
    "OR guideline*[tiab] OR evidence[tiab] OR citation*[tiab] OR hallucinat*[tiab] "
    "OR unanswerable[tiab] OR abstain*[tiab] OR abstention[tiab])))"
)
EUTILS = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/"
SEARCH_LIMIT = 9_999  # PubMed currently caps a single ESearch response at 9,999 IDs.
SUMMARY_BATCH = 100


def request_json(endpoint, params):
    query = urlencode(
        {
            "db": "pubmed",
            "retmode": "json",
            "tool": "medical_benchmark_collection",
            **params,
        }
    )
    req = Request(
        EUTILS + endpoint + ".fcgi?" + query,
        headers={
            "Accept": "application/json",
            "User-Agent": "medical_benchmark_collection/1.0",
        },
    )
    for attempt in range(3):
        time.sleep(0.35)  # NCBI allows three requests/second without an API key.
        try:
            with urlopen(req, timeout=30) as response:
                body = json.load(response)
            if not isinstance(body, dict) or "error" in body:
                raise ValueError(
                    f"{endpoint} returned an invalid response: {str(body)[:250]}"
                )
            return body
        except HTTPError as exc:
            if attempt == 2 or exc.code not in {429, 500, 502, 503, 504}:
                raise
            delay = exc.headers.get("Retry-After", "")
            time.sleep(
                int(delay) if delay.isdecimal() and int(delay) <= 60 else 2**attempt
            )
        except (OSError, http.client.HTTPException):
            if attempt == 2:
                raise
            time.sleep(2**attempt)


def discover(start: date, end: date) -> dict:
    if start > end:
        raise ValueError("start date must not be after end date")
    search = {
        "term": QUERY,
        "datetype": "edat",
        "mindate": start.strftime("%Y/%m/%d"),
        "maxdate": end.strftime("%Y/%m/%d"),
        "retmax": SEARCH_LIMIT,
    }
    report = {
        "status": "error",
        "retrieved_at_utc": datetime.now(timezone.utc).isoformat(),
        "query": QUERY,
        "date_field": "EDAT",
        "start": start.isoformat(),
        "end": end.isoformat(),
        "search_url": EUTILS
        + "esearch.fcgi?"
        + urlencode({"db": "pubmed", "retmode": "json", **search}),
        "total_matches": None,
        "unique_pmids_returned": 0,
        "records_retrieved": 0,
        "missing_count": None,
        "missing_summary_pmids": [],
        "warnings": [],
        "errors": [],
        "records": [],
    }
    failures = (OSError, http.client.HTTPException, ValueError, KeyError, TypeError)
    try:
        result = request_json("esearch", search)["esearchresult"]
        count = int(result["count"])
        ids = result["idlist"]
        if (
            count < 0
            or not isinstance(ids, list)
            or any(
                not isinstance(uid, str)
                or not uid.isascii()
                or not uid.isdigit()
                or int(uid) <= 0
                for uid in ids
            )
        ):
            raise ValueError("invalid PubMed count or ID list")
        pmids = list(dict.fromkeys(ids))
        if len(pmids) > count:
            raise ValueError("ESearch returned more unique IDs than its declared count")
        if result.get("ERROR"):
            raise ValueError(str(result["ERROR"]))
        # PubMed may return matches even if one OR phrase is absent from its index.
        errors = result.get("errorlist") or {}
        if not isinstance(errors, dict):
            raise ValueError(f"invalid ESearch error list: {errors}")
        errors = {key: messages for key, messages in errors.items() if messages}
        if set(errors) - {"phrasesnotfound"}:
            raise ValueError(f"ESearch query error: {errors}")
        if errors:
            report["warnings"].append(errors)
        if result.get("warninglist"):
            report["warnings"].append(result["warninglist"])
        report.update(total_matches=count, unique_pmids_returned=len(pmids))
    except failures as exc:
        report["errors"].append(f"ESearch: {exc}")
        return report

    if len(pmids) != count:
        report["warnings"].append(
            f"ESearch returned {len(pmids)} unique IDs from {count} matches; rerun a narrower EDAT window"
        )
    for i in range(0, len(pmids), SUMMARY_BATCH):
        batch = pmids[i : i + SUMMARY_BATCH]
        try:
            results = request_json("esummary", {"id": ",".join(batch)})["result"]
            if not isinstance(results, dict):
                raise ValueError("invalid PubMed ESummary result")
        except failures as exc:
            report["errors"].append(f"ESummary batch {i // SUMMARY_BATCH + 1}: {exc}")
            report["missing_summary_pmids"].extend(batch)
            continue
        for pmid in batch:
            article = results.get(pmid)
            if (
                not isinstance(article, dict)
                or article.get("uid") != pmid
                or article.get("error")
                or not article.get("title")
            ):
                report["missing_summary_pmids"].append(pmid)
                continue
            report["records"].append(
                {
                    "pmid": pmid,
                    "title": article["title"],
                    "publication_date": article.get("pubdate", ""),
                    "electronic_publication_date": article.get("epubdate", ""),
                    "url": f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
                }
            )
    report["records_retrieved"] = len(report["records"])
    report["missing_count"] = count - report["records_retrieved"]
    report["status"] = (
        "partial" if report["missing_count"] else ("complete" if count else "empty")
    )
    return report


def write_report(path: Path, report: dict) -> None:
    atomic(
        path, (json.dumps(report, indent=2, ensure_ascii=False) + "\n").encode("utf-8")
    )


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--start",
        type=date.fromisoformat,
        help="inclusive EDAT, defaults to 13 days before end",
    )
    parser.add_argument(
        "--end",
        type=date.fromisoformat,
        help="inclusive EDAT, defaults to today's UTC date",
    )
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    end = args.end or datetime.now(timezone.utc).date()
    start = args.start or end - timedelta(days=13)
    if start > end:
        parser.error("--start must not be after --end")
    report = discover(start, end)
    write_report(args.out, report)
    print(
        f"{report['status']}: {report['records_retrieved']} retrieved / {report['total_matches']} matches; {args.out}"
    )
    return {"complete": 0, "empty": 0, "error": 1, "partial": 2}[report["status"]]


if __name__ == "__main__":
    raise SystemExit(main())
