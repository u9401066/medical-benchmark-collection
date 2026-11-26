import hashlib
import json
from io import BytesIO
from types import SimpleNamespace

from scripts import tw_society_directory

from scripts.tw_society_directory import add_exam_metadata, compare_websites, extract, website_candidate


def test_domestic_boundaries_and_historical_host():
    raw = """
    <a href="https://hospital.example/">某醫院</a>
    <a name="comestic"></a><a name="1"></a>
    <a href="http://www.vghtpe.gov.tw/~tes">中華民國癲癇學會</a>
    <a name="abroad"></a><a href="https://international.example/">國際醫學會</a>
    """.encode()
    rows = extract("tami", raw)
    assert len(rows) == 1
    assert rows[0]["name"] == "中華民國癲癇學會"
    assert rows[0]["raw_href"] == "http://www.vghtpe.gov.tw/~tes"
    assert rows[0]["website"] == ""
    assert rows[0]["source_sha256"] == hashlib.sha256(raw).hexdigest()


def test_split_anchor_and_misdirected_radiation_society():
    raw = '<table><tr><td><a href="https://example.org/">台灣</a><a href="https://example.org/">腫瘤護理學會</a></td></tr></table>'.encode()
    rows = extract("ctcn", raw)
    assert [row["name"] for row in rows] == ["台灣腫瘤護理學會"]
    assert website_candidate("台灣放射腫瘤學會", "https://www.rsroc.org.tw/", "") == ("", "different_society_domain")


def test_only_identified_homepage_is_confirmed(tmp_path):
    url = "https://example.org/"
    receipt = {"requested": url, "destination": url, "date": "2026-11-26",
               "sha256": "a" * 64, "labels": ["臺灣腫瘤護理學會"]}
    (tmp_path / (hashlib.sha256(url.encode()).hexdigest() + ".json")).write_text(json.dumps(receipt), encoding="utf8")
    rows = [{"website": "http://example.org/old", "name": n, "website_check": "directory_only"}
            for n in ("台灣腫瘤護理學會(TONS)", "台灣護理學會")]
    compare_websites(rows, tmp_path, False)
    assert rows[0]["website_check"] == "identity_verified"
    assert rows[0]["website"] == url
    assert rows[1]["website_check"] == "directory_only"
    assert rows[1]["website"] == ""


def test_exam_evidence_tracks_distinct_attachment_roles():
    records = [{"name": "台灣醫學資訊學會", "raw_href": "http://www.medinfo.org.tw"}]
    add_exam_metadata(records)
    result = records[0]
    assert result["exam_evidence"] == "public_questions_with_key"
    assert result["exam_url"].endswith("postid=1183")
    assert "1-261121_MIM_Q&A.pdf" in result["exam_note"]
    assert "2-261121_MIA_Q.pdf" in result["exam_note"]
    assert "附件僅載題目" in result["exam_note"]


def test_empty_homepage_yields_a_receipt_without_affecting_other_sites(tmp_path, monkeypatch):
    url = "https://example.org/"
    page = BytesIO(b"")
    page.geturl = lambda: url
    monkeypatch.setattr(tw_society_directory, "build_opener", lambda *args: SimpleNamespace(open=lambda *a, **kw: page))
    result = tw_society_directory.web_identity(url, tmp_path, True)
    assert result.get("error") and not result.get("labels")
    assert result == tw_society_directory.web_identity(url, tmp_path, False)
