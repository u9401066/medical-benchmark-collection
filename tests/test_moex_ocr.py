import csv
import gzip
import hashlib
import json
from types import SimpleNamespace

import pytest

from medbench import moex_ocr as ocr


def test_tsv_preserves_word_box_confidence_and_reading_order():
    raw = ("level\tpage_num\tblock_num\tpar_num\tline_num\tword_num\tleft\ttop\twidth\theight\tconf\ttext\n"
           "4\t1\t2\t1\t1\t0\t20\t10\t80\t24\t-1\t\n"
           "5\t1\t2\t1\t1\t1\t20\t10\t80\t24\t53.7\t題\n"
           "5\t1\t2\t1\t2\t1\t30\t40\t60\t36\t-1\tAxillary\n")
    rect = SimpleNamespace(width=100, height=100, x0=0, y0=0)
    lines = ocr.parse_tsv(raw, rect, [200, 200])
    assert [line["line_id"] for line in lines] == ["2.1.1", "2.1.2"]
    assert lines[0]["words"] == [{"text": "題", "confidence": 53.7, "bbox_pt": [10, 5, 50, 17]}]
    assert lines[1]["words"][0]["confidence"] is None


def test_pinned_model_and_identifiers_are_checked(tmp_path):
    pytest.importorskip("pymupdf")
    (tmp_path / "chi_tra.traineddata").write_bytes(b"unexpected weights")
    with pytest.raises(ValueError, match="pinned official"):
        ocr.settings_for(tmp_path, "chi_tra", ocr.MODEL_REVISION, 300, 6, "pymupdf")
    with pytest.raises(ValueError, match="language"):
        ocr.settings_for(tmp_path, "../another", "local-test", 300, 6, "pymupdf")


def test_layout_follows_identical_pdf_across_official_categories(tmp_path):
    profiles = tmp_path / "layouts.tsv"
    digest = "ab" * 32
    profiles.write_text(f"asset_id\tsource_sha256\tlanguage\tpsm\nA\t{digest}\tchi_tra_vert\t5\n", encoding="utf-8")
    assert ocr.read_layouts(profiles)[digest]["asset_id"] == "A"
    with profiles.open("a", encoding="utf-8") as stream:
        stream.write(f"B\t{digest}\tchi_tra\t6\n")
    with pytest.raises(ValueError, match="Conflicting OCR profiles"):
        ocr.read_layouts(profiles)


def test_resumption_repairs_page_cache_and_rechecks_source(tmp_path, monkeypatch):
    mupdf = pytest.importorskip("pymupdf")
    pdf = tmp_path / "source.pdf"
    with mupdf.open() as doc:
        doc.new_page()
        doc.new_page()
        doc.save(pdf)
    row = {"paper_id": "081010-1-01", "asset_type": "Q", "asset_id": "moex-a-Q-1", "source_url": "https://wwwq.moex.gov.tw/a",
           "sha256": hashlib.sha256(pdf.read_bytes()).hexdigest(), "year_roc": "81",
           "local_path": pdf.name, "status": "verified", "format": "pdf"}
    manifest = tmp_path / "files.tsv"
    with manifest.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=row, delimiter="\t")
        writer.writeheader()
        writer.writerow(row)
    calls = []
    def page_transcript(page, tessdata, settings, exe):
        calls.append(page.number)
        return {"pdf_page": page.number + 1, "status": "ocr_draft", "text": "scan draft"}
    monkeypatch.setattr(ocr, "settings_for", lambda *args: ({"language": args[1], "psm": args[4]}, None))
    monkeypatch.setattr(ocr, "scan_page", page_transcript)
    out, cache = tmp_path / "out", tmp_path / "pages"
    args = (manifest, tmp_path, out, cache, tmp_path)
    settings = {"layouts": {row["asset_id"]: {"language": "chi_tra_vert", "psm": "5", "source_sha256": row["sha256"]}}}
    assert ocr.build(*args, **settings)["ocr_draft"] == 2
    shard = next(out.rglob("*.gz"))
    first = shard.read_bytes()
    with gzip.open(shard, "rt", encoding="utf-8") as stream:
        pages = [json.loads(line) for line in stream]
    assert pages[0]["settings"] == {"language": "chi_tra_vert", "psm": 5}
    assert pages[0]["source"]["sha256"] == row["sha256"]
    ocr.build(*args, **settings)
    assert calls == [0, 1] and shard.read_bytes() == first
    next(cache.rglob("0001.json.gz")).write_bytes(b"partial")
    ocr.build(*args, **settings)
    assert calls == [0, 1, 0] and shard.read_bytes() == first
    original = pdf.read_bytes()
    pdf.write_bytes(b"changed source")
    assert ocr.build(*args, **settings) == {"source_hash_or_path_error": 1}
    assert shard.read_bytes() == first
    pdf.write_bytes(original + b"\n")
    row["sha256"] = hashlib.sha256(pdf.read_bytes()).hexdigest()
    with manifest.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=row, delimiter="\t")
        writer.writeheader()
        writer.writerow(row)
    ocr.build(*args, **settings)
    with gzip.open(shard, "rt", encoding="utf-8") as stream:
        assert json.loads(stream.readline())["settings"] == {"language": "chi_tra", "psm": 3}
