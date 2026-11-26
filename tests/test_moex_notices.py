import json
from io import BytesIO
from pathlib import Path
from zipfile import ZipFile

from medbench.moex_notices import (
    INDEXES,
    Page,
    annual_exam_codes,
    attachment_links,
    extract_docx_paragraphs,
    list_rows,
    media,
    scan_index,
    title_in_scope,
)


def test_official_notice_listing_carries_roc_date_and_actual_attachment_parent():
    listing = """<table><tr><td><a id="ctl00_holderContent_grdNews_ctl02_lnkTitle"
      href="../news/wfrmNews.aspx?kind=3&amp;menu_id=42&amp;news_id=5979">社會工作試題疑義</a></td>
      <td><span id="ctl00_holderContent_grdNews_ctl02_lblBeginDate" translate="no">112/08/02</span></td></tr></table>"""
    (row,) = list_rows(listing.encode(), INDEXES["latest_news"])
    assert row["publication_date"] == "2023-08-02"
    assert row["url"] == INDEXES["latest_news"] + "&news_id=5979"
    page = Page(
        b'<a id="one_lnkFiles" href="../controls/a.ashx?id=1&amp;v=2" title="document"></a>'
        b'<a id="two_lnkFiles" href="https://external.invalid/file.pdf">external</a>'
    )
    assert attachment_links(page, row["url"]) == [
        ("https://wwwc.moex.gov.tw/main/controls/a.ashx?id=1&v=2", "document")
    ]


def test_paginated_case_law_archive_uses_next_form_and_checks_count():
    def page(i, next_button):
        return (
            f'<table id="ctl00_holderContent_grdLaws"><tr><td><a id="a_lnkTitle" href="?item={i}">'
            f"試題疑義</a></td></tr></table><span>共 </span><span>2</span><span> 筆</span>"
            f'<input type="hidden" name="__VIEWSTATE" value="page-{i}">'
            + ('<input type="submit" name="x$btnNext" value="下一頁">' if next_button else "")
        ).encode()

    class RecordedPages:
        def fetch(self, url, key, form=None):
            if form:
                assert form == {"__VIEWSTATE": "page-1", "x$btnNext": "下一頁"}
                return page(2, False)
            return page(1, True)

    cov = []
    rows = scan_index(RecordedPages(), "case_law", INDEXES["case_law"], "", cov)
    assert [r["page"] for r in cov] == [1, 2]
    assert len(rows) == 2 and all(r["reported_total"] == 2 for r in cov)


def test_official_word_file_uses_signature_and_main_document_paragraphs():
    data = BytesIO()
    with ZipFile(data, "w") as f:
        f.writestr(
            "word/document.xml",
            """<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
        <w:body><w:p><w:r><w:t>更正為</w:t></w:r><w:r><w:t>B 或 A</w:t></w:r></w:p></w:body></w:document>""",
        )
    assert media(data.getvalue()) == "docx"
    assert extract_docx_paragraphs(data.getvalue()) == ["更正為B 或 A"]
    assert media(b"<html>document.pdf</html>") == "unknown"
    assert title_in_scope("測驗式試題標準答案更正", "exam_detail")
    assert not title_in_scope("線上申請試題疑義操作說明", "exam_detail")


def test_nonmedical_title_can_contain_human_medical_category(tmp_path):
    (tmp_path / "year-1992.html").write_text(
        '<select name="ctl00$holderContent$ddlExamCode">'
        '<option value="081010">081專門職業及技術人員高等暨普通考試</option></select>',
        encoding="utf8",
    )
    cats = tmp_path / "categories.tsv"
    cats.write_text("year_roc\texam_code\tscope\n81\t081010\tmedical\n", encoding="utf8")
    codes, cov = annual_exam_codes(tmp_path, [1992], cats)
    assert codes == {"081010"} and cov[0]["title_matches"] == []
    assert cov[0]["medical_category_matches"] == ["081010"]


def test_curated_decisions_separate_litigant_claims_from_awards_and_boundaries():
    source = Path(__file__).resolve().parents[1] / "datasets/moex/notices/decisions.json"
    cases = json.loads(source.read_text(encoding="utf8"))
    clinical = {d["question"]: d for d in cases["clinical_items"]}
    assert clinical[13]["ruling"] == "original_key_upheld"
    assert clinical[10]["accepted_options"] == ["A", "B"]
    assert clinical[10]["paper_item_id"] == "090040-001-2004-010"
    assert clinical[13]["paper_item_id"] == "090040-001-3004-013"
    assert clinical[46]["ruling"] == "original_key_upheld"
    same_sheet = {x["question"]: x for x in clinical[46]["other_items_in_same_correction_sheet"]}
    assert same_sheet[1]["accepted_responses"] == ["A", "B", "AB"]
    assert same_sheet[18]["ruling"] == "universal_award"
    (boundary,) = cases["boundary_items"]
    assert boundary["original_key"] == "C" and boundary["ruling"] == "universal_award"
    assert boundary["source"] != boundary["preliminary_source"]
    assert all(c["source"] in cases["source_documents"] for c in [boundary, *clinical.values()])


