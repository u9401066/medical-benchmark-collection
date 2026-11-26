import gzip
import json

from medbench.moex_coverage import build, read_tsv, write


def test_missing_correction_and_boundary_do_not_inflate_coverage(tmp_path):
    index = tmp_path / "index"
    write(index / "coverage.tsv", ["year_roc", "status"], [{"year_roc": "99", "status": "unresolved"}])
    base = {"year_roc": "99", "exam_code": "099010", "category_code": "01", "subject_code": "0010", "scope": "medical"}
    boundary = {**base, "subject_code": "00a3", "scope": "boundary"}
    write(index / "subjects.tsv", list(base), [base, boundary])
    assets = [{**base, "asset_type": role, "source_url": role} for role in ("Q", "S", "M")]
    assets.append({**boundary, "asset_type": "Q", "source_url": "B"})
    write(index / "assets.tsv", list(assets[0]), assets)
    pid = "099010-01-0010"
    manifest = tmp_path / "files.tsv"
    verified = [{**r, "paper_id": pid, "status": "verified"} for r in assets[:2]]
    write(manifest, list(verified[0]), verified)
    items = tmp_path / "items" / "99"
    items.mkdir(parents=True)
    with gzip.open(items / "099010.jsonl.gz", "wt", encoding="utf-8") as f:
        refs = [{"asset_type": role, "source_url": role, "status": "pending" if role == "M" else "verified"}
                for role in ("Q", "S", "M")]
        f.write(json.dumps({"paper_id": pid, "status": "partial", "sources": refs, "items": [
            {"question": "Q", "key_evidence": {"S": {"token": "A"}}, "rule": {"kind": "unresolved"}}]}) + "\n")
    summary = build(index, manifest, items.parent, tmp_path / "coverage")
    assert summary["medical_papers"] == summary["boundary_papers"] == 1
    assert summary["indexed_files"] == 3 and summary["verified_files"] == 2
    assert summary["M_listed"] == summary["rule_unresolved"] == 1
    assert summary["M_verified"] == summary["papers_with_all_listed_files"] == 0
    assert summary["items_with_original_key"] == summary["papers_with_text"] == 1
    year = read_tsv(tmp_path / "coverage" / "years.tsv")[0]
    assert year["status"] == "unresolved"
    verified.append({**assets[2], "paper_id": pid, "status": "verified"})
    write(manifest, list(verified[0]), verified)
    updated = build(index, manifest, items.parent, tmp_path / "coverage")
    assert updated["extraction_stale"] == updated["stale_item_records"] == 1
    assert updated["item_records"] == updated["rule_unresolved"] == 0
