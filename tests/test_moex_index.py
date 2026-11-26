import csv

from medbench.moex_index import asset_id, classify, export, options, parse_result


MENU = """<select name="ctl00$holderContent$wUctlExamYearStart$ddlExamYear">
<option selected="selected" value="1992">81</option></select>
<select name="ctl00$holderContent$ddlExamCode"><option value="">全部</option>
<option value="081010">專門職業及技術人員考試</option></select>"""
RESULT = """<span id="ctl00_holderContent_lblStatistics">共 1 考試 2 類科 2 科目</span>
<td class="level1"><td style="vertical-align:text-top;">專門職業及技術人員考試</td>
<a href="wHandExamQandA_File.ashx?t=A&amp;code=081010">全考試答案</a>
<label for="ctl00_holderContent_chk_081010_004">醫師</label>
<label for="ctl00_holderContent_chk_081010_004_c024" class="exam-title">醫學（一）</label>
<a href="wHandExamQandA_File.ashx?t=Q&amp;code=081010&amp;c=004&amp;s=c024&amp;q=1">試題</a>
<a href="wHandExamQandA_File.ashx?t=Q&amp;code=081010&amp;c=004&amp;s=c024&amp;q=1">試題</a>
<a href="wHandExamQandA_File.ashx?t=M&amp;code=081010&amp;c=004&amp;s=c024&amp;q=1">更正答案</a>
<label for="ctl00_holderContent_chk_081010_017">交通工程技師</label>
<label for="ctl00_holderContent_chk_081010_017_0003" class="exam-title">工程概論</label>"""


def read_tsv(out, name):
    with (out / (name + ".tsv")).open(encoding="utf-8", newline="") as file:
        return list(csv.DictReader(file, delimiter="\t"))


def test_historical_alphanumeric_subject_and_mobile_duplicates():
    assert options(MENU, "wUctlExamYearStart$ddlExamYear") == {"1992": "81"}
    result = parse_result(RESULT)
    assert result.totals == (1, 2, 2)
    assert result.subjects["081010", "004", "c024"] == "醫學（一）"
    assert set(k[3] for k in result.assets) == {"A", "Q", "M"}
    assert len(result.assets) == 3
    for code, encoded in (("02-7", "02%2D7"), ("700*", "700%2A")):
        alt = parse_result(RESULT.replace("c024", code))
        assert ("081010", "004", code) in alt.subjects
        assert asset_id("081010", "004", code, "Q", "1") == f"moex-081010-004-{encoded}-Q-1"


def test_licensing_and_public_health_scope_in_mixed_exams():
    for category in ("藥劑生", "護士", "公職護理師", "公職法醫師", "衛生行政", "衛生技術"):
        assert classify(category) == "medical"
    for category in ("獸醫師", "社會工作師", "消防警察", "食品技師", "安全衛生"):
        assert classify(category) == "boundary"
    assert classify("刑事警察", "法醫學") == "boundary"
    assert classify("交通工程技師", "工程概論") == "outside"


def test_export_compares_official_totals_and_accounts_for_outside_scope(tmp_path):
    cache, out = tmp_path / "cache", tmp_path / "out"
    cache.mkdir()
    for name, text in [("search", MENU), ("year-1992", MENU), ("subjects-1992", RESULT)]:
        (cache / (name + ".html")).write_text(text, encoding="utf-8")
    export(cache, out)
    assert read_tsv(out, "coverage")[0]["status"] == "verified"
    assert len(read_tsv(out, "categories")) == 2
    assert len(read_tsv(out, "subjects")) == 1
    assert [r["asset_id"] for r in read_tsv(out, "assets")] == ["moex-081010-004-c024-M-1", "moex-081010-004-c024-Q-1"]
    assert read_tsv(out, "exam_assets")[0]["asset_role"] == "exam_answers"
    (cache / "subjects-1992.html").write_text(RESULT.replace("2 科目", "3 科目"), encoding="utf-8")
    export(cache, out)
    coverage = read_tsv(out, "coverage")[0]
    assert (coverage["status"], coverage["official_subjects"], coverage["parsed_subjects"]) == ("unresolved", "3", "2")


def test_individual_exam_results_can_recover_missing_annual_page(tmp_path):
    cache, out = tmp_path / "cache", tmp_path / "out"
    cache.mkdir()
    for name, text in [("search", MENU), ("year-1992", MENU), ("exam-1992-081010", RESULT)]:
        (cache / (name + ".html")).write_text(text, encoding="utf-8")
    export(cache, out)
    assert read_tsv(out, "coverage")[0]["status"] == "verified"
    assert read_tsv(out, "exam_coverage")[0]["parsed_subjects"] == "2"


def test_subject_without_its_own_category_heading_keeps_code_and_unknown_name(tmp_path):
    cache, out = tmp_path / "cache", tmp_path / "out"
    cache.mkdir()
    result = RESULT.replace('chk_081010_004">醫師', 'chk_081010_009">醫師')
    for name, text in [("search", MENU), ("year-1992", MENU), ("subjects-1992", result)]:
        (cache / (name + ".html")).write_text(text, encoding="utf-8")
    export(cache, out)
    cat = next(r for r in read_tsv(out, "categories") if r["category_code"] == "004")
    assert cat["category_name"] == "" and cat["subject_count"] == "1" and cat["heading_status"] != "listed"
    assert read_tsv(out, "coverage")[0]["category_codes_without_heading"] == "1"
    assert read_tsv(out, "subjects")[0]["scope"] == "boundary"


def test_official_unpublished_exam_is_accounted_without_inventing_papers(tmp_path):
    cache, out = tmp_path / "cache", tmp_path / "out"
    cache.mkdir()
    menu = MENU.replace("專門職業及技術人員考試</option>", "專門職業及技術人員考試</option>"
                        '<option value="081020">航海人員（未公布試題）</option>')
    for name, text in [("search", menu), ("year-1992", menu), ("subjects-1992", RESULT)]:
        (cache / (name + ".html")).write_text(text, encoding="utf-8")
    export(cache, out)
    row = read_tsv(out, "coverage")[0]
    assert (row["parsed_exams"], row["confirmed_empty_exams"], row["accounted_exams"]) == ("1", "1", "2")
    assert row["status"] == "verified"