def test_historical_publication_requires_exact_item_and_answer_conditions():
    source = Path(__file__).resolve().parents[1] / "datasets/moex/notices/decisions.json"
    cases = json.loads(source.read_text(encoding="utf8"))
    records = {r["id"]: r for r in cases["clinical_items"]}
    disputed = records["moex-compendium-6-8-public-health-086"]
    assert disputed["paper_item_id"] is None and "corrected_asset" not in disputed
    conflict = disputed["mapping_conflict"]
    assert conflict["reported_question"] > conflict["candidate_item_count"]
    assert conflict["candidate_question_68_responses"] == ["B", "BC"]
    assert conflict["candidate_source"] in cases["source_documents"]
    item = records["moex-compendium-6-10-medical-science-004"]
    assert item["original_key"] == "D" and item["accepted_options"] == ["C", "D"]
    assert item["paper_item_id"] == "099130-101-200-004" and "original_asset" not in item
    early = next(x for x in cases["unresolved_case_summaries"] if x["id"] == "moex-compendium-6-9-basic-sciences")
    assert early["question"] is None and early["candidate_item_numbers"] == [49, 79]


def test_fulltext_search_finds_unlabelled_ruling_and_ignores_navigation(tmp_path):
    from medbench.moex_notices import NewsBody, extract_file, signals

    body = NewsBody(
        """<nav>查詢試題疑義</nav><div class="news-content"><div>本次考試公告</div>
    <p>第七題一律給分。</p><a href="files/final.pdf">附件</a></div><footer>疑義公告</footer>""".encode()
    )
    assert body.has_article and signals("".join(body.parts)) == ["award"]
    assert body.hrefs == [("files/final.pdf", "")]
    path = tmp_path / "original.bin"
    with ZipFile(path, "w") as archive:
        archive.writestr(
            "word/document.xml",
            '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body><w:p><w:r><w:t>第 2 題更正答案</w:t></w:r></w:p></w:body></w:document>',
        )
    kind, parts = extract_file(path)
    assert kind == "docx" and signals(parts[0][1]) == ["key_revision"] and parts[0][0] == "paragraph-1"


def test_offline_inventory_distinguishes_missing_attachment_from_scanned_body(tmp_path):
    from medbench.moex_notices import Cache, fulltext, sha

    cache = Cache(tmp_path / "raw", offline=True)
    empty = '<table id="ctl00_holderContent_grdNews">目前無資料！</table>'.encode()
    for name in ("latest_news.html", "exam_bulletins.html", "emergency.html"):
        (cache.path / name).write_bytes(empty)
    listing = """<table id="ctl00_holderContent_grdNews"><tr><td><a id="row_lnkTitle"
    href="../news/story.aspx">例行考試公告</a></td><td><span id="a_lblBeginDate">112/08/02</span></td></tr></table>
    <span>共</span><span>1</span><span>筆</span>"""
    (cache.path / "latest_news-all-1.html").write_text(listing, encoding="utf8")
    url = "https://wwwc.moex.gov.tw/main/news/story.aspx"
    (cache.path / ("notice-" + sha(url.encode())[:20] + ".html")).write_text(
        '<div class="news-content"><p>第5題一律給分。</p><a href="test.pdf">附件</a></div>', encoding="utf8"
    )
    summary = fulltext(cache, tmp_path / "report")
    assert summary["reported"]["latest_news"] == summary["unique_articles"] == summary["bodies_scanned"] == 1
    assert summary["bodies_pending"] == 0
    assert summary["attachment_statuses"] == {"pending": 1}
    assert "block-1" in (tmp_path / "report/articles.tsv").read_text(encoding="utf8")


def test_weekly_records_nonmedical_titles_without_fetching_their_pdfs(tmp_path, monkeypatch):
    from medbench import moex_notices as notices

    class Listing:
        path = tmp_path

        def fetch(self, url, key):
            return b'<span id="lblCount">15334</span>'

    titles = ["醫師考試更正答案", "試題疑義處理辦法", "公路特考瑕疵一律給分"]
    rows = [
        dict(url=f"{notices.BASE}weekly-{i}", title=title, publication_date=None) for i, title in enumerate(titles)
    ]
    monkeypatch.setattr(
        notices, "scan_index", lambda cache, label, url, query, logs: rows if query == "給分" else []
    )
    fetched = []

    def download(cache, parent, url, title):
        fetched.append(title)
        return dict(sha256="a" * 64, bytes=10, media="pdf", cache_key="cache.bin")

    monkeypatch.setattr(notices, "save_attachment", download)
    report = notices.weekly_index(Listing(), tmp_path / "report")
    assert len(report["matches"]) == 3 and fetched == titles[:2]
    assert report["matches"][2]["file_status"] == "outside_download_scope"
