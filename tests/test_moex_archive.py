import hashlib
import io
import zipfile

import pytest

from medbench import moex_archive as archive


URL = "https://wwwq.moex.gov.tw/exam/wHandExamQandA_File.ashx?t=M&code=113180&c=101&s=0103&q=1"


def test_document_signatures_and_official_redirects():
    assert archive.detect(b"%PDF-1.6\nexample\n%%EOF", "application/octet-stream", "") == "pdf"
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("[Content_Types].xml", "<Types/>")
        z.writestr("word/document.xml", "<document/>")
    assert archive.detect(buf.getvalue(), "application/octet-stream", "") == "docx"
    for payload in (b"<html>No download</html>", b"%PDF-1.6\ntruncated"):
        with pytest.raises(ValueError):
            archive.detect(payload, "application/pdf", "")
    assert archive.official(URL)
    for url in ("https://wwwq.moex.gov.tw.example.org/", "http://wwwq.moex.gov.tw/", "https://name@wwwq.moex.gov.tw/"):
        assert not archive.official(url)


def test_sha_history_and_failed_refresh_keep_verified_bytes(tmp_path, monkeypatch):
    monkeypatch.setattr(archive.time, "sleep", lambda seconds: None)
    row = {"source_url": URL}
    first = archive.save_payload(row, tmp_path, b"v1", "pdf", URL)
    second = archive.save_payload(row, tmp_path, b"v2", "pdf", URL)
    assert (tmp_path / first["local_path"]).read_bytes() == b"v1"
    assert first["sha256"] != second["sha256"]

    class Failed:
        def open(self, request, timeout):
            raise OSError("unavailable")

    after = archive.acquire(row, tmp_path, Failed())
    assert after["status"] == "verified" and after["sha256"] == second["sha256"]
    assert after["error"] == "unavailable" and after["last_attempt_at"]
    (tmp_path / after["local_path"]).write_bytes(b"xx")
    assert archive.cached(tmp_path, URL, verify=True)["status"] == "local_file_invalid"


def test_pinned_seed_and_live_original_can_coexist(tmp_path):
    seed = tmp_path / "seed.tsv"
    seed.write_text("exam\tcategory\tsubject\tfile\turl\tsha256\n"
                    f"113180\t護理師\t內外科\tM\t{URL}\t{'1' * 64}\n", encoding="utf-8")
    index = tmp_path / "index.tsv"
    index.write_text("year_roc\texam_code\tcategory_code\tsubject_code\tscope\tasset_type\tsource_url\n"
                     f"113\t113180\t101\t0103\tmedical\tM\t{URL}\n"
                     f"113\t113180\t101\t0103\tmedical\tS\t{URL.replace('t=M', 't=S')}\n", encoding="utf-8")
    rows = archive.plan([index], seed)
    assert len(rows) == 2 and all(r["paper_id"] == "113180-101-0103" for r in rows)
    assert rows[0]["listed_by"] == "official-index+twmed-v1" and rows[0]["asset_sequence"] == "1"
    out = tmp_path / "report.tsv"
    archive.export(rows, {URL: {"sha256": hashlib.sha256(b"new").hexdigest(), "status": "verified"}}, out)
    corrected, original = archive.read_tsv(out)
    assert corrected["prior_comparison"] == "changed"
    assert original["status"] == "pending" and original["sha256"] == ""


def test_whole_exam_packages_are_separate_and_require_a_relevant_subject(tmp_path):
    (tmp_path / "subjects.tsv").write_text("exam_code\tscope\n081010\tmedical\n081020\tboundary\n", encoding="utf-8")
    (tmp_path / "exam_assets.tsv").write_text("exam_code\tasset_type\tsource_url\n081010\tA\turl1\n081020\tA\turl2\n",
                                             encoding="utf-8")
    result = archive.exam_plan(tmp_path, {"medical"})
    assert [(r["exam_code"], r["paper_id"], r["asset_type"]) for r in result] == [("081010", "", "A")]
