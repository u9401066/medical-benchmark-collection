import csv

import pytest

from medbench.moex_archive import read_tsv
from medbench.moex_coverage import write
from medbench.moex_opendata import build, register_csv, resolve


def test_csv_corrected_url_and_disagreeing_original_url():
    base = "https://wwwq.moex.gov.tw/exam/wHandExamQandA_File.ashx?code=101010&c=301&s="
    row = {"考試代碼": "101010", "類科代碼": "301", "試題網址": base + "11&t=Q", "測驗式試題答案網址": base + "11&t=M"}
    key = ("101010", "301", "11")
    assert resolve(row, {key}) == (key, "matched")
    assert resolve({**row, "測驗式試題答案網址": base + "22&t=S"}, {key}) == (None, "conflicting_keys")


def test_csv_scope_disagreement_and_snapshot_boundaries(tmp_path):
    index, cache, out = (tmp_path / name for name in ("index", "cache", "out"))
    url = "https://wwwq.moex.gov.tw/exam/wHandExamQandA_File.ashx?t=Q&code=115010&c=001&s="
    fields = ["考試年度", "考試代碼", "考試名稱", "類科代碼", "科目全名", "試題型態", "試題網址", "測驗式試題答案網址", "備註", "類科組別", "節次"]
    data = tmp_path / "test.csv"
    with data.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fields)
        writer.writeheader()
        for sub, cat in (("01", "醫師"), ("02", "工程"), ("03", "工程"), ("04", "藥師")):
            writer.writerow({"考試年度": "115", "考試代碼": "115010", "考試名稱": "聯合考試", "類科代碼": "001",
                             "科目全名": "科目" + sub, "試題型態": "測驗題", "試題網址": url + sub,
                             "類科組別": cat, "節次": "1"})
    headers = tmp_path / "headers"
    headers.write_text("HTTP/1.1 200 OK\nContent-Type: text/csv\n\n", encoding="ascii")
    meta = register_csv(cache, data, headers, "government_csv_export")
    assert meta["csv_rows"] == 4 and meta["delivery"] == "government_csv_export"
    rows = []
    for exam, sub, scope in (("115010", "01", "medical"), ("115010", "02", "boundary"),
                             ("115010", "05", "boundary"), ("115020", "06", "medical")):
        rows.append(dict(year_roc="115", exam_code=exam, category_code="001", category_name="",
                         subject_code=sub, subject_name="科目"+sub, scope=scope))
    write(index / "subjects.tsv", list(rows[0]), rows)
    write(index / "assets.tsv", ["exam_code", "category_code", "subject_code", "source_url", "asset_type"], [])
    write(index / "coverage.tsv", ["year_roc"], [{"year_roc": "115"}])
    build(index, cache, out)
    year = read_tsv(out / "years.tsv")[0]
    assert (year["medical_csv_rows"], year["outside_csv_rows"], year["boundary_csv_rows"]) == ("2", "2", "0")
    assert year["medical_csv_only"] == "1" and year["outside_matched_to_portal_selection"] == "1"
    assert year["boundary_portal_only"] == "1" and year["medical_exam_not_in_csv"] == "1"
    diff = next(r for r in read_tsv(out / "records.tsv") if r["scope"] == "outside")
    assert (diff["portal_scope"], diff["mapping"]) == ("boundary", "matched")
    assert read_tsv(out / "exams.tsv")[0]["scope_count"] == "2"


def test_csv_rejects_html_and_incomplete_origin(tmp_path):
    file = tmp_path / "response"
    headers = tmp_path / "headers"
    file.write_bytes(b"<html>Not found</html>")
    headers.write_text("HTTP/1.1 200 OK\nContent-Type: text/html\n\n")
    with pytest.raises(ValueError, match="did not return a CSV"):
        register_csv(tmp_path, file, headers, "government_csv_export")
    headers.write_text("HTTP/1.1 200 OK\nContent-Type: application/octet-stream\nContent-Length: 9000\n\n")
    with pytest.raises(ValueError, match="length"):
        register_csv(tmp_path, file, headers, "origin")
