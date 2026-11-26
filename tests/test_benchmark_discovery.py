from datetime import date
import json
from urllib.error import URLError

import pytest

from medbench import benchmark_discovery as discovery


def test_overlapping_windows_keep_canonical_pubmed_ids_and_dates(monkeypatch, tmp_path):
    searches, batches = [], []

    def api(endpoint, params):
        if endpoint == "esearch":
            searches.append(params)
            return {
                "esearchresult": {
                    "count": "2",
                    "idlist": ["123", "456", "123"],
                    "errorlist": {"phrasesnotfound": ["one rare synonym"]},
                }
            }
        batches.append(params["id"])
        return {
            "result": {
                uid: {
                    "uid": uid,
                    "title": "Clinical benchmark",
                    "pubdate": "2025 Dec",
                    "epubdate": "2025 Nov 28",
                }
                for uid in params["id"].split(",")
            }
        }

    monkeypatch.setattr(discovery, "request_json", api)
    out = tmp_path / "cache" / "report.json"
    end_dates = ("2026-11-19", "2026-11-26")
    for end in end_dates:
        assert discovery.main(["--end", end, "--out", str(out)]) == 0
    assert [(p["mindate"], p["maxdate"]) for p in searches] == [
        ("2026/11/06", "2026/11/19"),
        ("2026/11/13", "2026/11/26"),
    ]
    assert all(
        p["datetype"] == "edat" and p["term"] == discovery.QUERY for p in searches
    )
    assert batches == ["123,456", "123,456"]
    report = json.loads(out.read_text(encoding="utf-8"))
    assert report["status"] == "complete"
    assert report["warnings"] == [{"phrasesnotfound": ["one rare synonym"]}]
    assert (
        report["total_matches"]
        == report["unique_pmids_returned"]
        == report["records_retrieved"]
        == 2
    )
    assert report["missing_count"] == 0
    assert report["records"][0] == {
        "pmid": "123",
        "title": "Clinical benchmark",
        "url": "https://pubmed.ncbi.nlm.nih.gov/123/",
        "publication_date": "2025 Dec",
        "electronic_publication_date": "2025 Nov 28",
    }


def test_unreturned_ids_and_missing_summaries_keep_their_denominators(
    monkeypatch, tmp_path
):
    monkeypatch.setattr(discovery, "SUMMARY_BATCH", 1)

    def api(endpoint, params):
        if endpoint == "esearch":
            return {"esearchresult": {"count": "4", "idlist": ["12", "13", "14"]}}
        if params["id"] == "12":
            raise URLError("connection lost")
        if params["id"] == "13":
            return {"result": {"13": {"uid": "99", "title": "Different record"}}}
        return {"result": {"14": {"uid": "14", "title": "Retrieved"}}}

    monkeypatch.setattr(discovery, "request_json", api)
    out = tmp_path / "report.json"
    assert (
        discovery.main(
            ["--start", "2026-01-01", "--end", "2026-01-04", "--out", str(out)]
        )
        == 2
    )
    report = json.loads(out.read_text(encoding="utf-8"))
    assert report["status"] == "partial" and report["warnings"] and report["errors"]
    assert report["missing_summary_pmids"] == ["12", "13"]
    assert report["missing_count"] == 3
    assert report["records"][0]["pmid"] == "14"


def test_real_zero_and_query_error_are_distinct(monkeypatch, tmp_path):
    out = tmp_path / "zero.json"
    empty = {
        "esearchresult": {
            "count": "0",
            "idlist": [],
            "warninglist": {"outputmessages": ["No items found."]},
        }
    }
    monkeypatch.setattr(discovery, "request_json", lambda *args: empty)
    assert discovery.main(["--out", str(out)]) == 0
    assert json.loads(out.read_text(encoding="utf-8"))["status"] == "empty"
    empty["esearchresult"]["errorlist"] = {"fieldsnotfound": ["badfield"]}
    assert discovery.main(["--out", str(out)]) == 1
    report = json.loads(out.read_text(encoding="utf-8"))
    assert (
        report["status"] == "error"
        and report["missing_count"] is None
        and report["total_matches"] is None
    )


def test_invalid_date_range_and_atomic_write_failure_preserve_prior_report(tmp_path):
    out = tmp_path / "report.json"
    discovery.write_report(out, {"status": "empty"})
    before = out.read_bytes()
    with pytest.raises(ValueError):
        discovery.discover(date(2026, 11, 2), date(2026, 11, 1))
    with pytest.raises(TypeError):
        discovery.write_report(out, {"broken": object()})
    assert out.read_bytes() == before
    assert list(tmp_path.iterdir()) == [out]
