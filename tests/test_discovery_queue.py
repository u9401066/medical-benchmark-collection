import json

import pytest

from medbench.discovery_queue import main, make_queue


def snapshot(path, records, status="complete", total=None):
    path.write_text(
        json.dumps(
            {
                "start": "2026-11-13",
                "end": "2026-11-26",
                "status": status,
                "records_retrieved": len(records),
                "total_matches": len(records) if total is None else total,
                "records": [{"pmid": uid, "title": title} for uid, title in records],
            }
        ),
        encoding="utf-8",
    )
    return path


def test_queue_deduplicates_overlaps_without_double_counting_or_losing_the_resume_position(
    tmp_path,
):
    first = snapshot(tmp_path / "first.json", [("2", "second"), ("1", "old name")])
    second = snapshot(tmp_path / "next.json", [("1", "updated name"), ("3", "third")])
    triage = tmp_path / "triage.tsv"
    triage.write_text(
        "pmid\tstatus\tchecked_on\tstudy_url\n2\tauthor_request\t2026-11-26\thttps://example.org/2\n"
        "9\tpublic_supplement\t2026-11-25\thttps://example.org/9\n",
        encoding="utf-8",
    )
    result = make_queue([first, second], triage)
    assert result["all_searches_complete"]
    assert result["unique_candidate_pmids"] == 3 and result["remaining"] == 2
    assert result["screened_by_status"] == {"author_request": 1}
    assert result["screened_in_snapshots"] == 1 and result[
        "screened_outside_snapshots"
    ] == ["9"]
    assert result["pending"] == [
        {"pmid": "1", "title": "updated name"},
        {"pmid": "3", "title": "third"},
    ]
    with triage.open("a", encoding="utf-8") as stream:
        stream.write("2\tpublic_version_verified\t2026-11-26\thttps://example.org/2\n")
    with pytest.raises(ValueError, match="duplicate"):
        make_queue([first], triage)


def test_partial_search_keeps_acquired_records_and_surfaces_missing_coverage(tmp_path):
    archive = tmp_path / "saved"
    archive.mkdir()
    first = snapshot(archive / "2026-11-19.json", [("1", "saved")])
    live = snapshot(tmp_path / "today.json", [("2", "usable")], "partial", 8)
    ledger = tmp_path / "triage.tsv"
    ledger.write_text("pmid\tstatus\tchecked_on\tstudy_url\n", encoding="utf-8")
    out = tmp_path / "queue.json"
    args = [
        "--snapshots-dir",
        str(archive),
        "--latest",
        str(live),
        "--triage",
        str(ledger),
        "--out",
    ]
    assert main([*args, str(out)]) == 2
    result = json.loads(out.read_text(encoding="utf-8"))
    assert result["remaining"] == 2 and not result["all_searches_complete"]
    assert result["searches"][1]["total_matches"] == 8
    before = first.read_bytes()
    with pytest.raises(SystemExit):
        main([*args, str(first)])
    assert first.read_bytes() == before
