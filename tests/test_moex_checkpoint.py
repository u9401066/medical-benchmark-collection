from medbench import moex_items


def test_prune_pending_only_records_retains_scans_and_parsed_items(tmp_path):
    out = tmp_path / "items"
    shard = out / "81" / "081010.jsonl.gz"
    rows = [
        dict(paper_id="a", items=[], sources=[{"status": "pending"}]),
        dict(paper_id="b", items=[], sources=[{"status": "verified", "sha256": "abc"}]),
        dict(paper_id="c", items=[{"id": "c-01"}], sources=[]),
    ]
    moex_items._write_shard(shard, {r["paper_id"]: r for r in rows})
    moex_items.prune_empty_placeholders(out, tmp_path / "cache")
    assert set(moex_items._read_shard(shard)) == {"b", "c"}
